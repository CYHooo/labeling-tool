"""Undo/redo for mask edits: only the changed rectangle of each layer is
kept, so a panorama's history stays small."""
import numpy as np

from labeling_tool.core.canvas.mask_history import MaskHistory


def _masks(h=40, w=60):
    return {"crack": np.zeros((h, w), np.uint8), "spalling": np.zeros((h, w), np.uint8)}


def test_undo_and_redo_one_edit():
    m = _masks()
    hist = MaskHistory()
    before = {k: v.copy() for k, v in m.items()}
    m["crack"][5:8, 10:20] = 255
    assert hist.record(before, m)
    assert hist.can_undo() and not hist.can_redo()
    assert hist.undo(m)
    assert not m["crack"].any()
    assert hist.can_redo()
    assert hist.redo(m)
    assert m["crack"][5:8, 10:20].all() and m["crack"].sum() == 255 * 30


def test_only_the_changed_rectangle_is_stored():
    m = _masks(1000, 2000)
    hist = MaskHistory()
    before = {k: v.copy() for k, v in m.items()}
    m["spalling"][100:110, 200:230] = 255
    hist.record(before, m)
    assert hist.stored_bytes() == 2 * 10 * 30          # before + after patch only


def test_an_edit_that_changed_nothing_is_not_recorded():
    m = _masks()
    hist = MaskHistory()
    assert not hist.record({k: v.copy() for k, v in m.items()}, m)
    assert not hist.can_undo()


def test_a_new_edit_clears_redo():
    m = _masks()
    hist = MaskHistory()
    b = {k: v.copy() for k, v in m.items()}; m["crack"][0, 0] = 255; hist.record(b, m)
    hist.undo(m)
    b = {k: v.copy() for k, v in m.items()}; m["crack"][1, 1] = 255; hist.record(b, m)
    assert not hist.can_redo()


def test_history_keeps_the_last_steps_only():
    m = _masks()
    hist = MaskHistory(max_steps=3)
    for i in range(5):
        b = {k: v.copy() for k, v in m.items()}
        m["crack"][i, i] = 255
        hist.record(b, m)
    undone = 0
    while hist.undo(m):
        undone += 1
    assert undone == 3
    assert m["crack"][0, 0] == 255 and m["crack"][1, 1] == 255   # oldest two stay


def test_history_drops_oldest_steps_past_the_byte_budget():
    m = _masks(100, 100)
    hist = MaskHistory(max_bytes=2 * 100 * 100 + 10)       # room for one full-frame step
    for i in range(3):
        b = {k: v.copy() for k, v in m.items()}
        m["crack"][:, :] = 255 if i % 2 == 0 else 0
        hist.record(b, m)
    assert hist.stored_bytes() <= 2 * 100 * 100 + 10
    assert hist.undo(m) and not hist.undo(m)


def test_clear_forgets_everything():
    m = _masks()
    hist = MaskHistory()
    b = {k: v.copy() for k, v in m.items()}; m["crack"][0, 0] = 255; hist.record(b, m)
    hist.clear()
    assert not hist.can_undo() and hist.stored_bytes() == 0
