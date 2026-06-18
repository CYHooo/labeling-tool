import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


class _FakePredictor:
    """Returns a fixed block mask; records that set_image ran once."""
    def __init__(self):
        self.set_image_calls = 0
        self.last_points = None

    def set_image(self, bgr):
        self.set_image_calls += 1
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        self.last_points = (list(points), list(labels))
        h, w = self._hw
        m = np.zeros((h, w), np.uint8)
        m[10:20, 10:30] = 255
        return m


class _LeftClick:
    def __init__(self, x, y):
        self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y
    def button(self): return Qt.LeftButton
    def modifiers(self): return Qt.NoModifier


class _RightClick(_LeftClick):
    def button(self): return Qt.RightButton


def _canvas():
    c = ImageCanvas()
    c.resize(120, 80)
    c.set_image(np.full((80, 120, 3), 50, np.uint8), None, None)
    return c


def test_sam_first_click_sets_image_then_predicts():
    c = _canvas()
    pred = _FakePredictor()
    c.set_sam_predictor(pred)
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))     # image coords ~ widget coords here
    assert pred.set_image_calls == 1          # lazy encode on first click
    assert c.has_sam_preview()
    assert c._sam_labels[-1] == 1             # left = foreground


def test_sam_right_click_is_background_point():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.mousePressEvent(_RightClick(40, 40))
    assert c._sam_labels == [1, 0]
    assert c._sam_predictor.set_image_calls == 1   # not re-encoded on 2nd click


def test_commit_writes_into_spalling_only():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    edited = []
    c.mask_edited.connect(lambda: edited.append(1))
    ok = c.commit_sam()
    assert ok
    assert int((c.brush_mask_spalling > 0).sum()) == 10 * 20   # the block
    assert int((c.brush_mask_crack > 0).sum()) == 0            # crack untouched
    assert not c.has_sam_preview()                             # cleared after commit
    assert edited                                              # mask_edited emitted


def test_cancel_clears_without_writing():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.cancel_sam()
    assert not c.has_sam_preview()
    assert int((c.brush_mask_spalling > 0).sum()) == 0


def test_image_switch_clears_sam_state():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.set_image(np.full((80, 120, 3), 70, np.uint8), None, None)
    assert not c.has_sam_preview()
    assert c._sam_points == [] and c._sam_image_set is False


def test_sam_noop_without_predictor():
    c = _canvas()                              # no predictor injected
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))      # must not raise
    assert not c.has_sam_preview()
