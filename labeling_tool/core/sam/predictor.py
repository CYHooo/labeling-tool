"""Local MobileSAM inference via onnxruntime (no torch).

Pure helpers (resize / normalize / coord transform / mask select) are split
out so they unit-test without a real model or onnxruntime. The predictor takes
the encoder/decoder sessions by injection; ``from_paths`` builds them with a
lazy onnxruntime import.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import cv2

_MEAN = np.array([123.675, 116.28, 103.53], np.float32).reshape(1, 1, 3)
_STD = np.array([58.395, 57.12, 57.375], np.float32).reshape(1, 1, 3)


def resize_longest_hw(h: int, w: int, target: int = 1024) -> tuple[int, int, float]:
    """New (h, w) with the long side scaled to ``target`` + the scale factor."""
    scale = target / float(max(h, w))
    return int(round(h * scale)), int(round(w * scale)), scale


def preprocess_image(bgr: np.ndarray, target: int = 1024):
    """BGR uint8 -> (1,3,target,target) float32, original (h,w), scale.

    Resize-longest-to-target, SAM mean/std normalize, then pad bottom/right.
    """
    h, w = bgr.shape[:2]
    nh, nw, scale = resize_longest_hw(h, w, target)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
    norm = (resized.astype(np.float32) - _MEAN) / _STD
    padded = np.zeros((target, target, 3), np.float32)
    padded[:nh, :nw] = norm
    arr = np.transpose(padded, (2, 0, 1))[None]          # (1,3,T,T)
    return np.ascontiguousarray(arr, dtype=np.float32), (h, w), scale


def apply_coords(points_xy: np.ndarray, scale: float) -> np.ndarray:
    """Map original-image (x,y) into the resized 1024 frame (uniform scale)."""
    return points_xy.astype(np.float32) * float(scale)


SAM_CROP_PX = 1024   # native-resolution window side for large-image SAM


def crop_window(h: int, w: int, cx: int, cy: int,
                side: int = SAM_CROP_PX) -> tuple[int, int, int, int]:
    """Native-resolution square window (<= side) around (cx, cy), clamped inside
    the image. Returns (x0, y0, x1, y1). Image smaller than side -> whole image.

    Running SAM on this crop keeps full detail at the click instead of squishing
    the whole panorama to 1024 (which makes clicks select the whole image).
    """
    cw = min(int(side), int(w))
    ch = min(int(side), int(h))
    x0 = int(np.clip(int(cx) - cw // 2, 0, w - cw))
    y0 = int(np.clip(int(cy) - ch // 2, 0, h - ch))
    return x0, y0, x0 + cw, y0 + ch


SAM_MAX_AREA_FRAC = 0.85   # candidates covering more of the image are blow-ups


def select_mask(masks: np.ndarray, iou: np.ndarray,
                max_area_frac: float = SAM_MAX_AREA_FRAC) -> np.ndarray:
    """Pick the best mask, rejecting whole-image blow-ups; threshold -> 0/255.

    SAM returns 3 candidates per click; on a small/ambiguous target the
    highest-iou one is often a mask covering (almost) the whole image. Discard
    candidates whose foreground area exceeds ``max_area_frac`` of the image and
    keep the highest-iou survivor (the tightest good region). If every candidate
    is a blow-up, fall back to the smallest-area one.
    """
    cand = masks[0]                                 # (num, H, W) logits
    scores = np.asarray(iou[0]).reshape(-1)
    area_frac = np.array([float((cand[i] > 0.0).mean())
                          for i in range(cand.shape[0])])
    keep = np.where(area_frac <= max_area_frac)[0]
    if keep.size:
        best = int(keep[int(np.argmax(scores[keep]))])
    else:
        best = int(np.argmin(area_frac))            # all huge -> smallest
    logits = cand[best]
    return np.where(logits > 0.0, np.uint8(255), np.uint8(0)).astype(np.uint8)


class MobileSamPredictor:
    def __init__(self, encoder_session, decoder_session):
        self._enc = encoder_session
        self._dec = decoder_session
        self._embedding = None
        self._orig_hw = None
        self._scale = 1.0

    @classmethod
    def from_paths(cls, encoder_path, decoder_path) -> "MobileSamPredictor":
        import onnxruntime as ort                          # lazy: runtime only
        opt = ["CPUExecutionProvider"]
        enc = ort.InferenceSession(str(encoder_path), providers=opt)
        dec = ort.InferenceSession(str(decoder_path), providers=opt)
        return cls(enc, dec)

    @classmethod
    def try_load(cls, encoder_path=None, decoder_path=None):
        """Build a predictor, or return None if onnxruntime/models are missing
        or fail to load (so the GUI can disable SAM gracefully)."""
        if encoder_path is None or decoder_path is None:
            encoder_path, decoder_path = default_model_paths()
        if not (Path(encoder_path).exists() and Path(decoder_path).exists()):
            return None
        try:
            return cls.from_paths(encoder_path, decoder_path)
        except Exception:
            from labeling_tool.logging_setup import vlog
            vlog().exception("SAM predictor load failed")
            return None

    def set_image(self, bgr: np.ndarray) -> None:
        arr, orig_hw, scale = preprocess_image(bgr)
        self._orig_hw = orig_hw
        self._scale = scale
        self._embedding = self._enc.run(None, {"images": arr})[0]

    def predict(self, points_xy, labels) -> np.ndarray:
        if self._embedding is None:
            raise RuntimeError("call set_image() before predict()")
        pts = np.array(points_xy, np.float32).reshape(-1, 2)
        lbl = np.array(labels, np.float32).reshape(-1)
        # SAM-ONNX padding point (0,0) with label -1
        pts = np.concatenate([pts, np.zeros((1, 2), np.float32)], axis=0)
        lbl = np.concatenate([lbl, np.array([-1.0], np.float32)], axis=0)
        coords = apply_coords(pts, self._scale)[None]       # (1,N,2)
        oh, ow = self._orig_hw
        feed = {
            "image_embeddings": self._embedding.astype(np.float32),
            "point_coords": coords.astype(np.float32),
            "point_labels": lbl[None].astype(np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.zeros(1, np.float32),
            "orig_im_size": np.array([oh, ow], np.float32),
        }
        masks, iou, _ = self._dec.run(None, feed)
        return select_mask(masks, iou)


def default_model_paths() -> tuple[Path, Path]:
    """(encoder, decoder) ONNX paths under labeling_tool/models/sam/."""
    base = Path(__file__).resolve().parent.parent.parent / "models" / "sam"
    return base / "mobile_sam_encoder.onnx", base / "mobile_sam_decoder.onnx"


def models_available() -> bool:
    enc, dec = default_model_paths()
    return enc.exists() and dec.exists()
