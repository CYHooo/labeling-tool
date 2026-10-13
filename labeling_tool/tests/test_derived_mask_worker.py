import cv2
import numpy as np

from labeling_tool.ui.derived_mask_worker import (
    DerivedMaskRunnable, DerivedMaskSignals,
)


def test_run_emits_done_and_writes_files(tmp_path):
    area = np.zeros((40, 40), np.uint8)
    area[10:15, 10:15] = 255
    layers = {1: np.zeros((40, 40), np.uint8), 2: area}
    signals = DerivedMaskSignals()
    got = []
    signals.done.connect(lambda tok, hi, r15: got.append((tok, hi, r15)))
    hi_path, r15_path = tmp_path / "h.png", tmp_path / "r.png"

    DerivedMaskRunnable(layers=layers, px_per_cm=1.0,
                        highlight_path=str(hi_path),
                        repair15_path=str(r15_path),
                        token="a.jpg", signals=signals).run()

    assert len(got) == 1
    tok, hi, r15 = got[0]
    assert tok == "a.jpg" and hi[12, 12] == 2 and r15 is not None
    assert (cv2.imread(str(hi_path), cv2.IMREAD_UNCHANGED) == hi).all()
    assert r15_path.exists()
