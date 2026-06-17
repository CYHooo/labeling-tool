import numpy as np
import pytest

from labeling_tool.core.derived_masks import build_highlight, build_repair15
from labeling_tool.core.constants import CLASS_LABELS


def _crack():
    m = np.zeros((80, 80), np.uint8)
    m[38:42, 20:60] = 255          # a thin horizontal crack line
    return m


def _spalling():
    m = np.zeros((80, 80), np.uint8)
    m[10:20, 10:20] = 255          # a small spalling blob
    return m


# ---- build_highlight ----------------------------------------------------
def test_highlight_grows_foreground_by_about_10px():
    crack = _crack()
    hi = build_highlight(crack, None)
    # dilation by radius 10 makes the foreground strictly larger.
    assert int((hi > 0).sum()) > int((crack > 0).sum())


def test_highlight_values_are_subset_of_0_1_2():
    hi = build_highlight(_crack(), _spalling())
    assert set(np.unique(hi)).issubset({0, CLASS_LABELS["crack"], CLASS_LABELS["spalling"]})


def test_highlight_crack_precedence_on_overlap():
    # crack and spalling occupy the SAME pixels -> crack (1) must win.
    crack = np.zeros((40, 40), np.uint8); crack[18:22, 18:22] = 255
    spall = np.zeros((40, 40), np.uint8); spall[18:22, 18:22] = 255
    hi = build_highlight(crack, spall)
    assert hi[20, 20] == CLASS_LABELS["crack"]


def test_highlight_both_none_raises():
    with pytest.raises(ValueError):
        build_highlight(None, None)


# ---- build_repair15 -----------------------------------------------------
def test_repair15_output_is_0_or_255():
    r = build_repair15(_crack(), None, px_per_cm=1.0)
    assert set(np.unique(r)).issubset({0, 255})


def test_repair15_grows_with_larger_px_per_cm():
    small = build_repair15(_crack(), None, px_per_cm=0.5)   # ~8px dilate
    large = build_repair15(_crack(), None, px_per_cm=2.0)   # ~30px dilate
    assert int((large == 255).sum()) > int((small == 255).sum())


def test_repair15_region_larger_than_input_mask():
    crack = _crack()
    r = build_repair15(crack, None, px_per_cm=1.0)          # ~15px dilate
    assert int((r == 255).sum()) > int((crack > 0).sum())


def test_repair15_both_none_raises():
    with pytest.raises(ValueError):
        build_repair15(None, None, px_per_cm=1.0)


def test_repair15_distance_accuracy():
    # single foreground pixel; px_per_cm=2 -> pad = round(15*2)=30 px radius
    m = np.zeros((200, 200), np.uint8)
    m[100, 100] = 255
    r = build_repair15(m, None, px_per_cm=2.0)
    assert set(np.unique(r)).issubset({0, 255})
    assert r[100, 100] == 255                      # foreground kept
    assert r[100, 100 + 20] == 255                 # within 30px -> set
    assert r[100, 100 + 60] == 0                   # well beyond 30px -> clear


def test_repair15_empty_foreground_is_blank():
    m = np.zeros((50, 50), np.uint8)               # both layers empty (not None)
    r = build_repair15(m, m, px_per_cm=2.0)
    assert int(r.sum()) == 0
