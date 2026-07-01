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


def test_undo_removes_last_point_and_repredicts():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.mousePressEvent(_RightClick(40, 40))
    assert c._sam_labels == [1, 0] and c.has_sam_preview()
    assert c.undo_sam_point() is True          # drop the right-click
    assert c._sam_labels == [1]
    assert c.has_sam_preview()                  # still has the first point's preview


def test_undo_last_point_clears_preview():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    assert c.undo_sam_point() is True
    assert c._sam_points == [] and not c.has_sam_preview()   # back to empty
    assert c.undo_sam_point() is False         # nothing left to undo


def test_set_image_conforms_mismatched_mask_to_origin():
    """A loaded mask a few px off from the stitched origin must be conformed to
    the origin size, else SAM/brush/save layers desync."""
    c = ImageCanvas(); c.resize(120, 80)
    origin = np.full((80, 120, 3), 50, np.uint8)
    spall = np.zeros((88, 120), np.uint8)      # 8px taller than origin
    spall[5:10, 5:15] = 255
    c.set_image(origin, None, spall)
    assert c.brush_mask_spalling.shape == (80, 120)
    assert c.brush_mask_crack.shape == (80, 120)


def test_sam_commit_when_loaded_mask_mismatched_origin():
    """Regression: commit_sam boolean-index used to crash with IndexError when
    the loaded spalling mask height != origin height."""
    c = ImageCanvas(); c.resize(120, 80)
    origin = np.full((80, 120, 3), 50, np.uint8)
    spall = np.zeros((88, 120), np.uint8)      # mismatched -> boolean-index mismatch
    c.set_image(origin, None, spall)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    assert c.has_sam_preview()
    assert c.commit_sam() is True              # no IndexError
    assert int((c.brush_mask_spalling > 0).sum()) >= 200


def test_sam_crop_maps_preview_to_full_image(monkeypatch):
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 64)
    c = ImageCanvas(); c.resize(200, 200)
    c.set_image(np.full((200, 200, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(100, 100, 1)                 # image coords; crop centered here
    assert c._sam_crop == (68, 68, 132, 132)      # 64-window around (100,100)
    ys, xs = np.where(c._sam_preview > 0)
    # _FakePredictor puts a block at crop-local [10:20, 10:30]; +offset (68,68)
    assert (int(ys.min()), int(ys.max())) == (78, 87)
    assert (int(xs.min()), int(xs.max())) == (78, 97)
    assert c.commit_sam() is True
    assert int((c.brush_mask_spalling > 0).sum()) == 10 * 20   # placed, not whole image


def test_sam_crop_small_image_uses_whole(monkeypatch):
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 1024)   # image (120x80) < side -> whole
    c = ImageCanvas(); c.resize(120, 80)
    c.set_image(np.full((80, 120, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(60, 40, 1)
    assert c._sam_crop == (0, 0, 120, 80)
    assert c.has_sam_preview()


def test_sam_positive_click_outside_crop_recrops(monkeypatch):
    """A positive click beyond the current crop starts a fresh selection there
    (a fixed crop can't cover the whole panorama)."""
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 64)
    c = ImageCanvas(); c.resize(200, 200)
    c.set_image(np.full((200, 200, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(30, 30, 1)
    assert c._sam_crop == (0, 0, 64, 64)
    c._sam_add_point(150, 150, 1)              # far positive -> re-crop
    assert c._sam_crop == (118, 118, 182, 182)
    assert c._sam_points == [(150, 150)]        # fresh selection, old points dropped
    assert c.has_sam_preview()


def test_sam_click_inside_crop_refines(monkeypatch):
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 64)
    c = ImageCanvas(); c.resize(200, 200)
    c.set_image(np.full((200, 200, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(100, 100, 1)              # crop (68,68,132,132)
    c._sam_add_point(110, 110, 0)              # inside -> refine, same crop
    assert c._sam_crop == (68, 68, 132, 132)
    assert c._sam_points == [(100, 100), (110, 110)]
