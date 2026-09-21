# annotation_tool/tests/test_segmenter_base.py
import numpy as np
import pytest
from annotation_tool.segmenter.base import Segmenter


class DummySegmenter(Segmenter):
    def load(self):
        self.loaded = True

    def set_image(self, pil_rgb):
        self._wh = pil_rgb.size

    def predict(self, points_xy, labels, box=None):
        w, h = self._wh
        m = np.zeros((h, w), dtype=bool)
        for (x, y) in points_xy:
            m[y, x] = True
        return m

    def reset(self):
        self._wh = None


def test_dummy_segmenter_contract():
    from PIL import Image
    s = DummySegmenter()
    s.load()
    s.set_image(Image.new("RGB", (4, 3)))
    out = s.predict([(1, 2)], [1])
    assert out.shape == (3, 4)
    assert out[2, 1]


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        Segmenter()
