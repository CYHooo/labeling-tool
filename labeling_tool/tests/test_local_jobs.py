"""Downloaded-job listing for the login screen's 로컬 작업 tab."""

import json
import os

from PyQt5.QtWidgets import QApplication

from labeling_tool.session.local_jobs import list_local_jobs

_app = QApplication.instance() or QApplication([])  # keep a reference alive


def _make_job(root, sid, *, name=None, base="https://srv.example.com",
              photos=3, synced=1, mtime=1_000_000):
    d = root / f"session_{sid}"
    (d / "Labeling").mkdir(parents=True)
    data = {"sessionId": sid, "base": base, "fetchedAt": None,
            "photos": {f"p{i}.jpg": {"filename": f"p{i}.jpg", "timestamp": i,
                                     "photo_id": i, "report_photo_num": i,
                                     "px_per_cm": 1.0, "synced": i < synced}
                       for i in range(photos)}}
    if name is not None:
        data["inspectionName"] = name
    mf = d / "manifest.json"
    mf.write_text(json.dumps(data))
    os.utime(mf, (mtime, mtime))
    return d


def test_lists_jobs_with_counts_server_and_name(tmp_path):
    _make_job(tmp_path, 16, name="B1 주차장", photos=16, synced=3)
    [job] = list_local_jobs(tmp_path)
    assert job.session_id == 16
    assert job.inspection_name == "B1 주차장"
    assert (job.photo_count, job.synced_count) == (16, 3)
    assert job.base == "https://srv.example.com"
    assert job.host == "srv.example.com"


def test_sorted_by_last_modified_including_labeling_edits(tmp_path):
    _make_job(tmp_path, 1, mtime=1_000)
    _make_job(tmp_path, 2, mtime=2_000)
    old = _make_job(tmp_path, 3, mtime=500)
    edit = old / "Labeling" / "p0.png"          # recent edit in an old job
    edit.write_bytes(b"x")
    os.utime(edit, (3_000, 3_000))
    jobs = list_local_jobs(tmp_path)
    assert [j.session_id for j in jobs] == [3, 2, 1]
    assert jobs[0].modified == 3_000


def test_old_manifest_without_name_and_missing_root(tmp_path):
    _make_job(tmp_path, 5)
    assert list_local_jobs(tmp_path)[0].inspection_name is None
    assert list_local_jobs(tmp_path / "nope") == []


def test_skips_non_job_dirs_and_broken_manifests(tmp_path):
    _make_job(tmp_path, 5)
    (tmp_path / "images" / "masks").mkdir(parents=True)     # few-shot dataset
    bad = tmp_path / "session_9"; bad.mkdir()
    (bad / "manifest.json").write_text("{broken")
    (tmp_path / "session_x").mkdir()
    assert [j.session_id for j in list_local_jobs(tmp_path)] == [5]


def test_fetch_dialog_remembers_inspection_names(monkeypatch):
    from labeling_tool.ui.fetch_dialog import FetchDialog
    dlg = FetchDialog(base="https://srv", key="k")
    monkeypatch.setattr(dlg.client, "list_sessions", lambda: [
        {"sessionId": 16, "inspectionName": "B1 주차장", "photoCount": 16},
        {"sessionId": 18, "inspectionName": None},
    ])
    dlg._load_sessions()
    assert dlg._session_names == {16: "B1 주차장"}
