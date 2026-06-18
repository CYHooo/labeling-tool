"""Export MobileSAM (vit_t) to ONNX: image encoder + point decoder.

Run ONCE on a machine with torch (see requirements-export.txt):

    pip install -r requirements-export.txt
    python labeling_tool/scripts/export_mobilesam_onnx.py

Outputs labeling_tool/models/sam/mobile_sam_encoder.onnx and
mobile_sam_decoder.onnx, then commit them. The running app needs only
onnxruntime (no torch) afterwards.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import torch
from mobile_sam import sam_model_registry
from mobile_sam.utils.onnx import SamOnnxModel

_CKPT_URL = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"
_OUT_DIR = Path(__file__).resolve().parent.parent / "models" / "sam"


def _ensure_checkpoint(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading MobileSAM checkpoint -> {path}")
    urllib.request.urlretrieve(_CKPT_URL, path)
    return path


def export(checkpoint: Path, out_dir: Path, opset: int = 17) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sam = sam_model_registry["vit_t"](checkpoint=str(checkpoint))
    sam.eval()

    # ---- image encoder: (1,3,1024,1024) -> (1,256,64,64) ----
    enc_path = out_dir / "mobile_sam_encoder.onnx"
    dummy_img = torch.randn(1, 3, 1024, 1024, dtype=torch.float)
    torch.onnx.export(
        sam.image_encoder, dummy_img, str(enc_path),
        input_names=["images"], output_names=["embeddings"],
        opset_version=opset, do_constant_folding=True)
    print(f"encoder -> {enc_path} ({enc_path.stat().st_size/1e6:.1f} MB)")

    # ---- point decoder (SamOnnxModel) ----
    dec_path = out_dir / "mobile_sam_decoder.onnx"
    onnx_model = SamOnnxModel(sam, return_single_mask=False)
    embed_dim = sam.prompt_encoder.embed_dim
    embed_size = sam.prompt_encoder.image_embedding_size
    mask_input_size = [4 * x for x in embed_size]
    dummy = {
        "image_embeddings": torch.randn(1, embed_dim, *embed_size, dtype=torch.float),
        "point_coords": torch.randint(0, 1024, (1, 5, 2), dtype=torch.float),
        "point_labels": torch.randint(0, 4, (1, 5), dtype=torch.float),
        "mask_input": torch.randn(1, 1, *mask_input_size, dtype=torch.float),
        "has_mask_input": torch.tensor([1], dtype=torch.float),
        "orig_im_size": torch.tensor([1500, 2250], dtype=torch.float),
    }
    dynamic_axes = {"point_coords": {1: "num_points"},
                    "point_labels": {1: "num_points"}}
    with open(dec_path, "wb") as f:
        torch.onnx.export(
            onnx_model, tuple(dummy.values()), f,
            input_names=list(dummy.keys()),
            output_names=["masks", "iou_predictions", "low_res_masks"],
            dynamic_axes=dynamic_axes, opset_version=opset,
            do_constant_folding=True)
    print(f"decoder -> {dec_path} ({dec_path.stat().st_size/1e6:.1f} MB)")
    print("\nDone. Next:\n  git add labeling_tool/models/sam/*.onnx && git commit")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path,
                    default=_OUT_DIR / "mobile_sam.pt",
                    help="MobileSAM .pt (downloaded if missing)")
    ap.add_argument("--out-dir", type=Path, default=_OUT_DIR)
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()
    ckpt = _ensure_checkpoint(args.checkpoint)
    export(ckpt, args.out_dir, args.opset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
