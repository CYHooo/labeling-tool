from labeling_tool.core.sam.predictor import crop_window, SAM_CROP_PX


def test_default_side_is_1024():
    assert SAM_CROP_PX == 1024


def test_centered_window():
    assert crop_window(2000, 2000, 1000, 1000, 64) == (968, 968, 1032, 1032)


def test_clamp_top_left():
    assert crop_window(2000, 2000, 10, 10, 64) == (0, 0, 64, 64)


def test_clamp_bottom_right():
    assert crop_window(2000, 2000, 1995, 1995, 64) == (1936, 1936, 2000, 2000)


def test_small_image_returns_whole():
    # image (h=50, w=40) smaller than side -> whole image
    assert crop_window(50, 40, 20, 20, 64) == (0, 0, 40, 50)


def test_non_square_image():
    x0, y0, x1, y1 = crop_window(3000, 5000, 2500, 1500, 1024)
    assert (x1 - x0, y1 - y0) == (1024, 1024)
    assert 0 <= x0 and x1 <= 5000 and 0 <= y0 and y1 <= 3000
