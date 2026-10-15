"""surfaceUpdates / deletes riding along in register-annotations batches."""

from labeling_tool.api.uploader import upload_session


class EditClient:
    def __init__(self, fail_call=None, skip=(), as_objects=False):
        self.presigned_calls = []
        self.puts = []
        self.registers = []
        self.fail_call = fail_call
        self.skip = set(skip)
        self.as_objects = as_objects

    def request_presigned(self, session_id, files):
        self.presigned_calls.append(files)
        return {"urls": [{"filename": f["filename"],
                          "presignedUrl": f"https://s3/{f['filename']}"}
                         for f in files]}

    def put_mask(self, url, data, *, content_type, cache_control):
        self.puts.append(url)

    def register_annotations(self, *, edit_batch_id, session_id, items,
                             surface_updates=None, deletes=None):
        n = len(self.registers)
        self.registers.append({"id": edit_batch_id, "items": items,
                               "surface_updates": surface_updates,
                               "deletes": deletes})
        if self.fail_call == n:
            raise RuntimeError("boom")
        ts = [d["timestamp"] for d in (deletes or [])]
        deleted = [t for t in ts if t not in self.skip]
        skipped = [t for t in ts if t in self.skip]
        if self.as_objects:
            deleted = [{"timestamp": t} for t in deleted]
            skipped = [{"timestamp": t} for t in skipped]
        return {"updatedPhotoCount": len(items),
                "deleted": deleted, "skipped": skipped}


def _item(ts):
    return {"timestamp": ts}


def _bytes(ts):
    return {"mask": b"m", "high": b"h", "repair15": b"r"}


def _run(client, items=(), surface=(), deletes=()):
    return upload_session(client, session_id=1, items=list(items),
                          bytes_for=_bytes, edit_batch_id="b",
                          surface_updates=list(surface), deletes=list(deletes))


def _dels(n, start=1000):
    return [{"timestamp": start + i} for i in range(n)]


def test_deletes_only_skip_presigned_and_put():
    c = EditClient()
    r = _run(c, deletes=_dels(2))
    assert c.presigned_calls == [] and c.puts == []
    assert len(c.registers) == 1
    assert c.registers[0]["items"] == []
    assert c.registers[0]["deletes"] == _dels(2)
    assert r["deleted_timestamps"] == [1000, 1001]


def test_surface_only():
    c = EditClient()
    r = _run(c, surface=[{"timestamp": 5, "surface": "wall"}])
    assert len(c.registers) == 1
    assert c.registers[0]["surface_updates"] == [{"timestamp": 5, "surface": "wall"}]
    assert c.registers[0]["id"] == "b-0"
    assert r["surface_timestamps"] == [5]


def test_mixed_batches():
    c = EditClient()
    _run(c, items=[_item(i) for i in range(1, 41)], deletes=_dels(150))
    assert len(c.registers) == 2
    assert [len(x["items"]) for x in c.registers] == [33, 7]
    assert [len(x["deletes"]) for x in c.registers] == [100, 50]
    assert [x["id"] for x in c.registers] == ["b-0", "b-1"]


def test_more_edit_batches_than_item_batches():
    c = EditClient()
    _run(c, items=[_item(1)], deletes=_dels(250))
    assert [len(x["items"]) for x in c.registers] == [1, 0, 0]
    assert len(c.presigned_calls) == 1


def test_skipped_and_object_formats_count_as_deleted():
    c = EditClient(skip={1001}, as_objects=True)
    r = _run(c, deletes=_dels(2))
    assert r["deleted_timestamps"] == [1000, 1001]


def test_second_batch_failure_splits_results():
    c = EditClient(fail_call=1)
    r = _run(c, items=[_item(i) for i in range(1, 41)],
             deletes=_dels(150),
             surface=[{"timestamp": 7, "surface": "floor"}])
    assert r["deleted_timestamps"] == [x["timestamp"] for x in _dels(100)]
    assert len(r["failed"]) == 1
    f = r["failed"][0]
    assert f["delete_timestamps"] == [x["timestamp"] for x in _dels(150)[100:]]
    assert f["surface_timestamps"] == []
    assert r["surface_timestamps"] == [7]


def test_no_edits_passes_no_extra_kwargs():
    class Strict(EditClient):
        def register_annotations(self, *, edit_batch_id, session_id, items):
            self.registers.append(items)
            return {"updatedPhotoCount": len(items)}
    c = Strict()
    r = upload_session(c, session_id=1, items=[_item(1)], bytes_for=_bytes,
                       edit_batch_id="b")
    assert len(c.registers) == 1
    assert r["deleted_timestamps"] == [] and r["surface_timestamps"] == []


def test_nothing_at_all_makes_no_calls():
    c = EditClient()
    r = _run(c)
    assert c.registers == [] and r["uploaded"] == 0


# ---- client request body ------------------------------------------------

import json

import responses

from labeling_tool.api.client import ViewerApiClient

_BASE = "https://api.example.com"


def _register_body(**kw):
    with responses.RequestsMock() as rs:
        rs.add(responses.POST, f"{_BASE}/api/viewer/register-annotations/",
               json={"status": "saved", "updatedPhotoCount": 0}, status=200)
        ViewerApiClient(base_url=_BASE, api_key="k").register_annotations(
            edit_batch_id="b", session_id=1, items=[], **kw)
        return json.loads(rs.calls[0].request.body)


def test_client_body_unchanged_without_edits():
    assert _register_body() == {"editBatchId": "b", "sessionId": 1, "items": []}
    assert _register_body(surface_updates=[], deletes=[]) == {
        "editBatchId": "b", "sessionId": 1, "items": []}


def test_client_body_carries_non_empty_edits():
    body = _register_body(surface_updates=[{"timestamp": 1, "surface": "wall"}],
                          deletes=[{"timestamp": 2}])
    assert body["surfaceUpdates"] == [{"timestamp": 1, "surface": "wall"}]
    assert body["deletes"] == [{"timestamp": 2}]


# ---- worker passthrough ---------------------------------------------------

def _run_worker(tmp_path, client, **kw):
    from PyQt5.QtWidgets import QApplication
    from labeling_tool.ui.upload_worker import UploadWorker
    QApplication.instance() or QApplication([])
    (tmp_path / "Labeling").mkdir(exist_ok=True)
    worker = UploadWorker(client, session_id=1, specs=[],
                          labeling_dir=str(tmp_path / "Labeling"),
                          edit_batch_id="b", **kw)
    results = []
    worker.done.connect(results.append)
    worker.run()
    return results


def test_worker_uploads_edits_without_items(tmp_path):
    c = EditClient()
    res = _run_worker(tmp_path, c, deletes=_dels(2),
                      surface_updates=[{"timestamp": 5, "surface": "floor"}])
    assert len(c.registers) == 1
    assert res[0]["deleted_timestamps"] == [1000, 1001]
    assert res[0]["surface_timestamps"] == [5]
    assert res[0]["failed"] == []


def test_worker_with_nothing_still_returns_early(tmp_path):
    c = EditClient()
    res = _run_worker(tmp_path, c)
    assert c.registers == []
    assert res[0]["deleted_timestamps"] == [] and res[0]["uploaded"] == 0


# ---- fix round 1 ----------------------------------------------------------

def test_unsent_timestamp_from_server_is_not_deleted():
    class Extra(EditClient):
        def register_annotations(self, **kw):
            r = super().register_annotations(**kw)
            r["deleted"] = r["deleted"] + [999999]
            r["skipped"] = [888888]
            return r
    r = _run(Extra(), deletes=_dels(1))
    assert r["deleted_timestamps"] == [1000]


def test_post_register_failure_is_not_in_both_lists():
    class BadCount(EditClient):
        def register_annotations(self, **kw):
            r = super().register_annotations(**kw)
            r["updatedPhotoCount"] = "many"
            return r
    r = _run(BadCount(), items=[_item(1)], deletes=_dels(1))
    assert len(r["failed"]) == 1
    assert r["failed"][0]["delete_timestamps"] == [1000]
    assert r["deleted_timestamps"] == []
