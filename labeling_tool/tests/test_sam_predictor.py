import numpy as np

from labeling_tool.core.sam.predictor import (
    resize_longest_hw, preprocess_image, apply_coords, select_mask,
    MobileSamPredictor,
)


def test_resize_longest_hw_scales_long_side_to_target():
    nh, nw, scale = resize_longest_hw(500, 1000, target=1024)
    assert (nh, nw) == (512, 1024)               # long side -> 1024
    assert abs(scale - 1024 / 1000) < 1e-6


def test_preprocess_image_shape_and_pad():
    bgr = np.full((300, 600, 3), 128, np.uint8)
    arr, (oh, ow), scale = preprocess_image(bgr, target=1024)
    assert arr.shape == (1, 3, 1024, 1024) and arr.dtype == np.float32
    assert (oh, ow) == (300, 600)
    assert abs(scale - 1024 / 600) < 1e-6
    # normalization actually applied: R channel of pixel (0,0) = (128 - mean)/std
    assert abs(float(arr[0, 0, 0, 0]) - (128 - 123.675) / 58.395) < 0.05
    # padded region (bottom-right corner) stays 0
    assert float(arr[0, 0, 1023, 1023]) == 0.0


def test_apply_coords_uniform_scale():
    pts = np.array([[100.0, 50.0]], np.float32)
    out = apply_coords(pts, scale=2.0)
    assert np.allclose(out, [[200.0, 100.0]])


def test_select_mask_picks_highest_iou_and_thresholds():
    # 3 candidate masks (logits), iou says mask #1 is best
    masks = np.stack([
        np.full((4, 4), -5.0),
        np.where(np.eye(4) > 0, 3.0, -3.0),      # diagonal positive
        np.full((4, 4), -1.0),
    ])[None]                                       # (1,3,4,4)
    iou = np.array([[0.1, 0.9, 0.2]], np.float32)
    out = select_mask(masks, iou)
    assert out.dtype == np.uint8
    assert set(np.unique(out)).issubset({0, 255})
    assert out[0, 0] == 255 and out[0, 1] == 0    # diagonal mask chosen


class _FakeEncoder:
    def run(self, _out, feed):
        assert "images" in feed
        return [np.zeros((1, 256, 64, 64), np.float32)]


class _FakeDecoder:
    def __init__(self, oh, ow):
        self.oh, self.ow = oh, ow
        self.last_feed = None

    def run(self, _out, feed):
        self.last_feed = feed
        masks = np.full((1, 3, self.oh, self.ow), -1.0, np.float32)
        masks[0, 1, 2:5, 2:5] = 4.0               # best mask: a small block
        iou = np.array([[0.2, 0.95, 0.3]], np.float32)
        low = np.zeros((1, 3, 256, 256), np.float32)
        return [masks, iou, low]


def test_predictor_end_to_end_with_fake_sessions():
    bgr = np.full((40, 60, 3), 100, np.uint8)
    dec = _FakeDecoder(40, 60)
    p = MobileSamPredictor(_FakeEncoder(), dec)
    p.set_image(bgr)
    out = p.predict([(30, 20)], [1])
    assert out.shape == (40, 60) and out.dtype == np.uint8
    assert out[3, 3] == 255                        # inside the best mask block
    # decoder received the (0,0,-1) padding point appended -> 2 points total
    assert dec.last_feed["point_coords"].shape[1] == 2
    assert list(dec.last_feed["point_labels"][0])[-1] == -1.0
    # user point scaled into the 1024 frame (scale = 1024/max(h,w) = 1024/60)
    scale = 1024 / 60
    assert abs(dec.last_feed["point_coords"][0, 0, 0] - 30 * scale) < 0.5
    assert abs(dec.last_feed["point_coords"][0, 0, 1] - 20 * scale) < 0.5
