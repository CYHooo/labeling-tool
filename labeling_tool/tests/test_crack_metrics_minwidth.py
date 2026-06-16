import numpy as np
from labeling_tool.core.result.crack_metrics import (
    CrackMetrics, compute_crack_metrics,
)


def test_zero_has_min_width():
    z = CrackMetrics.zero()
    assert z.min_width_mm == 0.0


def test_min_le_mean_le_max_on_synthetic_crack():
    # A 3px-thick horizontal bar of varying width is hard to synthesize
    # cleanly; a constant-width bar makes min==mean==max, which still
    # validates the field exists and obeys ordering.
    mask = np.zeros((60, 200), dtype=np.uint8)
    mask[28:33, 20:180] = 255          # ~5px thick horizontal crack
    m = compute_crack_metrics(mask, scale_px_per_cm=10.0)
    assert m.min_width_mm is not None
    assert m.min_width_mm <= m.mean_width_mm <= m.max_width_mm
    assert m.length_mm > 0
