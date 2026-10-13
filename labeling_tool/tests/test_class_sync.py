import pytest
import requests

from labeling_tool.api import class_sync as S
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.core import classes as C

BASE = "https://viewer.example.com"


class _Client:
    def __init__(self, listing=None, error=None, added=None):
        self.listing, self.error, self.added = listing, error, added
        self.calls = []

    def list_classes(self):
        self.calls.append("list")
        if self.error:
            raise self.error
        return self.listing

    def add_class(self, name, color):
        self.calls.append(("add", name, color))
        if self.error:
            raise self.error
        return self.added


_LISTING = {"classes": [
    {"classId": 1, "name": "crack", "kind": "line", "color": "#FF3C3C", "builtin": True},
    {"classId": 2, "name": "spalling", "kind": "area", "color": "#3CE63C", "builtin": True},
    {"classId": 3, "name": "백태", "kind": "area", "color": "#3C8CFF", "builtin": False},
]}


def test_sync_reads_the_server_and_caches_it(tmp_path):
    reg, status = S.sync_classes(_Client(_LISTING), BASE, root=tmp_path)
    assert status == S.SYNC_OK and reg.ids() == [1, 2, 3]
    assert C.load_cached(BASE, root=tmp_path).ids() == [1, 2, 3]


def test_a_server_without_v5_means_builtins_only(tmp_path):
    C.save_cached(BASE, C.ClassRegistry([C.LabelClass(3, "x", "area", "#123456")]), root=tmp_path)
    err = ViewerApiError("HTTP_ERROR", "Not Found", 404)
    reg, status = S.sync_classes(_Client(error=err), BASE, root=tmp_path)
    assert status == S.SYNC_UNSUPPORTED and reg.ids() == [1, 2]


@pytest.mark.parametrize("err", [requests.ConnectionError("down"),
                                 ViewerApiError("S3_ERROR", "boom", 500)])
def test_offline_or_failing_uses_the_cache(tmp_path, err):
    C.save_cached(BASE, C.ClassRegistry([C.LabelClass(3, "x", "area", "#123456")]), root=tmp_path)
    reg, status = S.sync_classes(_Client(error=err), BASE, root=tmp_path)
    assert status == S.SYNC_OFFLINE and reg.ids() == [1, 2, 3]


def test_no_client_uses_the_cache(tmp_path):
    reg, status = S.sync_classes(None, BASE, root=tmp_path)
    assert status == S.SYNC_OFFLINE and reg.ids() == [1, 2]


def test_adding_a_class_updates_and_caches_the_registry(tmp_path):
    added = {"classId": 4, "name": "누수", "kind": "area", "color": "#FFAA00", "builtin": False}
    client = _Client(added=added)
    reg, cls = S.add_class_and_cache(client, BASE, C.ClassRegistry(), "  누수 ", "#FFAA00",
                                     root=tmp_path)
    assert client.calls == [("add", "누수", "#FFAA00")]          # name trimmed
    assert cls.class_id == 4 and reg.ids() == [1, 2, 4]
    assert C.load_cached(BASE, root=tmp_path).ids() == [1, 2, 4]


def test_adding_an_empty_name_is_refused_before_the_network(tmp_path):
    client = _Client()
    with pytest.raises(ValueError):
        S.add_class_and_cache(client, BASE, C.ClassRegistry(), "   ", "#FFAA00", root=tmp_path)
    assert client.calls == []


def test_client_methods_hit_the_v5_v6_urls(monkeypatch):
    from labeling_tool.api.client import ViewerApiClient
    seen = []

    class _Resp:
        ok, status_code = True, 200
        def json(self):
            return {"classes": []}

    c = ViewerApiClient("https://viewer.example.com/", "k")
    monkeypatch.setattr(c._s, "get", lambda url, **kw: seen.append(("GET", url)) or _Resp())
    monkeypatch.setattr(c._s, "post", lambda url, json=None, **kw: seen.append(("POST", url, json)) or _Resp())
    c.list_classes()
    c.add_class("누수", "#FFAA00")
    assert seen == [("GET", "https://viewer.example.com/api/viewer/classes/"),
                    ("POST", "https://viewer.example.com/api/viewer/classes/",
                     {"name": "누수", "color": "#FFAA00"})]
