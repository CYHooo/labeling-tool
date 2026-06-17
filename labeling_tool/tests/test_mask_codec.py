import numpy as np

from labeling_tool.core.mask_codec import encode_label_mask, decode_mask


def test_encode_basic_labels():
    crack = np.zeros((10, 10), np.uint8); crack[2, :] = 255
    spall = np.zeros((10, 10), np.uint8); spall[5:8, :] = 255
    label = encode_label_mask(crack, spall)
    assert label.ndim == 2 and label.dtype == np.uint8
    assert label[2, 0] == 1          # crack
    assert label[6, 0] == 2          # spalling
    assert label[0, 0] == 0          # background


def test_encode_crack_precedence_on_overlap():
    crack = np.zeros((4, 4), np.uint8); crack[1:3, 1:3] = 255
    spall = np.zeros((4, 4), np.uint8); spall[1:3, 1:3] = 255   # same pixels
    label = encode_label_mask(crack, spall)
    assert (label[1:3, 1:3] == 1).all()       # crack wins


def test_encode_both_none_raises():
    import pytest
    with pytest.raises(ValueError):
        encode_label_mask(None, None)


def test_roundtrip_integer():
    crack = np.zeros((6, 6), np.uint8); crack[1, :] = 255
    spall = np.zeros((6, 6), np.uint8); spall[4, :] = 255
    label = encode_label_mask(crack, spall)
    c2, s2 = decode_mask(label)
    assert np.array_equal(c2 > 0, crack > 0)
    assert np.array_equal(s2 > 0, spall > 0)


def test_decode_legacy_rgb():
    raw = np.zeros((5, 5, 3), np.uint8)
    raw[1, :, 2] = 255      # R = crack
    raw[3, :, 1] = 255      # G = spalling
    crack, spall = decode_mask(raw)
    assert int(crack.sum()) == 255 * 5 and (crack[1, :] == 255).all()
    assert int(spall.sum()) == 255 * 5 and (spall[3, :] == 255).all()


def test_decode_legacy_binary_by_filename():
    raw = np.zeros((5, 5), np.uint8); raw[2, :] = 255   # max 255 -> legacy binary
    crack, spall = decode_mask(raw, mask_path="/x/stitched_1_spalling.png")
    assert crack is None and spall is not None and int(spall.sum()) == 255 * 5
    crack2, spall2 = decode_mask(raw, mask_path="/x/stitched_1_mask.png")
    assert spall2 is None and crack2 is not None
