import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


class _Ev:
    def button(self):
        return Qt.LeftButton


def _canvas_with_thick_stroke():
    c = ImageCanvas()
    c.set_image(np.full((40, 60, 3), 100, np.uint8), None, None)
    stroke = np.zeros((40, 60), np.uint8)
    stroke[18:23, 5:55] = 255                 # ~5px-thick horizontal stroke
    c.brush_mask_crack[stroke > 0] = 255       # painted into the live mask
    c._crack_stroke = stroke.copy()
    c.brush_mode = True
    c._brushing = True
    return c


def test_default_thins_stroke_to_centerline():
    c = _canvas_with_thick_stroke()
    before = int((c.brush_mask_crack > 0).sum())
    c.fine_annotation = False
    c.mouseReleaseEvent(_Ev())
    after = int((c.brush_mask_crack > 0).sum())
    assert after < before * 0.5               # collapsed toward a 1px centerline


def test_fine_annotation_keeps_thickness():
    c = _canvas_with_thick_stroke()
    before = int((c.brush_mask_crack > 0).sum())
    c.fine_annotation = True
    c.mouseReleaseEvent(_Ev())
    after = int((c.brush_mask_crack > 0).sum())
    assert after == before                    # no thinning -> width preserved
