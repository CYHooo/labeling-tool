# 整型类别标签掩膜格式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 crack/spalling 掩膜从三通道 RGB 改为单通道整型类别标签(0=背景、1=crack、2=spalling),覆盖本地保存、重构缓存与上传。

**Architecture:** 新增集中式 `core/mask_codec.py`(encode/decode + 自动判别),内部画笔/叠加/计测仍用双二值层不重构,只在磁盘读写边界换格式。类别↔标签注册表落在 `core/constants.py`。

**Tech Stack:** Python 3.10+、NumPy、OpenCV(cv2)、PyQt5;测试 pytest。

## Global Constraints

- Python 3.10+,允许 `X | None` 注解;不新增运行时依赖。
- 类别标签唯一真源:`core/constants.CLASS_LABELS = {"crack": 1, "spalling": 2}`,背景=0;将来加类别只在此追加。
- 重叠像素 **crack 胜**(写 1)。
- 读取**自动判别**:三通道→旧 RGB(R=crack,G=spalling);单通道且 `max ≤ 类别数`→整型标签;单通道含 255→旧版二值(按文件名 `_spalling` 兜底)。
- 单通道 PNG 用**字面值 0/1/2**(非调色板)。
- 上传字节仍为 `mask_path.read_bytes()`(保存已是整型,上传天然整型,无额外转换)。
- GUI 接入点(主窗口保存/重构)不单测,验证用 import 冒烟;纯函数(codec/rebuild)用 TDD。
- 全程 `.venv/bin/python` 跑测试。

---

### Task 1: 类别注册表 + `mask_codec` 编解码模块

**Files:**
- Modify: `labeling_tool/core/constants.py`(追加注册表)
- Create: `labeling_tool/core/mask_codec.py`
- Test: `labeling_tool/tests/test_mask_codec.py`

**Interfaces:**
- Produces:
  - `constants.BACKGROUND_LABEL: int`、`constants.CLASS_LABELS: dict[str,int]`、`constants.LABEL_TO_CLASS: dict[int,str]`。
  - `mask_codec.encode_label_mask(crack: np.ndarray | None, spalling: np.ndarray | None) -> np.ndarray`(单通道 uint8,crack 优先;两者皆 None 抛 `ValueError`)。
  - `mask_codec.decode_mask(raw: np.ndarray, *, mask_path: str | None = None) -> tuple[np.ndarray | None, np.ndarray | None]`(返回 (crack, spalling) 0/255 层;旧二值分支才会出现 None)。

- [ ] **Step 1: 追加类别注册表到 constants.py**

在 `labeling_tool/core/constants.py` 末尾追加:

```python

# Integer class labels for single-channel mask storage (0 = background).
# Single source of truth — append future classes here (e.g. {"...": 3}).
BACKGROUND_LABEL: int = 0
CLASS_LABELS: dict[str, int] = {"crack": 1, "spalling": 2}
LABEL_TO_CLASS: dict[int, str] = {v: k for k, v in CLASS_LABELS.items()}
```

- [ ] **Step 2: 写失败测试**

新建 `labeling_tool/tests/test_mask_codec.py`:

```python
import numpy as np

from labeling_tool.core.mask_codec import encode_label_mask, decode_mask


def test_encode_basic_labels():
    crack = np.zeros((10, 10), np.uint8); crack[2, :] = 255
    spall = np.zeros((10, 10), np.uint8); spall[5:8, :] = 255
    label = encode_label_mask(crack, spall)
    assert label.ndim == 2 and label.dtype == np.uint8
    assert label[2, 0] == 1          # crack
    assert label[6, 0] == 2          # spalling
    assert label[0, 0] == 0          # background


def test_encode_crack_precedence_on_overlap():
    crack = np.zeros((4, 4), np.uint8); crack[1:3, 1:3] = 255
    spall = np.zeros((4, 4), np.uint8); spall[1:3, 1:3] = 255   # same pixels
    label = encode_label_mask(crack, spall)
    assert (label[1:3, 1:3] == 1).all()       # crack wins


def test_encode_both_none_raises():
    import pytest
    with pytest.raises(ValueError):
        encode_label_mask(None, None)


def test_roundtrip_integer():
    crack = np.zeros((6, 6), np.uint8); crack[1, :] = 255
    spall = np.zeros((6, 6), np.uint8); spall[4, :] = 255
    label = encode_label_mask(crack, spall)
    c2, s2 = decode_mask(label)
    assert np.array_equal(c2 > 0, crack > 0)
    assert np.array_equal(s2 > 0, spall > 0)


def test_decode_legacy_rgb():
    raw = np.zeros((5, 5, 3), np.uint8)
    raw[1, :, 2] = 255      # R = crack
    raw[3, :, 1] = 255      # G = spalling
    crack, spall = decode_mask(raw)
    assert int(crack.sum()) == 255 * 5 and (crack[1, :] == 255).all()
    assert int(spall.sum()) == 255 * 5 and (spall[3, :] == 255).all()


def test_decode_legacy_binary_by_filename():
    raw = np.zeros((5, 5), np.uint8); raw[2, :] = 255   # max 255 -> legacy binary
    crack, spall = decode_mask(raw, mask_path="/x/stitched_1_spalling.png")
    assert crack is None and spall is not None and int(spall.sum()) == 255 * 5
    crack2, spall2 = decode_mask(raw, mask_path="/x/stitched_1_mask.png")
    assert spall2 is None and crack2 is not None
```

- [ ] **Step 3: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_codec.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'labeling_tool.core.mask_codec'`

- [ ] **Step 4: 实现 mask_codec.py**

新建 `labeling_tool/core/mask_codec.py`:

```python
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
```

- [ ] **Step 5: 运行确认通过**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_codec.py -q`
Expected: PASS(6 passed)

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/core/constants.py labeling_tool/core/mask_codec.py labeling_tool/tests/test_mask_codec.py
git commit -m "feat(mask): add integer-label codec + class-label registry"
```

---

### Task 2: 读取路径接入 codec(`mask_io.load_origin_and_masks`)

**Files:**
- Modify: `labeling_tool/core/mask_io.py`
- Test: `labeling_tool/tests/test_mask_io.py`(新建)

**Interfaces:**
- Consumes: `mask_codec.decode_mask`。
- Produces: `load_origin_and_masks(origin_path, mask_path)` 返回不变 `(origin_bgr, crack|None, spalling|None)`,但内部解码改走 codec(支持整型/旧 RGB/旧二值)。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_mask_io.py`:

```python
import numpy as np
import cv2

from labeling_tool.core.mask_io import load_origin_and_masks


def test_load_integer_label_mask(tmp_path):
    origin = np.full((20, 20, 3), 100, np.uint8)
    op = tmp_path / "stitched_1.jpg"; cv2.imwrite(str(op), origin)
    label = np.zeros((20, 20), np.uint8)
    label[5, :] = 1     # crack
    label[10, :] = 2    # spalling
    mp = tmp_path / "stitched_1_mask.png"; cv2.imwrite(str(mp), label)

    _, crack, spall = load_origin_and_masks(str(op), str(mp))
    assert int((crack[5, :] > 0).sum()) == 20
    assert int((spall[10, :] > 0).sum()) == 20


def test_load_legacy_rgb_mask(tmp_path):
    origin = np.full((20, 20, 3), 100, np.uint8)
    op = tmp_path / "stitched_2.jpg"; cv2.imwrite(str(op), origin)
    rgb = np.zeros((20, 20, 3), np.uint8)
    rgb[5, :, 2] = 255      # R = crack
    mp = tmp_path / "stitched_2_mask.png"; cv2.imwrite(str(mp), rgb)

    _, crack, spall = load_origin_and_masks(str(op), str(mp))
    assert int((crack[5, :] > 0).sum()) == 20
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_io.py -q`
Expected: FAIL — 整型标签图当前被旧逻辑当作三通道处理失败,或断言不成立。

- [ ] **Step 3: 改写 load_origin_and_masks**

把 `labeling_tool/core/mask_io.py` 顶部 import 与 `load_origin_and_masks` 整体替换。

顶部 import 段(第 1–8 行)替换为:

```python
"""Mask file path resolution and decoding."""

import cv2
from pathlib import Path

from labeling_tool.core.constants import IMAGE_EXTENSIONS, MASK_NAME_SUFFIXES
from labeling_tool.core.mask_codec import decode_mask
```

`load_origin_and_masks` 函数(原第 34–62 行)替换为:

```python
def load_origin_and_masks(origin_path: str, mask_path: str | None):
    """
    Load the origin image and decode the detected mask into separate
    crack / spalling uint8 layers (0 or 255).

    Returns: (origin_bgr, crack_mask_or_None, spalling_mask_or_None)
    """
    origin = cv2.imread(origin_path)
    if origin is None:
        raise FileNotFoundError(f"Cannot read origin image: {origin_path}")

    crack_mask = None
    spalling_mask = None
    if mask_path is not None:
        raw = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if raw is not None:
            crack_mask, spalling_mask = decode_mask(raw, mask_path=mask_path)

    return origin, crack_mask, spalling_mask
```

(注:`find_mask_path` 保持不变。删掉了不再使用的 `import os` 与 `import numpy as np`。)

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_io.py -q`
Expected: PASS(2 passed)

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/mask_io.py labeling_tool/tests/test_mask_io.py
git commit -m "feat(mask): decode masks via codec (integer + legacy RGB/binary)"
```

---

### Task 3: 保存路径接入 codec(`main_window._save_all_artifacts`)

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`

**Interfaces:**
- Consumes: `mask_codec.encode_label_mask`。

- [ ] **Step 1: 加 import**

在 `labeling_tool/core/window/main_window.py` 顶部已有的 `from labeling_tool.core.mask_io import load_origin_and_masks` 之后新增一行:

```python
from labeling_tool.core.mask_codec import encode_label_mask
```

- [ ] **Step 2: 改保存 mask 的块**

把 `_save_all_artifacts` 中这段(原 322–333 行附近):

```python
        # ----- 1. Mask -----
        if mc is not None or ms is not None:
            ref = mc if mc is not None else ms
            h, w = ref.shape
            bgr = np.zeros((h, w, 3), dtype=np.uint8)
            if mc is not None:
                bgr[..., 2] = mc
            if ms is not None:
                bgr[..., 1] = ms
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mask_out = self.output_dir / mask_store.mask_name(filename)
            _cv2.imwrite(str(mask_out), bgr)
```

替换为:

```python
        # ----- 1. Mask (single-channel integer label: 0=bg, 1=crack, 2=spalling) -----
        if mc is not None or ms is not None:
            label = encode_label_mask(mc, ms)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mask_out = self.output_dir / mask_store.mask_name(filename)
            _cv2.imwrite(str(mask_out), label)
```

- [ ] **Step 3: import 冒烟 + 全量测试**

Run: `.venv/bin/python -c "import labeling_tool.core.window.main_window; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(保存为 GUI 路径,无单测,改动不破坏现有测试)。

- [ ] **Step 4: 提交**

```bash
git add labeling_tool/core/window/main_window.py
git commit -m "feat(mask): save Labeling masks as single-channel integer labels"
```

---

### Task 4: 重构缓存改整型(`mask_store` + 各 rebuild 落盘点 + 测试)

**Files:**
- Modify: `labeling_tool/session/mask_store.py`(`build_rebuilt_rgb` → `build_rebuilt_label_mask`)
- Modify: `labeling_tool/rebuild_cache.py`(`_prebuild_one`)
- Modify: `labeling_tool/core/window/main_window.py`(两处 rebuild 落盘)
- Test: `labeling_tool/tests/test_mask_store.py`、`labeling_tool/tests/test_rebuild_cache.py`(更新)

**Interfaces:**
- Consumes: `mask_codec.decode_mask`、`constants.CLASS_LABELS`。
- Produces: `mask_store.build_rebuilt_label_mask(origin_bgr, coarse_raw) -> np.ndarray`(单通道 uint8 标签,crack 优先)。**注意:旧名 `build_rebuilt_rgb` 被移除**,所有调用方改用新名。

- [ ] **Step 1: 更新 test_mask_store.py 的两个 rebuild 用例**

把 `labeling_tool/tests/test_mask_store.py` 中这两个函数(原 60–78 行):

```python
def test_build_rebuilt_rgb_refines_crack_and_keeps_g():
    origin = np.full((80, 200, 3), 30, np.uint8)
    origin[38:43, 10:190] = 20
    coarse = np.zeros((80, 200, 3), np.uint8)
    coarse[38:43, 10:190, 2] = 255
    coarse[10:25, 10:60, 1] = 255
    rgb = mask_store.build_rebuilt_rgb(origin, coarse)
    assert rgb.ndim == 3 and rgb.shape[2] == 3
    assert int((rgb[..., 2] > 0).sum()) > 0
    assert int((rgb[..., 1] > 0).sum()) > 0


def test_build_rebuilt_rgb_resizes_g_to_guided(tmp_path):
    origin = np.full((60, 120, 3), 30, np.uint8)
    coarse = np.zeros((30, 60, 3), np.uint8)
    coarse[10:20, 5:55, 1] = 255
    rgb = mask_store.build_rebuilt_rgb(origin, coarse)
    assert rgb.shape[:2] == origin.shape[:2]
    assert int((rgb[..., 1] > 0).sum()) > 0
```

替换为:

```python
def test_build_rebuilt_label_refines_crack_and_keeps_spalling():
    origin = np.full((80, 200, 3), 30, np.uint8)
    origin[38:43, 10:190] = 20
    coarse = np.zeros((80, 200, 3), np.uint8)
    coarse[38:43, 10:190, 2] = 255      # R = crack
    coarse[10:25, 10:60, 1] = 255       # G = spalling
    label = mask_store.build_rebuilt_label_mask(origin, coarse)
    assert label.ndim == 2
    assert int((label == 1).sum()) > 0      # crack
    assert int((label == 2).sum()) > 0      # spalling


def test_build_rebuilt_label_resizes_spalling_to_guided():
    origin = np.full((60, 120, 3), 30, np.uint8)
    coarse = np.zeros((30, 60, 3), np.uint8)
    coarse[10:20, 5:55, 1] = 255
    label = mask_store.build_rebuilt_label_mask(origin, coarse)
    assert label.shape[:2] == origin.shape[:2]
    assert int((label == 2).sum()) > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py -q`
Expected: FAIL — `AttributeError: module 'labeling_tool.session.mask_store' has no attribute 'build_rebuilt_label_mask'`

- [ ] **Step 3: 改写 mask_store.build_rebuilt_rgb → build_rebuilt_label_mask**

`labeling_tool/session/mask_store.py` 顶部 import(第 13–18 行附近)在 `from labeling_tool.core.rebuild import process_one` 之后补两行:

```python
from labeling_tool.core.constants import CLASS_LABELS
from labeling_tool.core.mask_codec import decode_mask
```

把 `build_rebuilt_rgb` 整个函数(原 61–79 行)替换为:

```python
def build_rebuilt_label_mask(origin_bgr: np.ndarray,
                             coarse_raw: np.ndarray) -> np.ndarray:
    """Build a Rebuilt label mask: crack intensity-refined, other class kept.

    `coarse_raw` is the Detected/Labeling mask as read (3-ch BGR, integer label,
    or single-ch). It is decoded via the codec, crack is refined via process_one,
    and the non-crack (spalling) class is carried through (resized if needed).
    Returns a single-channel uint8 label image (0/1/2) with crack precedence.
    """
    crack_in, spalling_in = decode_mask(coarse_raw)
    coarse_gray = (crack_in if crack_in is not None
                   else np.zeros(coarse_raw.shape[:2], dtype=np.uint8))
    guided, _, _ = process_one(origin_bgr, coarse_gray, compute_length=False)
    out = np.zeros(guided.shape[:2], dtype=np.uint8)
    if spalling_in is not None and spalling_in.max() > 0:
        g = spalling_in
        if g.shape != guided.shape:
            g = cv2.resize(g, (guided.shape[1], guided.shape[0]),
                           interpolation=cv2.INTER_NEAREST)
        out[g > 0] = CLASS_LABELS["spalling"]
    out[guided > 0] = CLASS_LABELS["crack"]
    return out
```

- [ ] **Step 4: 更新 rebuild_cache._prebuild_one**

把 `labeling_tool/rebuild_cache.py` 第 50–51 行:

```python
        rgb = mask_store.build_rebuilt_rgb(origin_bgr, raw)
        cv2.imwrite(out_path, rgb)
```

替换为:

```python
        label = mask_store.build_rebuilt_label_mask(origin_bgr, raw)
        cv2.imwrite(out_path, label)
```

- [ ] **Step 5: 更新 main_window 两处 rebuild 落盘**

把 `labeling_tool/core/window/main_window.py` 第一处(原 474–480 行):

```python
            rgb = mask_store.build_rebuilt_rgb(origin_bgr, coarse_raw)
            if self.rebuilt_dir is not None:
                self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.rebuilt_dir / name), rgb)
            if self.output_dir is not None:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.output_dir / name), rgb)
```

替换为:

```python
            label = mask_store.build_rebuilt_label_mask(origin_bgr, coarse_raw)
            if self.rebuilt_dir is not None:
                self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.rebuilt_dir / name), label)
            if self.output_dir is not None:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.output_dir / name), label)
```

把第二处(原 618–622 行):

```python
                    rgb = mask_store.build_rebuilt_rgb(origin_bgr_rb, coarse_raw)
                    if self.rebuilt_dir is not None:
                        self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                        rebuilt_path = self.rebuilt_dir / name
                        _cv2.imwrite(str(rebuilt_path), rgb)
```

替换为:

```python
                    label = mask_store.build_rebuilt_label_mask(origin_bgr_rb, coarse_raw)
                    if self.rebuilt_dir is not None:
                        self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                        rebuilt_path = self.rebuilt_dir / name
                        _cv2.imwrite(str(rebuilt_path), label)
```

- [ ] **Step 6: 更新 test_rebuild_cache.py 的格式断言**

把 `labeling_tool/tests/test_rebuild_cache.py` 第 37 行:

```python
    assert cached.ndim == 3                       # 3-channel (R=crack) like on-demand rebuild
```

替换为:

```python
    assert cached.ndim == 2                       # single-channel integer label
```

把第 92 行:

```python
    assert int((out[..., 1] > 0).sum()) > 0     # non-crack (G) preserved
```

替换为:

```python
    assert int((out == 2).sum()) > 0            # spalling (label 2) preserved
```

- [ ] **Step 7: 运行确认通过 + import 冒烟 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py labeling_tool/tests/test_rebuild_cache.py -q`
Expected: 全部通过。

Run: `.venv/bin/python -c "import labeling_tool.core.window.main_window; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 8: 确认无残留旧名**

Run: `grep -rn "build_rebuilt_rgb" labeling_tool`
Expected: 无输出(全部改为 `build_rebuilt_label_mask`)。

- [ ] **Step 9: 提交**

```bash
git add labeling_tool/session/mask_store.py labeling_tool/rebuild_cache.py labeling_tool/core/window/main_window.py labeling_tool/tests/test_mask_store.py labeling_tool/tests/test_rebuild_cache.py
git commit -m "feat(mask): build Rebuilt cache as single-channel integer labels"
```

---

### Task 5: 上传解码接入 codec(`upload_worker._build_items`)

**Files:**
- Modify: `labeling_tool/ui/upload_worker.py`

**Interfaces:**
- Consumes: `mask_codec.decode_mask`。

- [ ] **Step 1: 加 import**

在 `labeling_tool/ui/upload_worker.py` 顶部 import 段(`from labeling_tool.session import mask_store` 之后)新增:

```python
from labeling_tool.core.mask_codec import decode_mask
```

- [ ] **Step 2: 改解码块**

把 `_build_items` 中这段(原 59–61 行):

```python
            bgr = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
            crack = bgr[..., 2] if bgr is not None and bgr.ndim == 3 else None
            spall = bgr[..., 1] if bgr is not None and bgr.ndim == 3 else None
```

替换为:

```python
            raw = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
            crack, spall = (None, None)
            if raw is not None:
                crack, spall = decode_mask(raw, mask_path=str(mask_path))
```

- [ ] **Step 3: 运行 upload_worker 测试 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_upload_worker.py -q`
Expected: PASS(现有测试写的是 RGB mask,`decode_mask` 自动判别为 RGB,流程不变)。

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 4: 提交**

```bash
git add labeling_tool/ui/upload_worker.py
git commit -m "feat(mask): decode upload masks via codec (integer + legacy)"
```

---

### Task 6: 端到端冒烟(整型保存 + 读回 + 上传字节)

**Files:** 无(仅验证)

- [ ] **Step 1: 离屏端到端检查**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import numpy as np, cv2, tempfile, os
from labeling_tool.core.mask_codec import encode_label_mask, decode_mask
# encode -> imwrite -> imread -> decode roundtrip on a real PNG file
crack = np.zeros((30, 30), np.uint8); crack[10, :] = 255
spall = np.zeros((30, 30), np.uint8); spall[20, :] = 255
label = encode_label_mask(crack, spall)
d = tempfile.mkdtemp(); p = os.path.join(d, "stitched_1_mask.png")
cv2.imwrite(p, label)
raw = cv2.imread(p, cv2.IMREAD_UNCHANGED)
assert raw.ndim == 2 and set(np.unique(raw)) <= {0, 1, 2}, set(np.unique(raw))
c, s = decode_mask(raw, mask_path=p)
assert (c[10, :] > 0).all() and (s[20, :] > 0).all()
print("PNG on-disk values:", sorted(set(int(v) for v in np.unique(raw))))
print("roundtrip ok")
PY
```
Expected:
```
PNG on-disk values: [0, 1, 2]
roundtrip ok
```

- [ ] **Step 2: 记录结果**

确认磁盘 PNG 为单通道、像素值 ∈ {0,1,2},encode→imwrite→imread→decode 往返一致。

---

## Self-Review

**Spec coverage:**
- 整型标签编解码 + crack 优先 + 自动判别三格式 → Task 1 ✅
- 读取接入(自动兼容旧 RGB/旧二值)→ Task 2 ✅
- 本地保存改整型 → Task 3 ✅
- Rebuilt 缓存改整型(+ 各 rebuild 落盘点)→ Task 4 ✅
- 上传解码接入(上传字节天然整型)→ Task 5 ✅
- 类别注册表(唯一真源)→ Task 1 ✅
- 端到端字面值 0/1/2 验证 → Task 6 ✅

**Placeholder scan:** 无 TBD/TODO;每个改代码的 step 均含完整代码。

**Type consistency:** `encode_label_mask(crack, spalling) -> np.ndarray`、`decode_mask(raw, *, mask_path=None) -> (crack, spalling)` 在 Task 1 定义,Task 2(load)、Task 4(build_rebuilt)、Task 5(upload)消费一致;`build_rebuilt_label_mask(origin_bgr, coarse_raw) -> np.ndarray` 在 Task 4 定义并替换全部 `build_rebuilt_rgb` 调用(Step 8 grep 兜底);`CLASS_LABELS` 在 Task 1 定义,Task 4 消费一致。

**说明(相对 spec 的小细化):** `build_rebuilt_label_mask` 内部改用 `decode_mask` 统一解 coarse 输入(原 `build_rebuilt_rgb` 直接取 `[...,2]/[...,1]`),使其同时支持 coarse 为 RGB 或整型,逻辑更一致;行为对等(crack 精修 + 非裂缝类保留)。
