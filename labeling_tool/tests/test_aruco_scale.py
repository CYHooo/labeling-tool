from labeling_tool.core.bbox.aruco_scale import (
    MARKER_PHYSICAL_CM, scale_from_two_points,
)


def test_marker_physical_size_is_7cm():
    assert MARKER_PHYSICAL_CM == 7.0


def test_scale_from_two_points_horizontal():
    # 70 px over a 7 cm reference -> 10 px/cm
    assert scale_from_two_points((10, 5), (80, 5), 7.0) == 10.0


def test_scale_from_two_points_diagonal():
    # 3-4-5 triangle: 30,40 -> 50 px over 5 cm -> 10 px/cm
    assert scale_from_two_points((0, 0), (30, 40), 5.0) == 10.0


def test_scale_from_two_points_rejects_bad_length():
    assert scale_from_two_points((0, 0), (70, 0), 0) is None
    assert scale_from_two_points((0, 0), (70, 0), -1) is None


def test_scale_from_two_points_rejects_zero_distance():
    assert scale_from_two_points((5, 5), (5, 5), 7.0) is None
