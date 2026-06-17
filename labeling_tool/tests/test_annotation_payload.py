import numpy as np
from labeling_tool.core.bbox.oriented_box import OrientedBox
from labeling_tool.annotation_payload import build_annotation_item


def _crack_mask():
    m = np.zeros((60, 200), dtype=np.uint8)
    m[28:33, 20:180] = 255
    return m


def test_repair_areas_use_camelcase_angle():
    boxes = [OrientedBox(cx=320, cy=180, w=120, h=40, angle_deg=15)]
    item = build_annotation_item(
        timestamp=1717572612000,
        mask_s3_key="results/43/masks/mask_1717572612000.png",
        highlight_s3_key="results/43/masks/high_1717572612000.png",
        repair15_s3_key="results/43/masks/15_1717572612000.png",
        px_per_cm=45.2, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=None, boxes=boxes,
    )
    assert item["timestamp"] == 1717572612000
    assert item["maskS3Key"] == "results/43/masks/mask_1717572612000.png"
    assert item["highlightS3Key"] == "results/43/masks/high_1717572612000.png"
    assert item["repair15S3Key"] == "results/43/masks/15_1717572612000.png"
    assert item["pxPerCm"] == 45.2
    assert item["scaleSource"] == "aruco"
    ra = item["repairAreas"][0]
    assert set(ra.keys()) == {"cx", "cy", "w", "h", "angleDeg"}
    assert ra["angleDeg"] == 15


def test_crack_metrics_fields_and_defect_type():
    item = build_annotation_item(
        timestamp=1, mask_s3_key="k", highlight_s3_key="results/43/masks/high_1.png", repair15_s3_key="results/43/masks/15_1.png", px_per_cm=10.0, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=None, boxes=[],
    )
    cm = item["crackMetrics"]
    for key in ("lengthMm", "avgWidthMm", "minWidthMm", "maxWidthMm",
                "bboxAreaMm2", "bboxCount", "spallingMm2", "defectType",
                "pxPerMm"):
        assert key in cm
    assert cm["defectType"] == 0          # crack only
    assert cm["pxPerMm"] == 1.0           # 10 px/cm = 1 px/mm
    assert cm["bboxCount"] == 0
    assert cm["minWidthMm"] <= cm["avgWidthMm"] <= cm["maxWidthMm"]


def test_defect_type_spalling_and_mixed():
    spall = np.zeros((60, 200), dtype=np.uint8)
    spall[10:20, 10:20] = 255
    only_spall = build_annotation_item(
        timestamp=1, mask_s3_key="k", highlight_s3_key="results/43/masks/high_1.png", repair15_s3_key="results/43/masks/15_1.png", px_per_cm=10.0, scale_source="aruco",
        crack_mask=np.zeros((60, 200), np.uint8), spalling_mask=spall, boxes=[],
    )
    assert only_spall["crackMetrics"]["defectType"] == 1   # spalling only
    assert only_spall["crackMetrics"]["spallingMm2"] > 0

    mixed = build_annotation_item(
        timestamp=1, mask_s3_key="k", highlight_s3_key="results/43/masks/high_1.png", repair15_s3_key="results/43/masks/15_1.png", px_per_cm=10.0, scale_source="aruco",
        crack_mask=_crack_mask(), spalling_mask=spall, boxes=[],
    )
    assert mixed["crackMetrics"]["defectType"] == 2        # both


def test_bbox_area_sums_in_mm2():
    # 10 px/cm -> 1 px/mm -> area_px2 == area_mm2
    boxes = [OrientedBox(cx=0, cy=0, w=10, h=20, angle_deg=0)]  # 200 px^2
    item = build_annotation_item(
        timestamp=1, mask_s3_key="k", highlight_s3_key="results/43/masks/high_1.png", repair15_s3_key="results/43/masks/15_1.png", px_per_cm=10.0, scale_source="aruco",
        crack_mask=np.zeros((30, 30), np.uint8), spalling_mask=None, boxes=boxes,
    )
    assert item["crackMetrics"]["bboxCount"] == 1
    assert abs(item["crackMetrics"]["bboxAreaMm2"] - 200.0) < 1e-6
