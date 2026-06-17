import time
import numpy as np
import cv2

from labeling_tool.session import mask_store


def test_naming():
    assert mask_store.mask_name("stitched_123.jpg") == "stitched_123_mask.png"
    assert mask_store.bbox_name("stitched_123.jpg") == "stitched_123.bbox.json"


def _touch(p, mtime=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))


def test_resolve_labeling_wins(tmp_path):
    lab, reb, det = tmp_path / "L", tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(lab / name); _touch(reb / name); _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=lab, rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "labeling" and path == lab / name


def test_resolve_fresh_rebuilt(tmp_path):
    reb, det = tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(det / name, mtime=1000)
    _touch(reb / name, mtime=2000)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "rebuilt" and path == reb / name


def test_resolve_stale_rebuilt_needs_rebuild(tmp_path):
    reb, det = tmp_path / "R", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(reb / name, mtime=1000)
    _touch(det / name, mtime=2000)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=reb, detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "needs_rebuild" and path is None


def test_resolve_nothing(tmp_path):
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", rebuilt_dir=tmp_path / "R",
        detected_dir=tmp_path / "D", origin_filename="stitched_1.jpg")
    assert src == "needs_rebuild" and path is None


def test_build_rebuilt_label_refines_crack_and_keeps_spalling():
    origin = np.full((80, 200, 3), 30, np.uint8)
    origin[38:43, 10:190] = 20
    coarse = np.zeros((80, 200, 3), np.uint8)
    coarse[38:43, 10:190, 2] = 255      # R = crack
    coarse[10:25, 10:60, 1] = 255       # G = spalling
    label = mask_store.build_rebuilt_label_mask(origin, coarse)
    assert label.ndim == 2
    assert int((label == 1).sum()) > 0      # crack
    assert int((label == 2).sum()) > 0      # spalling


def test_build_rebuilt_label_resizes_spalling_to_guided():
    origin = np.full((60, 120, 3), 30, np.uint8)
    coarse = np.zeros((30, 60, 3), np.uint8)
    coarse[10:20, 5:55, 1] = 255
    label = mask_store.build_rebuilt_label_mask(origin, coarse)
    assert label.shape[:2] == origin.shape[:2]
    assert int((label == 2).sum()) > 0
