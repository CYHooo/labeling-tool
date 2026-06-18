from labeling_tool.core.bbox.oriented_box import OrientedBox, union_area_px2


def test_empty_is_zero():
    assert union_area_px2([]) == 0.0


def test_single_box_matches_area():
    b = OrientedBox(cx=100, cy=100, w=100, h=80, angle_deg=0)   # 8000 px^2
    assert abs(union_area_px2([b]) - 8000.0) / 8000.0 < 0.05


def test_disjoint_boxes_are_summed():
    a = OrientedBox(cx=50, cy=50, w=100, h=100, angle_deg=0)
    b = OrientedBox(cx=400, cy=400, w=100, h=100, angle_deg=0)  # far apart
    u = union_area_px2([a, b])
    assert abs(u - 20000.0) / 20000.0 < 0.05                    # ~ sum, no overlap


def test_overlap_counted_once():
    a = OrientedBox(cx=50, cy=50, w=100, h=100, angle_deg=0)    # x[0,100] y[0,100]
    b = OrientedBox(cx=100, cy=100, w=100, h=100, angle_deg=0)  # x[50,150] y[50,150]
    u = union_area_px2([a, b])
    assert u < 20000.0                                          # less than the sum
    assert abs(u - 17500.0) / 17500.0 < 0.05                    # union = 20000 - 2500


def test_identical_boxes_count_once():
    a = OrientedBox(cx=100, cy=100, w=80, h=80, angle_deg=0)
    u_one = union_area_px2([a])
    u_two = union_area_px2([a, OrientedBox(cx=100, cy=100, w=80, h=80, angle_deg=0)])
    assert abs(u_two - u_one) / u_one < 0.02                    # duplicate adds ~nothing
