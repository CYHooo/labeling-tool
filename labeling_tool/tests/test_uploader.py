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
            "pxPerCm": 10.0, "scaleSource": "aruco",
            "repairAreas": [], "crackMetrics": {}}


def test_uploads_single_batch_in_order():
    client = FakeClient()
    items = [_item(1), _item(2)]
    result = upload_session(
        client, session_id=43, items=items,
        mask_bytes_for=lambda ts: f"png{ts}".encode(),
        edit_batch_id="batch-xyz")
    assert result["uploaded"] == 2
    assert result["failed"] == []
    assert client.register_calls == [("batch-xyz", 43, 2)]
    assert len(client.puts) == 2


def test_paginates_over_100():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 items -> 2 batches
    result = upload_session(
        client, session_id=43, items=items,
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b")
    assert result["uploaded"] == 150
    # 100 + 50
    assert [c[2] for c in client.register_calls] == [100, 50]
    # same editBatchId reused across pages
    assert {c[0] for c in client.register_calls} == {"b"}


def test_v4_failure_recorded_per_batch():
    class FailingRegister(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailingRegister()
    result = upload_session(
        client, session_id=43, items=[_item(1)],
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b")
    assert result["uploaded"] == 0
    assert len(result["failed"]) == 1


def test_progress_reports_each_item():
    client = FakeClient()
    items = [_item(i) for i in range(1, 151)]   # 150 -> 2 batches
    seen = []
    result = upload_session(
        client, session_id=43, items=items,
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 150
    assert seen[-1] == (150, 150)          # reaches the end
    assert all(d <= t for d, t in seen)    # never overshoots
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)  # monotonic


def test_progress_completes_even_when_batch_fails():
    class FailReg(FakeClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            raise RuntimeError("boom")

    client = FailReg()
    seen = []
    result = upload_session(
        client, session_id=43, items=[_item(1), _item(2)],
        mask_bytes_for=lambda ts: b"x", edit_batch_id="b",
        progress=lambda done, total: seen.append((done, total)))
    assert result["uploaded"] == 0
    assert seen[-1] == (2, 2)              # bar still reaches total
