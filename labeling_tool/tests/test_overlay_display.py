import numpy as np

from labeling_tool.core.canvas.overlay_painter import _screen_thicken


def test_screen_thicken_widens_thin_line():
    img = np.zeros((30, 30), dtype=np.uint8)
    img[15, 5:25] = 255                    # 1px line
    out = _screen_thicken(img, 3)
    assert int((out > 0).sum()) > int((img > 0).sum())
    assert int((out[:, 15] > 0).sum()) >= 2   # thicker on screen


def test_screen_thicken_is_noop_for_1px_target():
    img = np.zeros((10, 10), dtype=np.uint8)
    img[5, 2:8] = 255
    out = _screen_thicken(img, 1)
    assert np.array_equal(out, img)        # r=0 -> input returned unchanged


def test_screen_thicken_does_not_mutate_input():
    img = np.zeros((20, 20), dtype=np.uint8)
    img[10, 3:17] = 255
    original = img.copy()
    _screen_thicken(img, 3)
    assert np.array_equal(img, original)
