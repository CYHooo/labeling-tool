# annotation_tool/tests/test_mask_state.py
import numpy as np
import pytest
from annotation_tool.core.mask_state import MaskState


def _mask(h, w, region):
    m = np.zeros((h, w), dtype=bool)
    (y0, y1, x0, x1) = region
    m[y0:y1, x0:x1] = True
    return m


def test_add_and_flatten_single_class():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))  # concrete fills all
    out = s.flatten()
    assert out.dtype == np.uint8
    assert (out == 2).all()


def test_priority_scalebar_over_joint_over_concrete():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))   # concrete everywhere
    s.add(1, _mask(4, 4, (0, 2, 0, 4)))   # joint top half
    s.add(3, _mask(4, 4, (0, 1, 0, 4)))   # scalebar top row
    out = s.flatten()
    assert (out[0] == 3).all()             # scalebar wins top row
    assert (out[1] == 1).all()             # joint wins 2nd row
    assert (out[2:] == 2).all()            # concrete elsewhere


def test_erase_removes_from_layer():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))
    s.erase(2, _mask(4, 4, (0, 2, 0, 4)))
    out = s.flatten()
    assert (out[0:2] == 0).all()
    assert (out[2:] == 2).all()


def test_load_from_roundtrip():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))
    s.add(3, _mask(4, 4, (0, 1, 0, 4)))
    flat = s.flatten()
    s2 = MaskState(4, 4)
    s2.load_from(flat)
    assert np.array_equal(s2.flatten(), flat)


def test_undo_redo():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))
    assert s.can_undo
    s.undo()
    assert (s.flatten() == 0).all()
    s.redo()
    assert (s.flatten() == 2).all()


def test_clear_class():
    s = MaskState(4, 4)
    s.add(1, _mask(4, 4, (0, 4, 0, 4)))
    s.clear(1)
    assert (s.flatten() == 0).all()


def test_stats_fractions():
    s = MaskState(2, 2)
    s.add(2, _mask(2, 2, (0, 1, 0, 2)))  # half concrete
    st = s.stats()
    assert st[2] == pytest.approx(0.5)
    assert st[1] == 0.0


def test_invalid_class_raises():
    s = MaskState(4, 4)
    with pytest.raises(ValueError):
        s.add(9, _mask(4, 4, (0, 1, 0, 1)))


def test_undo_does_not_corrupt_history():
    s = MaskState(4, 4)
    s.add(2, _mask(4, 4, (0, 4, 0, 4)))  # state A: all-2
    s.undo()                              # back to empty; A now in redo stack
    s.add(1, _mask(4, 4, (0, 4, 0, 4)))  # state B: all-1; redo stack must be cleared
    assert not s.can_redo
    s.undo()                              # back to empty
    assert (s.flatten() == 0).all()
