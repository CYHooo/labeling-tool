import pytest
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


# ---------------------------------------------------------------- N classes
from labeling_tool.core.mask_codec import decode_layers, encode_layers


def _layer(shape, *rects):
    m = np.zeros(shape, np.uint8)
    for y0, y1, x0, x1 in rects:
        m[y0:y1, x0:x1] = 255
    return m


def test_layers_round_trip_with_user_classes():
    shape = (10, 10)
    layers = {1: _layer(shape, (0, 1, 0, 10)), 2: _layer(shape, (2, 4, 0, 5)),
              3: _layer(shape, (5, 7, 0, 5)), 17: _layer(shape, (8, 10, 0, 5))}
    label = encode_layers(layers)
    assert set(np.unique(label)) == {0, 1, 2, 3, 17}
    back = decode_layers(label)
    assert sorted(back) == [1, 2, 3, 17]
    for cid in layers:
        assert (back[cid] == layers[cid]).all(), cid


def test_crack_wins_over_every_class():
    shape = (4, 4)
    label = encode_layers({3: _layer(shape, (0, 4, 0, 4)), 1: _layer(shape, (1, 2, 0, 4))})
    assert (label[1] == 1).all() and label[0, 0] == 3


def test_decode_always_has_crack_and_spalling_layers():
    back = decode_layers(np.zeros((3, 3), np.uint8))
    assert sorted(back) == [1, 2] and not back[1].any() and not back[2].any()


def test_legacy_binary_and_rgb_still_decode_to_two_layers():
    binm = np.zeros((4, 4), np.uint8); binm[1, 1] = 255
    back = decode_layers(binm, mask_path="x_spalling.png")
    assert sorted(back) == [1, 2] and back[2][1, 1] == 255 and not back[1].any()
    rgb = np.zeros((4, 4, 3), np.uint8); rgb[0, 0, 2] = 255
    back = decode_layers(rgb)
    assert back[1][0, 0] == 255 and not back[2].any()


def test_old_two_layer_functions_still_work():
    crack = _layer((4, 4), (0, 1, 0, 4)); spall = _layer((4, 4), (2, 3, 0, 4))
    c, s = decode_mask(encode_label_mask(crack, spall))
    assert (c == crack).all() and (s == spall).all()


def test_a_label_with_a_user_class_is_not_mistaken_for_binary():
    label = np.zeros((4, 4), np.uint8); label[0, 0] = 9
    back = decode_layers(label)
    assert back[9][0, 0] == 255 and not back[1].any()


def test_encode_with_no_layers_is_an_error():
    with pytest.raises(ValueError):
        encode_layers({1: None, 2: None})


def test_load_origin_and_layers_reads_user_class_from_disk(tmp_path):
    import cv2
    from labeling_tool.core.mask_io import load_origin_and_layers
    cv2.imwrite(str(tmp_path / "a.png"), np.zeros((4, 4, 3), np.uint8))
    label = np.zeros((4, 4), np.uint8); label[2, 2] = 5
    cv2.imwrite(str(tmp_path / "m.png"), label)
    origin, layers = load_origin_and_layers(str(tmp_path / "a.png"), str(tmp_path / "m.png"))
    assert origin.shape == (4, 4, 3) and layers[5][2, 2] == 255
    assert load_origin_and_layers(str(tmp_path / "a.png"), None)[1] == {}
