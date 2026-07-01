from pathlib import Path
import cv2, numpy as np
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def _setup(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; out = tmp_path / "out"
    img.mkdir(); msk.mkdir()
    cv2.imwrite(str(img / "foo.jpg"), np.full((40, 60, 3), 100, np.uint8))
    label = np.zeros((40, 60), np.uint8); label[5:15, 5:20] = 2   # spalling region
    cv2.imwrite(str(msk / "foo.png"), label)
    return img, msk, out


def test_lists_paired_and_loads(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(img, msk, out)
    assert w.image_files == ["foo.jpg"]
    w._show_image(0)
    assert w.canvas.brush_mask_spalling is not None
    assert int((w.canvas.brush_mask_spalling > 0).sum()) == 10 * 15   # loaded mask


def test_save_writes_output_png(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    from labeling_tool.core.mask_codec import decode_mask
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(img, msk, out)
    w._show_image(0)
    w._save_all_artifacts(silent=True)
    saved = out / "foo.png"
    assert saved.exists()
    raw = cv2.imread(str(saved), cv2.IMREAD_UNCHANGED)
    crack, spall = decode_mask(raw, mask_path=str(saved))
    assert int((spall > 0).sum()) == 10 * 15         # round-trips spalling
    # no derived/result dirs were created
    assert not (out.parent / "HighLight").exists()
    assert not (out.parent / "Repair15").exists()
