# annotation_tool/segmenter/sam2_backend.py
"""SAM2.1 ImagePredictor backend (zero-download fallback)."""
from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from annotation_tool import configs
from annotation_tool.segmenter.base import Segmenter


class SAM2Segmenter(Segmenter):
    def __init__(self):
        self._predictor = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

    def load(self):
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        model = build_sam2(configs.SAM2_MODEL_CFG, configs.SAM2_CHECKPOINT, device=self._device)
        self._predictor = SAM2ImagePredictor(model)

    def set_image(self, pil_rgb: Image.Image):
        self._predictor.set_image(np.array(pil_rgb.convert("RGB")))

    def predict(self, points_xy, labels, box=None) -> np.ndarray:
        pc = np.array(points_xy, dtype=np.float32) if points_xy else None
        pl = np.array(labels, dtype=np.int32) if labels else None
        bx = np.array(box, dtype=np.float32) if box is not None else None
        with torch.inference_mode(), torch.autocast(self._device, dtype=torch.bfloat16):
            masks, scores, _ = self._predictor.predict(
                point_coords=pc, point_labels=pl, box=bx, multimask_output=False)
        return masks[0].astype(bool)

    def reset(self):
        if self._predictor is not None:
            self._predictor.reset_predictor()
