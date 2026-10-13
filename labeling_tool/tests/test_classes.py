import json

import pytest

from labeling_tool.core import classes as C


def _user(cid, name="백태", color="#3C8CFF"):
    return C.LabelClass(cid, name, "area", color)


def test_builtins_are_always_there_in_id_order():
    reg = C.ClassRegistry([_user(4, "누수"), _user(3)])
    assert reg.ids() == [1, 2, 3, 4]
    assert reg.get(1).kind == "line" and reg.get(2).kind == "area"
    assert reg.get(1).builtin and not reg.get(3).builtin


def test_a_server_entry_cannot_replace_a_builtin():
    reg = C.ClassRegistry([C.LabelClass(1, "hack", "area", "#000000")])
    assert reg.get(1).name == "crack" and reg.get(1).kind == "line"


def test_ids_outside_3_to_254_are_ignored():
    reg = C.ClassRegistry([_user(0), _user(255), _user(300), _user(3)])
    assert reg.ids() == [1, 2, 3]


def test_display_names():
    tr = {"cat_crack": "균열", "cat_spalling": "박리"}
    reg = C.ClassRegistry([_user(3, "백태")])

    def fake_tr(key, **kw):
        return tr.get(key, f"{key}:{kw}")
    assert reg.display_name(1, fake_tr) == "균열"
    assert reg.display_name(2, fake_tr) == "박리"
    assert reg.display_name(3, fake_tr) == "백태"
    assert reg.display_name(7, fake_tr) == "class_unknown:{'id': 7}"


def test_colours_and_kinds_for_unknown_ids():
    reg = C.ClassRegistry()
    assert reg.rgb(1) == (255, 60, 60)
    assert reg.rgb(9) == C.UNKNOWN_RGB
    assert reg.is_area(2) and not reg.is_area(1)
    assert reg.is_area(9)                       # unknown pixels behave like an area


def test_parse_classes_skips_bad_entries():
    reg = C.parse_classes({"classes": [
        {"classId": 1, "name": "crack", "kind": "line", "color": "#FF3C3C", "builtin": True},
        {"classId": 3, "name": " 백태 ", "kind": "area", "color": "#3c8cff"},
        {"classId": "x", "name": "bad"},
        {"classId": 4, "name": "", "kind": "area", "color": "#123456"},
        {"classId": 5, "name": "누수", "kind": "area", "color": "red"},
    ]})
    assert reg.ids() == [1, 2, 3, 5]
    assert reg.get(3).name == "백태" and reg.get(3).color == "#3C8CFF"
    assert reg.get(5).color.startswith("#") and len(reg.get(5).color) == 7


def test_cache_round_trip_is_per_server(tmp_path):
    reg = C.ClassRegistry([_user(3)])
    C.save_cached("https://a.example.com", reg, root=tmp_path)
    assert C.load_cached("https://a.example.com/", root=tmp_path).ids() == [1, 2, 3]
    assert C.load_cached("https://b.example.com", root=tmp_path).ids() == [1, 2]


def test_a_broken_cache_gives_the_builtins(tmp_path):
    path = C.cache_file("https://a.example.com", root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert C.load_cached("https://a.example.com", root=tmp_path).ids() == [1, 2]
    assert path.read_text(encoding="utf-8") == "{not json"   # left alone


def test_pick_color_avoids_colours_in_use():
    reg = C.ClassRegistry([_user(3, color=C.PALETTE[0])])
    assert C.pick_color(reg) == C.PALETTE[1]
    many = C.ClassRegistry([_user(3 + i, f"c{i}", c) for i, c in enumerate(C.PALETTE)])
    extra = C.pick_color(many)
    assert extra not in C.PALETTE and extra.startswith("#") and len(extra) == 7


def test_with_class_returns_a_new_registry():
    reg = C.ClassRegistry()
    reg2 = reg.with_class(_user(3))
    assert reg.ids() == [1, 2] and reg2.ids() == [1, 2, 3]


def test_tests_never_write_the_cache_into_the_repo():
    from labeling_tool.core.app_paths import REPO_ROOT
    assert REPO_ROOT not in C.cache_dir().parents


@pytest.mark.parametrize("content", ["[1]", '{"classes": 5}'])
def test_a_cache_of_the_wrong_shape_gives_the_builtins(tmp_path, content):
    path = C.cache_file("https://a.example.com", root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    assert C.load_cached("https://a.example.com", root=tmp_path).ids() == [1, 2]
    assert path.read_text(encoding="utf-8") == content   # left alone
