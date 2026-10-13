import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas
from labeling_tool.core.classes import ClassRegistry, LabelClass

_app = QApplication.instance() or QApplication([])
REG = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF"),
                     LabelClass(4, "누수", "area", "#FFAA00")])


class _Event:
    def __init__(self, x, y, button=Qt.LeftButton):
        self._x, self._y, self._b = x, y, button
    def x(self): return self._x
    def y(self): return self._y
    def button(self): return self._b
    def modifiers(self): return Qt.NoModifier


class _Predictor:
    def set_image(self, bgr):
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        m = np.zeros(self._hw, np.uint8)
        m[:, :] = 255
        return m


def _canvas(layers=None):
    c = ImageCanvas()
    c.resize(100, 100)
    c.set_class_registry(REG)
    c.set_image_layers(np.zeros((100, 100, 3), np.uint8), layers or {})
    return c


def _stroke(c, x0, y0, x1, y1, button=Qt.LeftButton):
    wx0, wy0 = c.viewport.image_to_widget(x0, y0)
    wx1, wy1 = c.viewport.image_to_widget(x1, y1)
    c.mousePressEvent(_Event(wx0, wy0, button))
    c.mouseMoveEvent(_Event(wx1, wy1, button))
    c.mouseReleaseEvent(_Event(wx1, wy1, button))


def test_layers_always_hold_crack_and_spalling():
    c = _canvas()
    assert sorted(c.layers) == [1, 2]
    assert c.brush_mask_crack is c.layers[1] and c.brush_mask_spalling is c.layers[2]


def test_loaded_user_class_layers_are_kept():
    lay = np.zeros((100, 100), np.uint8); lay[0:5, 0:5] = 255
    c = _canvas({3: lay, 9: lay.copy()})
    assert sorted(c.layers) == [1, 2, 3, 9]


def test_the_brush_paints_the_current_user_class():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    assert c.layers[3].any() and not c.layers[2].any() and not c.layers[1].any()


def test_painting_an_area_class_clears_other_area_classes_there():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    c.current_class_id = 2
    _stroke(c, 20, 50, 80, 50)
    assert c.layers[2].any() and not c.layers[3][50, 50]


def test_area_painting_leaves_crack_alone():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 1
    _stroke(c, 10, 50, 90, 50)
    crack = c.layers[1].copy()
    c.current_class_id = 3
    _stroke(c, 10, 50, 90, 50)
    assert (c.layers[1] == crack).all()


def test_sam_commits_into_the_current_area_class_and_clears_others():
    c = _canvas()
    c.layers[2][:, :] = 255
    c.set_sam_predictor(_Predictor())
    c.set_sam_mode(True)
    c.current_class_id = 4
    c._sam_add_point(50, 50, 1)
    assert c.commit_sam()
    assert c.layers[4][50, 50] == 255 and c.layers[2][50, 50] == 0


def test_sam_never_writes_crack():
    c = _canvas()
    c.set_sam_predictor(_Predictor())
    c.set_sam_mode(True)
    c.current_class_id = 1
    c._sam_add_point(50, 50, 1)
    assert c.commit_sam()
    assert not c.layers[1].any() and c.layers[2][50, 50] == 255


def test_undo_restores_a_user_class_stroke():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    assert c.undo() and not c.layers[3].any()
    assert c.redo() and c.layers[3].any()


def test_undo_after_reset_brings_a_user_class_back():
    c = _canvas()
    c.brush_mode = True
    c.current_class_id = 3
    _stroke(c, 20, 50, 80, 50)
    drawn = c.layers[3].copy()
    before = c.snapshot()
    c.set_image_layers(np.zeros((100, 100, 3), np.uint8), {})    # 복원: no class 3
    c.record_external_change(before)
    assert not c.layers[3].any()
    assert c.undo()
    assert (c.layers[3] == drawn).all()


def test_current_category_compat_property():
    c = _canvas()
    c.current_category = "spalling"
    assert c.current_class_id == 2 and c.current_category == "spalling"
    c.current_category = "crack"
    assert c.current_class_id == 1
