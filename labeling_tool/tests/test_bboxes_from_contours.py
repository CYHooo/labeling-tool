import numpy as np

from labeling_tool.core.bbox import bboxes_from_contours
from labeling_tool.core.bbox.oriented_box import OrientedBox


def _rect_contour(x0, y0, w, h):
    return np.array([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]],
                    dtype=np.int32)


def test_one_contour_one_box():
    boxes = bboxes_from_contours([_rect_contour(0, 0, 100, 50)])
    assert len(boxes) == 1
    b = boxes[0]
    assert isinstance(b, OrientedBox)
    assert abs(b.w * b.h - 100 * 50) / (100 * 50) < 0.05   # area ~ contour
    assert abs(b.cx - 50) < 2 and abs(b.cy - 25) < 2        # center


def test_multiple_contours():
    boxes = bboxes_from_contours([_rect_contour(0, 0, 40, 40),
                                  _rect_contour(200, 200, 60, 30)])
    assert len(boxes) == 2


def test_degenerate_contours_skipped():
    assert bboxes_from_contours([np.array([[0, 0], [10, 10]], np.int32)]) == []  # <3 pts
    assert bboxes_from_contours([]) == []
    assert bboxes_from_contours(None) == []


def test_tiny_area_skipped():
    assert bboxes_from_contours([_rect_contour(0, 0, 1, 1)], min_area_px=10.0) == []
