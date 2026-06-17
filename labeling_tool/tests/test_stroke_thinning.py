import numpy as np

from labeling_tool.core.canvas.stroke_thinning import thin_stroke_into


def _max_run_per_column(mask, x0, x1):
    """Max vertical foreground run within columns [x0,x1) — a thickness proxy."""
    worst = 0
    for x in range(x0, x1):
        col = mask[:, x] > 0
        worst = max(worst, int(col.sum()))
    return worst


def test_thick_stroke_becomes_thin_line():
    crack = np.zeros((60, 80), dtype=np.uint8)
    stroke = np.zeros((60, 80), dtype=np.uint8)
    stroke[20:31, 10:70] = 255            # 11px-thick horizontal bar
    before = int((stroke > 0).sum())

    thin_stroke_into(crack, stroke)

    after = int((crack > 0).sum())
    assert after > 0
    assert after < before / 3             # far thinner than the painted bar
    # Each column of the bar keeps at most a couple of pixels (≈1px line).
    assert _max_run_per_column(crack, 12, 68) <= 3


def test_preserves_preexisting_crack_outside_stroke():
    crack = np.zeros((60, 80), dtype=np.uint8)
    crack[50, 75] = 255                    # existing crack far from the stroke
    stroke = np.zeros((60, 80), dtype=np.uint8)
    stroke[20:31, 10:40] = 255

    thin_stroke_into(crack, stroke)

    assert crack[50, 75] == 255            # untouched


def test_short_stroke_survives():
    # A tiny stroke must NOT be deleted (no aggressive pruning).
    crack = np.zeros((40, 40), dtype=np.uint8)
    stroke = np.zeros((40, 40), dtype=np.uint8)
    stroke[18:23, 18:23] = 255            # small 5x5 blob
    thin_stroke_into(crack, stroke)
    assert int((crack > 0).sum()) > 0


def test_empty_stroke_is_noop():
    crack = np.zeros((20, 20), dtype=np.uint8)
    stroke = np.zeros((20, 20), dtype=np.uint8)
    thin_stroke_into(crack, stroke)
    assert int((crack > 0).sum()) == 0
