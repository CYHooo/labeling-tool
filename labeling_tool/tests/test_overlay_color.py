import numpy as np
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.viewport import Viewport
from labeling_tool.core.canvas.overlay_painter import paint_single_color_overlay

_app = QApplication.instance() or QApplication([])


def test_single_color_overlay_renders_yellow():
    w = h = 20
    mask = np.zeros((h, w), np.uint8)
    mask[5:15, 5:15] = 255                      # a covered block

    target = QImage(w, h, QImage.Format_RGBA8888)
    target.fill(0)                              # transparent
    painter = QPainter(target)
    vp = Viewport()
    vp.set_image_size(w, h)
    vp.scale = 1.0
    vp.offset = QPoint(0, 0)
    paint_single_color_overlay(painter, vp, w, h, mask, (255, 255, 0), alpha=255)
    painter.end()

    c = target.pixelColor(10, 10)               # inside the covered block
    assert (c.red(), c.green(), c.blue()) == (255, 255, 0)   # YELLOW, not cyan


def test_compute_highlight_halo_excludes_original_mask():
    import numpy as np
    from labeling_tool.core.canvas.overlay_painter import compute_highlight_halo
    highlight = np.zeros((9, 9), np.uint8); highlight[2:7, 2:7] = 1   # 5x5 dilated
    crack = np.zeros((9, 9), np.uint8); crack[3:6, 3:6] = 255          # 3x3 original
    halo = compute_highlight_halo(highlight, crack, None)
    assert set(np.unique(halo)).issubset({0, 255})
    assert halo[3, 3] == 0          # original mask pixel -> NOT in halo
    assert halo[2, 2] == 255        # ring pixel (dilated, outside mask) -> halo
    assert compute_highlight_halo(None, crack, None) is None
