import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.classes import ClassRegistry, LabelClass
from labeling_tool.session import mask_store
from labeling_tool.ui import upload_worker as UW

_app = QApplication.instance() or QApplication([])


def _prepare(tmp_path, label):
    ldir = tmp_path / "Labeling"; ldir.mkdir()
    (tmp_path / "HighLight").mkdir(); (tmp_path / "Repair15").mkdir()
    name = mask_store.mask_name("stitched_1.jpg")
    for d in ("Labeling", "HighLight", "Repair15"):
        cv2.imwrite(str(tmp_path / d / name), label)
    return ldir


class _Client:
    def __init__(self, listing=None):
        self.listing = listing

    def list_classes(self):
        if self.listing is None:
            raise UW.requests.ConnectionError("down")
        return self.listing


def test_known_classes_get_areas_and_unknown_ones_are_reported(tmp_path):
    label = np.zeros((20, 20), np.uint8)
    label[0:2, 0:2] = 3          # known after sync
    label[5:6, 5:6] = 9          # nobody on the server knows 9
    ldir = _prepare(tmp_path, label)
    listing = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF")]).to_payload()
    worker = UW.UploadWorker(
        _Client(listing), session_id=45,
        specs=[{"filename": "stitched_1.jpg", "timestamp": 1, "px_per_cm": 10.0}],
        labeling_dir=str(ldir), edit_batch_id="b", class_registry=ClassRegistry())
    items, _cache = worker._build_items()
    assert items[0]["classAreas"] == [{"classId": 3, "areaMm2": 4.0, "pixelCount": 4}]
    assert worker.unknown_classes == [9]


class _NoV5Client:
    """A server without the class API (V5): list_classes answers 404."""

    def list_classes(self):
        from labeling_tool.api.errors import ViewerApiError
        raise ViewerApiError("NOT_FOUND", "no class API", 404)


def test_server_without_class_api_uploads_builtins_only(tmp_path):
    label = np.zeros((20, 20), np.uint8)
    label[0:2, 0:2] = 3          # known only to the stale local registry
    ldir = _prepare(tmp_path, label)
    passed = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF")])
    worker = UW.UploadWorker(
        _NoV5Client(), session_id=45,
        specs=[{"filename": "stitched_1.jpg", "timestamp": 1, "px_per_cm": 10.0}],
        labeling_dir=str(ldir), edit_batch_id="b", class_registry=passed)
    items, _cache = worker._build_items()
    assert "classAreas" not in items[0]
    assert worker.unknown_classes == [3]
