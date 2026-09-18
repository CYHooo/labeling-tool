# annotation_tool/tests/test_class_registry.py
import json

import pytest

from annotation_tool.core.class_registry import ClassRegistry


def _defaults():
    return ClassRegistry(
        names={1: "joint", 2: "concrete"},
        colors={1: (255, 0, 0), 2: (0, 200, 0)},
        export_order=[2, 1],
    )


def test_add_assigns_next_free_id_and_top_priority():
    r = _defaults()
    cid = r.add("crack", (10, 20, 30))
    assert cid == 3
    assert r.name(cid) == "crack"
    assert r.color(cid) == (10, 20, 30)
    assert r.class_ids == [1, 2, 3]
    assert r.export_order[-1] == 3  # newest class overrides others


def test_add_fills_gaps_in_ids():
    r = ClassRegistry(names={1: "a", 3: "c"}, colors={1: (0, 0, 0), 3: (0, 0, 0)},
                      export_order=[1, 3])
    assert r.add("b", (1, 1, 1)) == 2


def test_add_rejects_empty_or_duplicate_name():
    r = _defaults()
    with pytest.raises(ValueError):
        r.add("  ", (0, 0, 0))
    with pytest.raises(ValueError):
        r.add("joint", (0, 0, 0))


def test_add_fails_when_all_pixel_values_used():
    names = {i: f"c{i}" for i in range(1, 256)}
    r = ClassRegistry(names=names, colors={i: (0, 0, 0) for i in names},
                      export_order=list(names))
    with pytest.raises(ValueError):
        r.add("overflow", (0, 0, 0))


def test_rename_and_set_color():
    r = _defaults()
    r.rename(1, "seam")
    r.set_color(1, (1, 2, 3))
    assert r.name(1) == "seam"
    assert r.color(1) == (1, 2, 3)
    with pytest.raises(ValueError):
        r.rename(1, "concrete")  # duplicate
    with pytest.raises(KeyError):
        r.rename(99, "x")


def test_move_priority_up_and_down_with_bounds():
    r = _defaults()  # order [2, 1]
    r.move_priority(2, +1)
    assert r.export_order == [1, 2]
    r.move_priority(2, +1)  # already highest -> unchanged
    assert r.export_order == [1, 2]
    r.move_priority(2, -1)
    assert r.export_order == [2, 1]


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "classes.json"
    r = _defaults()
    r.add("crack", (10, 20, 30))
    r.save(path)
    r2 = ClassRegistry.load(path, fallback=ClassRegistry(names={}, colors={}, export_order=[]))
    assert r2.class_ids == r.class_ids
    assert r2.export_order == r.export_order
    assert r2.color(3) == (10, 20, 30)
    assert r2.name(3) == "crack"


def test_load_missing_file_returns_fallback_copy(tmp_path):
    fallback = _defaults()
    r = ClassRegistry.load(tmp_path / "nope.json", fallback=fallback)
    assert r.class_ids == [1, 2]
    r.add("x", (0, 0, 0))
    assert fallback.class_ids == [1, 2]  # fallback not mutated


@pytest.mark.parametrize("content", [
    "not json",
    json.dumps({"classes": [{"id": 0, "name": "bg", "color": [0, 0, 0]}], "export_order": [0]}),
    json.dumps({"classes": [{"id": 1, "name": "a", "color": [0, 0, 0]}], "export_order": [1, 2]}),
])
def test_load_invalid_file_raises(tmp_path, content):
    path = tmp_path / "classes.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        ClassRegistry.load(path, fallback=_defaults())


def test_from_configs_uses_defaults():
    from annotation_tool import configs
    r = ClassRegistry.from_configs()
    assert r.class_ids == sorted(configs.CLASS_IDS)
    assert r.export_order == list(configs.EXPORT_ORDER)
