"""Mask disk codec: (crack, spalling) binary layers <-> single-channel integer
label PNG (0 = background, 1 = crack, 2 = spalling).

Label values come from core.constants.CLASS_LABELS (single source of truth);
future classes append there. The tool keeps separate 0/255 binary layers per
class internally — this module only translates at the disk boundary, and on
decode auto-detects legacy 3-channel RGB (R = crack, G = spalling) and legacy
single-channel binary (0/255, class by filename).
"""

from __future__ import annotations

import os

import numpy as np

from labeling_tool.core.constants import CLASS_LABELS

_CRACK = CLASS_LABELS["crack"]
_SPALLING = CLASS_LABELS["spalling"]
_MAX_LABEL = max(CLASS_LABELS.values())


def encode_label_mask(crack: np.ndarray | None,
                      spalling: np.ndarray | None) -> np.ndarray:
    """Pack two 0/255 binary layers into a single-channel uint8 label image.

    Background = 0. Spalling is written first, then crack, so a pixel painted
    as BOTH resolves to crack (crack precedence). Shape comes from whichever
    layer is non-None.
    """
    ref = crack if crack is not None else spalling
    if ref is None:
        raise ValueError("encode_label_mask: both layers are None")
    out = np.zeros(ref.shape[:2], dtype=np.uint8)
    if spalling is not None:
        out[spalling > 0] = _SPALLING
    if crack is not None:
        out[crack > 0] = _CRACK
    return out


def decode_mask(raw: np.ndarray, *, mask_path: str | None = None
                ) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Decode a mask image into (crack, spalling) 0/255 layers, auto-detecting:

      * 3-channel  -> legacy RGB: R = crack, G = spalling.
      * 1-channel, max <= number of classes -> integer label map.
      * 1-channel with 255 (legacy binary) -> class by filename (_spalling).
    A layer is None only in the legacy-binary branch (the other class absent).
    """
    if raw.ndim == 3:
        crack = (raw[..., 2] > 0).astype(np.uint8) * 255
        spalling = (raw[..., 1] > 0).astype(np.uint8) * 255
        return crack, spalling
    if int(raw.max()) <= _MAX_LABEL:
        crack = (raw == _CRACK).astype(np.uint8) * 255
        spalling = (raw == _SPALLING).astype(np.uint8) * 255
        return crack, spalling
    binm = (raw > 0).astype(np.uint8) * 255
    if mask_path is not None and "_spalling" in os.path.basename(mask_path).lower():
        return None, binm
    return binm, None
