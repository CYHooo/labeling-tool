from labeling_tool.session import mask_store, naming
from labeling_tool.session.workspace import Workspace


def _photo_files(ws, ts):
    fn = naming.stitched_filename(ts)
    stem = f"stitched_{ts}"
    return [
        ws.origin_dir / fn,
        ws.detected_dir / naming.detected_mask_filename(ts),
        ws.labeling_dir / mask_store.mask_name(fn),
        ws.labeling_dir / mask_store.bbox_name(fn),
        ws.highlight_dir / mask_store.mask_name(fn),
        ws.repair15_dir / mask_store.mask_name(fn),
        ws.result_dir / f"{stem}.png",
        ws.result_dir / f"{stem}.txt",
    ]


def test_remove_photo_files_deletes_only_that_photos_files(tmp_path):
    ws = Workspace(root=tmp_path, session_id=1)
    ws.ensure()
    mine, other = _photo_files(ws, 100), _photo_files(ws, 200)
    for p in mine + other:
        p.write_bytes(b"x")

    removed = ws.remove_photo_files(naming.stitched_filename(100), 100)

    assert sorted(removed) == sorted(mine)
    assert not any(p.exists() for p in mine)
    assert all(p.exists() for p in other)
    assert ws.remove_photo_files(naming.stitched_filename(100), 100) == []


def test_remove_photo_files_logs_and_continues_on_oserror(tmp_path, monkeypatch):
    from pathlib import Path
    ws = Workspace(root=tmp_path, session_id=1)
    ws.ensure()
    files = _photo_files(ws, 100)
    for p in files:
        p.write_bytes(b"x")
    real_unlink = Path.unlink

    def flaky(self, *a, **kw):
        if self == files[0]:
            raise PermissionError("locked")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", flaky)
    removed = ws.remove_photo_files(naming.stitched_filename(100), 100)
    assert files[0] not in removed and len(removed) == 7
    assert files[0].exists()
