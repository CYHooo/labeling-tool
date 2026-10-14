import pytest

from labeling_tool.api import edit_fields as F


@pytest.mark.parametrize("value, expected", [
    ("floor", "floor"), ("wall", "wall"), ("ceiling", "ceiling"),
    (None, None), ("slope", None), ("", None), (3, None),
])
def test_normalize_surface(value, expected):
    assert F.normalize_surface(value) == expected


def test_photo_fields_reads_the_three_server_values():
    assert F.photo_fields({"surface": "wall", "tiltDeg": 87.4, "tiltSource": "sensor"}) == {
        "surface": "wall", "tilt_deg": 87.4, "tilt_source": "sensor"}
    assert F.photo_fields({}) == {"surface": None, "tilt_deg": None, "tilt_source": None}
    assert F.photo_fields({"surface": "slope", "tiltDeg": "x"}) == {
        "surface": None, "tilt_deg": None, "tilt_source": None}


@pytest.mark.parametrize("body, expected", [
    ({"deleted": [1, 2]}, [1, 2]),
    ({"deleted": [{"timestamp": 1}, {"timestamp": 2}]}, [1, 2]),
    ({}, []), ({"deleted": None}, []), ({"deleted": "x"}, []), ("oops", []),
])
def test_timestamps_in(body, expected):
    assert F.timestamps_in(body, F.DELETED_KEY) == expected
