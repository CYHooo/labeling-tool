from labeling_tool.core.bbox.io import save_bboxes, load_scale


def test_load_scale_roundtrip(tmp_path):
    path = tmp_path / "a.bbox.json"
    save_bboxes(path, "stitched_1.jpg", [], scale_px_per_cm=45.2,
                scale_source="aruco")
    assert load_scale(path) == 45.2


def test_load_scale_missing_file(tmp_path):
    assert load_scale(tmp_path / "nope.json") is None


def test_load_scale_none_or_zero(tmp_path):
    p1 = tmp_path / "none.bbox.json"
    save_bboxes(p1, "x.jpg", [], scale_px_per_cm=None, scale_source="none")
    assert load_scale(p1) is None

    p2 = tmp_path / "zero.bbox.json"
    save_bboxes(p2, "x.jpg", [], scale_px_per_cm=0.0, scale_source="none")
    assert load_scale(p2) is None
