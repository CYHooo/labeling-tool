# annotation_tool/segmenter/sam3_backend.py
"""SAM3 interactive point/box backend (main backend).

SAM3's interactive (SAM1-style) segmentation is driven through the image model:
``Sam3Processor.set_image`` computes the shared backbone features into a state
dict, and ``Sam3Image.predict_inst(state, point_coords=..., point_labels=...,
box=...)`` runs the interactive predictor on those features. The point/box
arguments match the SAM2 predictor (points are (X,Y) pixels, box is XYXY).

Requires HuggingFace access to ``facebook/sam3`` (``huggingface-cli login``);
weights are downloaded on the first ``load()`` via ``load_from_HF=True``. The
pip wheel omits the CLIP-style BPE vocab, so we pass our own copy via
``configs.SAM3_BPE_PATH``.
"""
from __future__ import annotations

import os

import numpy as np
import torch
from PIL import Image

from annotation_tool import configs
from annotation_tool.segmenter.base import Segmenter


class SAM3Segmenter(Segmenter):
    def __init__(self):
        self._model = None
        self._proc = None
        self._state = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

    def load(self):
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor
        # Prefer the local checkpoint (copied out of the HF cache) so the tool
        # works offline / without HF auth; fall back to HF download if missing.
        use_local = os.path.isfile(configs.SAM3_CHECKPOINT)
        self._model = build_sam3_image_model(
            device=self._device,
            eval_mode=True,
            load_from_HF=not use_local,
            checkpoint_path=configs.SAM3_CHECKPOINT if use_local else None,
            enable_inst_interactivity=True,  # enable the SAM1-style point/box predictor
            bpe_path=configs.SAM3_BPE_PATH,  # pip wheel omits the default vocab
        )
        self._proc = Sam3Processor(self._model)

    def set_image(self, pil_rgb: Image.Image):
        self._state = self._proc.set_image(pil_rgb.convert("RGB"))

    def predict(self, points_xy, labels, box=None) -> np.ndarray:
        pc = np.array(points_xy, dtype=np.float32) if points_xy else None
        pl = np.array(labels, dtype=np.int32) if labels else None
        bx = np.array(box, dtype=np.float32) if box is not None else None
        with torch.inference_mode():
            masks, scores, _ = self._model.predict_inst(
                self._state, point_coords=pc, point_labels=pl, box=bx,
                multimask_output=False)
        return masks[0].astype(bool)

    def reset(self):
        self._state = None
