import pytest

from labeling_tool.session import photo_edits as E
from labeling_tool.session.manifest import PhotoEntry


def _e(ts=1, surface=None, **kw):
    return PhotoEntry(filename=f"{ts}.jpg", timestamp=ts, photo_id=ts,
                      report_photo_num=ts, px_per_cm=2.0, surface=surface, **kw)


def test_shown_surface_prefers_the_local_edit():
    assert E.shown_surface(_e(surface="wall")) == "wall"
    assert E.shown_surface(_e(surface="wall", surface_edit="floor")) == "floor"
    assert E.shown_surface(_e(surface="slope")) is None


def test_set_surface_and_set_back_to_the_server_value():
    e = _e(surface="wall")
    assert E.set_surface(e, "floor") is True and e.surface_edit == "floor"
    assert E.set_surface(e, "floor") is False
    assert E.set_surface(e, "wall") is True and e.surface_edit is None


def test_set_surface_on_an_unknown_server_value_is_an_edit():
    e = _e(surface=None)
    assert E.set_surface(e, "ceiling") and e.surface_edit == "ceiling"


def test_set_surface_rejects_unknown_values():
    with pytest.raises(ValueError):
        E.set_surface(_e(), "slope")


def test_toggle_delete_and_pending():
    e = _e()
    assert not E.has_pending_edit(e)
    assert E.toggle_delete(e) is True and E.has_pending_edit(e)
    assert E.toggle_delete(e) is False and not E.has_pending_edit(e)


def test_upload_lists_skip_deleted_photos_and_sort():
    a = _e(3, surface="wall", surface_edit="floor")
    b = _e(1, surface="wall", surface_edit="ceiling", delete_pending=True)
    c = _e(2, delete_pending=True)
    assert E.surface_updates([a, b, c]) == [{"timestamp": 3, "surface": "floor"}]
    assert E.deletes([a, b, c]) == [{"timestamp": 1}, {"timestamp": 2}]
