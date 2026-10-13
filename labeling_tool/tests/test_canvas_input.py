"""Clicks outside the photo, and dragging the view with the middle button
(any tool) or the left button (보기 only)."""
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


class _Event:
    def __init__(self, x, y, button=Qt.LeftButton, modifiers=Qt.NoModifier):
        self._x, self._y, self._b, self._m = x, y, button, modifiers
    def x(self): return self._x
    def y(self): return self._y
    def button(self): return self._b
    def modifiers(self): return self._m


class _Predictor:
    def set_image(self, bgr):
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        m = np.zeros(self._hw, np.uint8)
        m[1:4, 1:4] = 255
        return m


def _canvas():
    c = ImageCanvas()
    c.resize(400, 200)                       # wider than the photo: margins left/right
    c.set_image(np.full((100, 100, 3), 50, np.uint8), None, None)
    return c


def _outside(c):
    """A widget point left of the photo."""
    x0 = c.viewport.offset.x()
    assert x0 > 10
    return 3, c.height() // 2


def _inside(c):
    return c.width() // 2, c.height() // 2


def test_sam_ignores_clicks_outside_the_photo():
    c = _canvas()
    c.set_sam_predictor(_Predictor())
    c.set_sam_mode(True)
    for button in (Qt.LeftButton, Qt.RightButton):
        c.mousePressEvent(_Event(*_outside(c), button))
    assert c._sam_points == [] and not c.can_undo_sam_point()
    c.mousePressEvent(_Event(*_inside(c)))
    assert len(c._sam_points) == 1


def test_repair_area_ignores_new_points_outside_the_photo():
    c = _canvas()
    c.set_bbox_mode(True)
    c.mousePressEvent(_Event(*_outside(c)))
    assert c.bbox_interaction.in_progress_clicks == []
    c.mousePressEvent(_Event(*_inside(c)))
    assert len(c.bbox_interaction.in_progress_clicks) == 1


def test_measuring_ignores_points_outside_the_photo():
    c = _canvas()
    c.set_measure_mode(True)
    c.mousePressEvent(_Event(*_outside(c)))
    assert c.measure_points() == []


def _drag(c, button, dx=40, dy=25, modifiers=Qt.NoModifier):
    x, y = _inside(c)
    before = c.viewport.offset.x(), c.viewport.offset.y()
    c.mousePressEvent(_Event(x, y, button, modifiers))
    c.mouseMoveEvent(_Event(x + dx, y + dy, button, modifiers))
    c.mouseReleaseEvent(_Event(x + dx, y + dy, button, modifiers))
    after = c.viewport.offset.x(), c.viewport.offset.y()
    return after[0] - before[0], after[1] - before[1]


def test_middle_drag_moves_the_view_in_every_tool():
    for setup in (lambda c: None, lambda c: setattr(c, "brush_mode", True),
                  lambda c: c.set_sam_mode(True), lambda c: c.set_bbox_mode(True),
                  lambda c: c.set_measure_mode(True)):
        c = _canvas()
        c.set_sam_predictor(_Predictor())
        setup(c)
        crack = c.brush_mask_crack.copy()
        assert _drag(c, Qt.MiddleButton) == (40, 25)
        assert not c._panning
        assert (c.brush_mask_crack == crack).all()        # nothing drawn
        assert c._sam_points == []
        assert c.bbox_interaction.in_progress_clicks == []


def test_left_drag_moves_the_view_only_in_view_mode():
    c = _canvas()
    assert _drag(c, Qt.LeftButton) == (40, 25)
    assert not c._panning
    c = _canvas()
    c.brush_mode = True
    assert _drag(c, Qt.LeftButton) == (0, 0)               # the brush draws instead
    assert c.brush_mask_crack.any()


def test_ctrl_left_drag_still_moves_the_view():
    c = _canvas()
    c.brush_mode = True
    assert _drag(c, Qt.LeftButton, modifiers=Qt.ControlModifier) == (40, 25)
    assert not c.brush_mask_crack.any()


def test_a_middle_press_during_a_box_drag_does_not_leave_it_stuck():
    c = _canvas()
    c.set_bbox_mode(True)
    c.set_bbox_padding_px(2.0)
    b = c.bbox_interaction
    b.on_left_press(30, 30); b.on_left_press(70, 70)
    assert b.commit(2.0)
    b.selected_idx = None
    x, y = c.viewport.image_to_widget(50, 50)
    c.mousePressEvent(_Event(x, y))                       # grab the box body
    assert b.dragging == "body"
    c.mousePressEvent(_Event(x, y, Qt.MiddleButton))      # ignored mid-drag
    assert not c._panning
    c.mouseReleaseEvent(_Event(x + 5, y, Qt.LeftButton))
    assert b.dragging is None
    c.mouseReleaseEvent(_Event(x + 5, y, Qt.MiddleButton))


def test_another_button_released_mid_stroke_keeps_the_stroke_going():
    c = _canvas()
    c.brush_mode = True
    x, y = _inside(c)
    c.mousePressEvent(_Event(x, y))
    c.mousePressEvent(_Event(x, y, Qt.RightButton))       # ignored
    c.mouseReleaseEvent(_Event(x, y, Qt.RightButton))     # must not end the stroke
    assert c._brushing
    c.mouseMoveEvent(_Event(x + 20, y))
    c.mouseReleaseEvent(_Event(x + 20, y))
    assert not c._brushing
    assert c.can_undo()


def test_panning_while_measuring_gives_the_cross_cursor_back():
    c = _canvas()
    c.set_measure_mode(True)
    _drag(c, Qt.MiddleButton)
    assert c.cursor().shape() == Qt.CrossCursor
