import numpy as np
import cv2

from labeling_tool.core.mask_io import load_origin_and_masks


def test_load_integer_label_mask(tmp_path):
    origin = np.full((20, 20, 3), 100, np.uint8)
    op = tmp_path / "stitched_1.jpg"; cv2.imwrite(str(op), origin)
    label = np.zeros((20, 20), np.uint8)
    label[5, :] = 1     # crack
    label[10, :] = 2    # spalling
    mp = tmp_path / "stitched_1_mask.png"; cv2.imwrite(str(mp), label)

    _, crack, spall = load_origin_and_masks(str(op), str(mp))
    assert int((crack[5, :] > 0).sum()) == 20
    assert int((spall[10, :] > 0).sum()) == 20


def test_load_legacy_rgb_mask(tmp_path):
    origin = np.full((20, 20, 3), 100, np.uint8)
    op = tmp_path / "stitched_2.jpg"; cv2.imwrite(str(op), origin)
    rgb = np.zeros((20, 20, 3), np.uint8)
    rgb[5, :, 2] = 255      # R = crack
    mp = tmp_path / "stitched_2_mask.png"; cv2.imwrite(str(mp), rgb)

    _, crack, spall = load_origin_and_masks(str(op), str(mp))
    assert int((crack[5, :] > 0).sum()) == 20
