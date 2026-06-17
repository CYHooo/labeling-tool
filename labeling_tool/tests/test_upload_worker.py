from pathlib import Path

import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.upload_worker import UploadWorker
from labeling_tool.tests.test_uploader import FakeClient
from labeling_tool.session import naming, mask_store
from labeling_tool.core.bbox import save_bboxes

_app = QApplication.instance() or QApplication([])


def _setup_labeling(tmp_path, ts_list):
    labeling = tmp_path / "Labeling"
    high = tmp_path / "HighLight"
    rep = tmp_path / "Repair15"
    for d in (labeling, high, rep):
        d.mkdir(parents=True, exist_ok=True)
    for ts in ts_list:
        stitched = naming.stitched_filename(ts)
        name = mask_store.mask_name(stitched)            # {stem}_mask.png
        # Labeling mask carries the real crack channel for metrics.
        m = np.zeros((40, 40, 3), np.uint8)
        m[18:23, 5:35, 2] = 255                          # R = crack
        cv2.imwrite(str(labeling / name), m)
        # HighLight + Repair15 just need to exist with valid PNG bytes.
        cv2.imwrite(str(high / name), np.zeros((40, 40), np.uint8))
        cv2.imwrite(str(rep / name), np.zeros((40, 40), np.uint8))
        stem = Path(stitched).stem
        save_bboxes(labeling / f"{stem}.bbox.json", stitched, [], 10.0, "aruco")
    return [{"filename": naming.stitched_filename(ts), "timestamp": ts,
             "px_per_cm": 10.0, "scale_source": "aruco"} for ts in ts_list]


def test_worker_builds_items_and_uploads(tmp_path):
    specs = _setup_labeling(tmp_path, [1, 2])
    client = FakeClient()
    worker = UploadWorker(client, session_id=43, specs=specs,
                          labeling_dir=str(tmp_path / "Labeling"),
                          edit_batch_id="b")
    prepare, upload, results = [], [], []
    worker.progress.connect(
        lambda d, t, ph: (prepare if ph == "prepare" else upload).append((d, t)))
    worker.done.connect(lambda r: results.append(r))
    worker.run()
    assert results and results[0]["uploaded"] == 2
    assert results[0]["batch_id"] == "b"
    assert set(results[0]["timestamps"]) == {1, 2}
    assert prepare[-1] == (2, 2)
    assert upload[-1] == (2, 2)
    assert len(client.puts) == 6                          # 3 PUTs * 2 photos


def test_worker_skips_missing_masks(tmp_path):
    (tmp_path / "Labeling").mkdir()
    specs = [{"filename": naming.stitched_filename(99), "timestamp": 99,
              "px_per_cm": 10.0, "scale_source": "aruco"}]   # no files on disk
    worker = UploadWorker(FakeClient(), session_id=43, specs=specs,
                          labeling_dir=str(tmp_path / "Labeling"),
                          edit_batch_id="b")
    results = []
    worker.done.connect(lambda r: results.append(r))
    worker.run()
    assert results and results[0]["uploaded"] == 0
    assert results[0]["timestamps"] == []
