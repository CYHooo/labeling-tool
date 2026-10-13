"""Mask disk codec: class layers <-> single-channel integer label PNG.

Pixel value = class id (core.classes): 0 background, 1 crack, 2 spalling,
3..254 user classes. The tool keeps one 0/255 binary layer per class in
memory; this module translates at the disk boundary. On decode it still
recognises legacy 3-channel RGB (R = crack, G = spalling) and legacy
single-channel 0/255 binary masks (class by filename).
"""

from __future__ import annotations

import os

import numpy as np

from labeling_tool.core.classes import CRACK_ID, MAX_CLASS_ID, SPALLING_ID


def _is_spalling_name(mask_path: str | None) -> bool:
    return (mask_path is not None
            and "_spalling" in os.path.basename(mask_path).lower())


def encode_layers(layers: dict) -> np.ndarray:
    """Pack {class id: 0/255 layer} into a label image. Area classes are
    written in id order, crack last, so crack wins any overlap."""
    present = {cid: m for cid, m in layers.items() if m is not None}
    if not present:
        raise ValueError("encode_layers: no layers")
    ref = next(iter(present.values()))
    out = np.zeros(ref.shape[:2], dtype=np.uint8)
    for cid in sorted(c for c in present if c != CRACK_ID):
        out[present[cid] > 0] = cid
    if CRACK_ID in present:
        out[present[CRACK_ID] > 0] = CRACK_ID
    return out


def decode_layers(raw: np.ndarray, *, mask_path: str | None = None) -> dict:
    """Decode a mask image into {class id: 0/255 layer}. Crack and spalling
    layers are always present; other ids only when their pixels are."""
    if raw.ndim == 3:
        return {CRACK_ID: (raw[..., 2] > 0).astype(np.uint8) * 255,
                SPALLING_ID: (raw[..., 1] > 0).astype(np.uint8) * 255}
    zeros = np.zeros(raw.shape[:2], dtype=np.uint8)
    if int(raw.max()) <= MAX_CLASS_ID:
        layers = {CRACK_ID: zeros, SPALLING_ID: zeros.copy()}
        # bincount, not np.unique: O(N) on a large panorama instead of a sort
        counts = np.bincount(raw.ravel(), minlength=MAX_CLASS_ID + 1)
        for value in np.nonzero(counts)[0]:
            if int(value) != 0:
                layers[int(value)] = (raw == value).astype(np.uint8) * 255
        return layers
    binm = (raw > 0).astype(np.uint8) * 255
    if _is_spalling_name(mask_path):
        return {CRACK_ID: zeros, SPALLING_ID: binm}
    return {CRACK_ID: binm, SPALLING_ID: zeros}


def encode_label_mask(crack: np.ndarray | None,
                      spalling: np.ndarray | None) -> np.ndarray:
    """Two-layer form of encode_layers (crack precedence)."""
    if crack is None and spalling is None:
        raise ValueError("encode_label_mask: both layers are None")
    return encode_layers({CRACK_ID: crack, SPALLING_ID: spalling})


def decode_mask(raw: np.ndarray, *, mask_path: str | None = None
                ) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Two-layer form of decode_layers: (crack, spalling). A legacy binary
    mask gives None for the class it does not hold, as before."""
    layers = decode_layers(raw, mask_path=mask_path)
    if raw.ndim != 3 and int(raw.max()) > MAX_CLASS_ID:
        if _is_spalling_name(mask_path):
            return None, layers[SPALLING_ID]
        return layers[CRACK_ID], None
    return layers[CRACK_ID], layers[SPALLING_ID]
