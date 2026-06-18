from labeling_tool.ui.fetch_dialog import filter_photos_by_range


def _photos(n):
    return [{"reportPhotoNum": i, "timestamp": 1000 + i} for i in range(1, n + 1)]


def _nums(ps):
    return [p["reportPhotoNum"] for p in ps]


def test_both_zero_returns_all():
    assert _nums(filter_photos_by_range(_photos(16), 0, 0)) == list(range(1, 17))


def test_full_range():
    assert _nums(filter_photos_by_range(_photos(16), 5, 15)) == list(range(5, 16))


def test_to_only_is_first_n():
    assert _nums(filter_photos_by_range(_photos(16), 0, 5)) == [1, 2, 3, 4, 5]


def test_from_only_is_to_end():
    assert _nums(filter_photos_by_range(_photos(16), 12, 0)) == [12, 13, 14, 15, 16]


def test_range_out_of_bounds_is_empty():
    assert filter_photos_by_range(_photos(16), 50, 60) == []
