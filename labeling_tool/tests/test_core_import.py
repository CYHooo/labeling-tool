"""Smoke test: the copied core package imports under its new package path.

We import only the Qt-free logic modules so the test runs headless.
"""


def test_oriented_box_imports():
    from labeling_tool.core.bbox.oriented_box import OrientedBox
    box = OrientedBox(cx=10, cy=20, w=4, h=6, angle_deg=0)
    assert box.area_px2() == 24.0


def test_crack_metrics_imports():
    from labeling_tool.core.result.crack_metrics import (
        CrackMetrics, compute_crack_metrics, compute_spalling_area_mm2,
    )
    assert CrackMetrics.zero().length_mm == 0.0
