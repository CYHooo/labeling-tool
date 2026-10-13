import cv2
import numpy as np

from labeling_tool.core.classes import ClassRegistry, LabelClass
from labeling_tool.core.result.exporter import export_result


def test_result_image_and_text_show_user_classes(tmp_path):
    origin = np.zeros((20, 20, 3), np.uint8)
    layer = np.zeros((20, 20), np.uint8); layer[0:10, 0:10] = 255
    reg = ClassRegistry([LabelClass(3, "백태", "area", "#3C8CFF")])
    export_result(tmp_path, "p.jpg", origin, None, None, [], 10.0,
                  extra_layers={3: layer}, registry=reg)
    img = cv2.imread(str(tmp_path / "p.png"))
    assert tuple(int(v) for v in img[5, 5]) == (255, 140, 60)     # BGR of #3C8CFF
    text = (tmp_path / "p.txt").read_text(encoding="utf-8")
    assert "class_area_mm2[백태]: 100.00" in text


def test_unknown_ids_are_named_by_number(tmp_path):
    origin = np.zeros((10, 10, 3), np.uint8)
    layer = np.zeros((10, 10), np.uint8); layer[0, 0] = 255
    export_result(tmp_path, "p.jpg", origin, None, None, [], 10.0,
                  extra_layers={9: layer}, registry=ClassRegistry())
    assert "class_area_mm2[#9]: 1.00" in (tmp_path / "p.txt").read_text(encoding="utf-8")
