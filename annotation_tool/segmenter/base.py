# annotation_tool/segmenter/base.py
"""Abstract segmentation backend + factory.

predict() contract:
  points_xy : list[(x, y)] in native image pixel coords
  labels    : list[int], 1=positive, 0=negative (same length as points_xy)
  box       : optional (x0, y0, x1, y1) in native image pixel coords
  returns   : bool ndarray of shape (H, W) at native resolution
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np


class Segmenter(ABC):
    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def set_image(self, pil_rgb) -> None: ...

    @abstractmethod
    def predict(self, points_xy, labels, box=None) -> np.ndarray: ...

    @abstractmethod
    def reset(self) -> None: ...


def build_segmenter(backend: str | None = None) -> Segmenter:
    """Construct a backend by name (defaults to configs.BACKEND)."""
    from annotation_tool import configs
    backend = backend or configs.BACKEND
    if backend == "sam2":
        from annotation_tool.segmenter.sam2_backend import SAM2Segmenter
        return SAM2Segmenter()
    if backend == "sam3":
        from annotation_tool.segmenter.sam3_backend import SAM3Segmenter
        return SAM3Segmenter()
    raise ValueError(f"unknown backend: {backend}")
