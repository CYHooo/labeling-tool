from labeling_tool.api.uploader import upload_session


class FakeClient:
    def __init__(self):
        self.presigned_calls = []
        self.puts = []
        self.register_calls = []

    def request_presigned(self, session_id, files):
        self.presigned_calls.append((session_id, files))
        return {"urls": [
            {"filename": f["filename"],
             "s3Key": f"results/{session_id}/masks/{f['filename']}",
             "presignedUrl": f"https://s3/{f['filename']}",
             "cacheControl": "max-age=0, must-revalidate"} for f in files]}

    def put_mask(self, url, data, *, content_type, cache_control):
        self.puts.append(url)

    def register_annotations(self, *, edit_batch_id, session_id, items):
        self.register_calls.append((edit_batch_id, session_id, len(items)))
        return {"sessionId": session_id, "status": "saved",
                "updatedPhotoCount": len(items)}


def _item(ts):
    return {"timestamp": ts,
            "maskS3Key": f"results/43/masks/mask_{ts}.png",
            "highlightS3Key": f"results/43/masks/high_{ts}.png",
            "repair15S3Key": f"results/43/masks/15_{ts}.png",
            "pxPerCm": 10.0, "scaleSource": "aruco",
            "repairAreas": [], "crackMetrics": {}}


def _bytes(ts):
    return {"mask": f"m{ts}".encode(),
            "high": f"h{ts}".encode(),
            "repair15": f"r{ts}".encode()}


def test_uploads_single_batch_in_order():
    client = FakeClient()
    items = [_item(1), _item(2)]
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="batch-xyz")
    assert result["uploaded"] == 2
    assert result["failed"] == []
    assert client.register_calls == [("batch-xyz-0", 43, 2)]   # per-batch id
    assert len(client.puts) == 6                       # 3 PUTs * 2 photos
    # mask -> high -> 15 order for the first photo
    assert client.puts[0] == "https://s3/mask_1.png"
    assert client.puts[1] == "https://s3/high_1.png"
    assert client.puts[2] == "https://s3/15_1.png"


def test_paginates_over_100():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 items -> 5 batches (BATCH_LIMIT=33)
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="b")
    assert result["uploaded"] == 150
    assert [c[2] for c in client.register_calls] == [33, 33, 33, 33, 18]
    # each batch registers under its OWN editBatchId (else later batches are
    # deduped away server-side and their highlight/15/metrics never persist)
    assert [c[0] for c in client.register_calls] == ["b-0", "b-1", "b-2", "b-3", "b-4"]
    assert len(client.puts) == 450                     # 3 * 150


def test_each_batch_gets_distinct_edit_batch_id():
    """Regression: reusing one editBatchId made register dedupe every batch
    after the first, so only the first 33 photos' annotations persisted."""
    client = FakeClient()
    items = [_item(i) for i in range(1, 70)]    # 69 items -> 3 batches (33,33,3)
    upload_session(client, session_id=43, items=items,
                   bytes_for=_bytes, edit_batch_id="run9")
    ids = [c[0] for c in client.register_calls]
    assert ids == ["run9-0", "run9-1", "run9-2"]
    assert len(set(ids)) == len(ids)            # all distinct


def test_v2_presign_never_exceeds_100_files():
    client = FakeClient()
    items = [_item(i) for i in range(1, 41)]    # 40 items -> 2 presign calls (33, 7)
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="b")
    assert result["uploaded"] == 40
    assert len(client.presigned_calls) == 2      # [33, 7] batches
    for _sid, files in client.presigned_calls:
        assert len(files) <= 100                 # V2 file array cap never exceeded


def test_v4_failure_recorded_per_batch():
    class FailingRegister(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailingRegister()
    result = upload_session(
        client, session_id=43, items=[_item(1)],
        bytes_for=_bytes, edit_batch_id="b")
    assert result["uploaded"] == 0
    assert len(result["failed"]) == 1


def test_progress_reports_each_item():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 -> 2 batches
    seen = []
    result = upload_session(
        client, session_id=43, items=items,
        bytes_for=_bytes, edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 150
    assert seen[-1] == (150, 150)
    assert all(d <= t for d, t in seen)
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_progress_completes_even_when_batch_fails():
    class FailReg(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailReg()
    seen = []
    result = upload_session(
        client, session_id=43, items=[_item(1), _item(2)],
        bytes_for=_bytes, edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 0
    assert seen[-1] == (2, 2)


def test_failed_batch_is_logged():
    """A failing batch's reason must land in the vapi log so users can diagnose."""
    import logging
    from labeling_tool.logging_setup import vlog

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    class FailReg(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom-500")

    log = vlog()
    h = _Capture()
    log.addHandler(h)
    prev_level = log.level
    log.setLevel(logging.INFO)
    try:
        result = upload_session(
            FailReg(), session_id=43, items=[_item(1)],
            bytes_for=_bytes, edit_batch_id="b")
    finally:
        log.removeHandler(h)
        log.setLevel(prev_level)

    assert result["uploaded"] == 0
    assert any("boom-500" in m for m in records), records
