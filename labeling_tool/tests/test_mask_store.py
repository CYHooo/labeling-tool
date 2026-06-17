from labeling_tool.session import mask_store


def test_naming():
    assert mask_store.mask_name("stitched_123.jpg") == "stitched_123_mask.png"
    assert mask_store.bbox_name("stitched_123.jpg") == "stitched_123.bbox.json"


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_resolve_labeling_wins(tmp_path):
    lab, det = tmp_path / "L", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(lab / name); _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=lab, detected_dir=det, origin_filename="stitched_1.jpg")
    assert src == "labeling" and path == lab / name


def test_resolve_detected_when_no_labeling(tmp_path):
    det = tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "detected" and path == det / name


def test_resolve_none(tmp_path):
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", detected_dir=tmp_path / "D",
        origin_filename="stitched_1.jpg")
    assert src == "none" and path is None
