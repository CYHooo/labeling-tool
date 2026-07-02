from pathlib import Path
import cv2, numpy as np
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def _setup(tmp_path):
    """Create img/ + msk/ folders with one paired foo image+mask. Output goes to
    tmp_path/Labeling (beside the image folder)."""
    img = tmp_path / "img"; msk = tmp_path / "msk"
    img.mkdir(); msk.mkdir()
    cv2.imwrite(str(img / "foo.jpg"), np.full((40, 60, 3), 100, np.uint8))
    label = np.zeros((40, 60), np.uint8); label[5:15, 5:20] = 2   # spalling region
    cv2.imwrite(str(msk / "foo.png"), label)
    return img, msk, tmp_path / "Labeling"     # output = <image parent>/Labeling


def _open(w, img, msk):
    """Simulate the in-GUI folder selection (what the buttons do)."""
    w.origin_dir = Path(img)
    w.detected_dir = Path(msk)
    w._sync_output_dir()
    w._reload_data()


def test_starts_empty_without_folders():
    from labeling_tool.ui.local_main_window import LocalMainWindow
    w = LocalMainWindow()                       # no args, no startup dialog
    assert w.image_files == []                  # nothing until folders picked
    assert w.origin_dir is None and w.output_dir is None


def test_lists_paired_and_loads(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(); _open(w, img, msk)
    assert w.image_files == ["foo.jpg"]
    assert w.output_dir == out                  # Labeling beside image folder
    w._show_image(0)
    assert int((w.canvas.brush_mask_spalling > 0).sum()) == 10 * 15   # loaded mask


def test_save_writes_output_png(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    from labeling_tool.core.mask_codec import decode_mask
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(); _open(w, img, msk)
    w._show_image(0)
    w._save_all_artifacts(silent=True)
    saved = out / "foo.png"
    assert saved.exists()
    raw = cv2.imread(str(saved), cv2.IMREAD_UNCHANGED)
    crack, spall = decode_mask(raw, mask_path=str(saved))
    assert int((spall > 0).sum()) == 10 * 15         # round-trips spalling
    assert not (out.parent / "HighLight").exists()
    assert not (out.parent / "Repair15").exists()


def test_construct_survives_cwd_origin(tmp_path, monkeypatch):
    """Regression: base ctor auto-loads when a ./Origin exists in CWD; the
    overridden _build_image_list must guard the not-yet-picked folders."""
    from labeling_tool.ui.local_main_window import LocalMainWindow
    (tmp_path / "Origin").mkdir()          # trigger the base auto-load path
    monkeypatch.chdir(tmp_path)
    w = LocalMainWindow()                  # must not raise
    assert w.image_files == []


def test_no_derived_or_autobbox_even_with_scale(tmp_path):
    """15cm/highlight fully disabled: derived dispatch + auto-bbox are no-ops,
    no HighLight/Repair15 dirs, repair15 overlay off."""
    from labeling_tool.ui.local_main_window import LocalMainWindow
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(); _open(w, img, msk)
    w._show_image(0)
    w.current_scale = 20.0                 # a scale is present (manual/aruco)
    w._dispatch_derived("foo.jpg", None, None, 20.0)   # no-op, no raise
    w._maybe_auto_bbox("foo.jpg")                       # no-op
    w._save_all_artifacts(silent=True)
    assert not (out.parent / "HighLight").exists()
    assert not (out.parent / "Repair15").exists()
    assert w.canvas.show_repair15 is False
    assert w._has_labeling_file("foo.jpg") is True      # green marker works
