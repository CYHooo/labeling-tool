from labeling_tool.session.local_pairing import pair_by_stem, mask_for_stem


def _touch(p):
    p.write_bytes(b"x")


def test_pairs_same_stem_png(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "foo.jpg"); _touch(msk / "foo.png")
    pairs = pair_by_stem(img, msk)
    assert pairs == [("foo.jpg", msk / "foo.png")]


def test_missing_mask_is_none(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "bar.jpg")
    assert pair_by_stem(img, msk) == [("bar.jpg", None)]


def test_png_preferred_and_sorted(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "b.jpg"); _touch(img / "a.jpg")
    _touch(msk / "a.png"); _touch(msk / "a.bmp"); _touch(msk / "b.bmp")
    pairs = pair_by_stem(img, msk)
    assert [n for n, _ in pairs] == ["a.jpg", "b.jpg"]      # sorted
    assert pairs[0][1] == msk / "a.png"                     # png preferred
    assert pairs[1][1] == msk / "b.bmp"


def test_mask_for_stem_none(tmp_path):
    assert mask_for_stem(tmp_path, "nope") is None
