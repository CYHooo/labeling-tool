# MobileSAM Phase 1 (导出脚本 + 推理模块 + 依赖) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 MobileSAM spalling 分割的 Phase 1:ONNX 导出脚本、本地 onnxruntime 推理模块(可注入 session、可单测)、依赖声明与模型目录。

**Architecture:** 导出脚本(用户在 torch 机器跑一次产出 `.onnx`)与运行时推理解耦。`MobileSamPredictor` 用 onnxruntime 跑编码器(每图一次、缓存嵌入)+ 解码器(每次点击);onnxruntime 与坐标/掩膜的纯函数拆开,session 可注入,故 Phase 1 不需真实模型即可单测。

**Tech Stack:** Python 3.10+、NumPy、OpenCV;运行时 `onnxruntime`(惰性导入);导出时 `torch` + `mobile_sam`(仅导出脚本,运行时不需要)。

## Global Constraints
- Python 3.10+;运行时**不引入 torch**;`onnxruntime` 为必需运行依赖,但代码**惰性导入**它(`import onnxruntime` 只在 `MobileSamPredictor.from_paths` 内),使测试套件在未装 onnxruntime 时仍可运行。
- 模型放 `labeling_tool/models/sam/`,普通 git 提交(非 LFS);`.gitignore` 不忽略 `.onnx`(已确认)。
- SAM 预处理常量:ResizeLongestSide 到 **1024**;归一化 mean=`[123.675,116.28,103.53]`、std=`[58.395,57.12,57.375]`(RGB);右/下 pad 到 1024×1024。
- 解码器 ONNX(SamOnnxModel)输入名:`image_embeddings, point_coords, point_labels, mask_input, has_mask_input, orig_im_size`;输出:`masks, iou_predictions, low_res_masks`,`masks` 已上采样到原图尺寸。
- 点提示按 SAM-ONNX 约定追加一个 `(0,0)`、label `-1` 的填充点。
- 输出掩膜:取最高 iou,`logits > 0` 阈值 → uint8 0/255。
- 纯函数 TDD;onnxruntime 整体推理(真实模型)留 Phase 2 人工冒烟。`.venv/bin/python` 跑测试。

---

### Task 1: 依赖声明 + 模型目录

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-export.txt`
- Create: `labeling_tool/models/sam/README.md`
- Create: `labeling_tool/models/sam/.gitkeep`

**Interfaces:**
- Produces: 模型落点目录 `labeling_tool/models/sam/`;运行依赖含 `onnxruntime`。

- [ ] **Step 1: requirements.txt 追加 onnxruntime**

在 `requirements.txt` 末尾追加:

```
# SAM 추론(로컬 ONNX, torch 불필요)
onnxruntime>=1.16
```

- [ ] **Step 2: 新建 requirements-export.txt(仅导出 ONNX 时需要)**

新建 `requirements-export.txt`:

```
# ONNX 모델을 직접 만들 때만 필요 (scripts/export_mobilesam_onnx.py).
# 일반 실행에는 필요 없습니다.
torch>=1.13
onnx>=1.14
# MobileSAM (vit_t) — 공식 저장소에서 설치:
#   pip install git+https://github.com/ChaoningZhang/MobileSAM.git
```

- [ ] **Step 3: 模型目录占位 + 说明**

新建 `labeling_tool/models/sam/.gitkeep`(空文件)。

新建 `labeling_tool/models/sam/README.md`:

```markdown
# MobileSAM ONNX 모델

이 폴더에는 SAM(박리) 분할용 ONNX 모델 2개가 들어갑니다 (git 으로 함께 배포):

- `mobile_sam_encoder.onnx`  (이미지 인코더, ~30–40MB)
- `mobile_sam_decoder.onnx`  (포인트 디코더, ~16MB)

## 생성 방법 (torch 가 있는 머신에서 1회)

```bash
pip install -r requirements-export.txt
python scripts/export_mobilesam_onnx.py        # 두 .onnx 를 이 폴더에 생성
git add labeling_tool/models/sam/*.onnx
git commit -m "chore: add MobileSAM ONNX models"
```

생성 후에는 torch 없이 onnxruntime 만으로 동작합니다.
```

- [ ] **Step 4: 验证目录与全量测试**

Run: `ls labeling_tool/models/sam/ && tail -3 requirements.txt`
Expected: 看到 `.gitkeep`、`README.md`,requirements 末尾有 onnxruntime。

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(无代码改动)。

- [ ] **Step 5: 提交**

```bash
git add requirements.txt requirements-export.txt labeling_tool/models/sam/.gitkeep labeling_tool/models/sam/README.md
git commit -m "build(sam): add onnxruntime dep + models/sam dir + export requirements"
```

---

### Task 2: ONNX 导出脚本

**Files:**
- Create: `labeling_tool/scripts/export_mobilesam_onnx.py`

**Interfaces:**
- Produces: 一个可执行脚本;运行后在 `labeling_tool/models/sam/` 生成 `mobile_sam_encoder.onnx`、`mobile_sam_decoder.onnx`。

> 本任务**无法在本仓库运行**(需 torch/mobile_sam/网络)。验证 = `py_compile` 语法检查 + 人工审阅;用户在本机运行产出模型。

- [ ] **Step 1: 写脚本**

新建 `labeling_tool/scripts/export_mobilesam_onnx.py`:

```python
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
```

- [ ] **Step 2: 语法检查(不导入 torch)**

Run: `.venv/bin/python -m py_compile labeling_tool/scripts/export_mobilesam_onnx.py && echo "syntax ok"`
Expected: 输出 `syntax ok`(`py_compile` 不执行/不导入 torch,仅校验语法)。

- [ ] **Step 3: 提交**

```bash
git add labeling_tool/scripts/export_mobilesam_onnx.py
git commit -m "feat(sam): add MobileSAM -> ONNX export script (encoder + decoder)"
```

---

### Task 3: 推理模块 `core/sam/predictor.py` + 单测

**Files:**
- Create: `labeling_tool/core/sam/__init__.py`
- Create: `labeling_tool/core/sam/predictor.py`
- Test: `labeling_tool/tests/test_sam_predictor.py`

**Interfaces:**
- Produces:
  - 纯函数 `resize_longest_hw(h, w, target=1024) -> (new_h, new_w, scale)`、
    `preprocess_image(bgr, target=1024) -> (np.ndarray[1,3,T,T] float32, (orig_h,orig_w), scale)`、
    `apply_coords(points_xy: np.ndarray, scale: float) -> np.ndarray`、
    `select_mask(masks, iou) -> np.ndarray uint8(0/255)`。
  - `MobileSamPredictor(encoder_session, decoder_session)`:`set_image(bgr)`、
    `predict(points_xy: list[tuple], labels: list[int]) -> np.ndarray uint8(0/255)`;
    类方法 `from_paths(encoder_path, decoder_path) -> "MobileSamPredictor"`(惰性 import onnxruntime)。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_sam_predictor.py`:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_predictor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.core.sam'`

- [ ] **Step 3: 实现模块**

新建 `labeling_tool/core/sam/__init__.py`(空文件)。

新建 `labeling_tool/core/sam/predictor.py`:

```python
"""Local MobileSAM inference via onnxruntime (no torch).

Pure helpers (resize / normalize / coord transform / mask select) are split
out so they unit-test without a real model or onnxruntime. The predictor takes
the encoder/decoder sessions by injection; ``from_paths`` builds them with a
lazy onnxruntime import.
"""

from __future__ import annotations

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


def select_mask(masks: np.ndarray, iou: np.ndarray) -> np.ndarray:
    """Pick the highest-iou mask, threshold logits>0 -> uint8 0/255 (HxW)."""
    best = int(np.argmax(iou[0]))
    logits = masks[0, best]
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
```

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_predictor.py -q`
Expected: PASS(5 passed)

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(predictor 用注入的 fake session,不依赖 onnxruntime / 真实模型)。

- [ ] **Step 5: import 冒烟(确认惰性 onnxruntime)**

Run: `.venv/bin/python -c "import labeling_tool.core.sam.predictor as p; print('ok', hasattr(p, 'MobileSamPredictor'))"`
Expected: 输出 `ok True`(模块顶层不 import onnxruntime,故未装也能导入)。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/core/sam/__init__.py labeling_tool/core/sam/predictor.py labeling_tool/tests/test_sam_predictor.py
git commit -m "feat(sam): MobileSamPredictor (onnxruntime, injectable sessions, pure helpers)"
```

---

## Self-Review

**Spec coverage(Phase 1 范围):**
- onnxruntime 必需依赖(惰性导入)+ requirements-export → Task 1 ✅
- 模型目录 `models/sam/` + 普通 git → Task 1 ✅
- 导出脚本(编码器 + 解码器 ONNX,vit_t)→ Task 2 ✅
- `MobileSamPredictor`(set_image 编码缓存 / predict 解码 + 最高 iou + 阈值 + 填充点)+ 纯函数 → Task 3 ✅
- 不依赖真实模型可单测(注入 fake session、惰性 onnxruntime)→ Task 3 ✅
- Phase 2(画布/UI)不在本计划 —— 见 spec,模型产出后另起计划。

**Placeholder scan:** 无 TBD/TODO;每个改/建代码 step 均含完整代码。导出脚本因需 torch 仅 `py_compile` 校验(已注明,合理)。

**Type consistency:** `preprocess_image -> (arr,(h,w),scale)`、`apply_coords(points,scale)`、`select_mask(masks,iou)`、
`MobileSamPredictor(encoder_session, decoder_session)` / `set_image(bgr)` / `predict(points,labels)->uint8` 在 Task 3 定义并被测试一致消费;解码器输入键与 Global Constraints/spec 一致。

**说明:** 解码器 `point_labels` 填充点用 `-1`、`has_mask_input=0`、`mask_input` 全 0 为 SAM-ONNX 标准点提示约定;`masks` 已由 ONNX 上采样到原图尺寸,故 `select_mask` 只需选最高 iou + 阈值,不再缩放。
