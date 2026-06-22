from pathlib import Path

from labeling_tool.core.bbox.io import save_bboxes, load_scale_info, load_scale
from labeling_tool.core.bbox.oriented_box import OrientedBox


def test_manual_scale_and_points_roundtrip(tmp_path):
    p = tmp_path / "img.bbox.json"
    save_bboxes(p, "img.jpg", [OrientedBox(cx=1, cy=2, w=3, h=4, angle_deg=0)],
                52.3, "manual", scale_points=[(10.0, 20.0), (110.0, 25.0)])
    info = load_scale_info(p)
    assert info["source"] == "manual"
    assert abs(info["scale"] - 52.3) < 1e-9
    assert info["points"] == [(10.0, 20.0), (110.0, 25.0)]
    assert abs(load_scale(p) - 52.3) < 1e-9   # upload path still works


def test_aruco_scale_has_no_points(tmp_path):
    p = tmp_path / "a.bbox.json"
    save_bboxes(p, "a.jpg", [], 40.0, "aruco")     # scale_points omitted
    info = load_scale_info(p)
    assert info["source"] == "aruco"
    assert info["points"] == []
    assert abs(info["scale"] - 40.0) < 1e-9


def test_load_scale_info_missing_file(tmp_path):
    info = load_scale_info(tmp_path / "nope.json")
    assert info == {"scale": None, "source": "none", "points": []}


def test_load_scale_info_zero_scale_is_none(tmp_path):
    p = tmp_path / "z.bbox.json"
    save_bboxes(p, "z.jpg", [], 0.0, "none")
    assert load_scale_info(p)["scale"] is None
