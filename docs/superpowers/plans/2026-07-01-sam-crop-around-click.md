# 大图 SAM 点击处原分辨率裁块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SAM 点选 spalling 时,在点击处取原分辨率裁块跑 SAM(而非把整张大图压到 1024),把裁块掩膜贴回全图,解决大图"整片被选中"。

**Architecture:** 新增纯函数 `crop_window`(点击处的原分辨率窗口)+ 常量 `SAM_CROP_PX=1024`。canvas 首点确定裁块并只对该块 `set_image`;`_sam_recompute` 把全图点坐标平移进裁块 → predict → 裁块掩膜按偏移贴进全图尺寸的 `_sam_preview`。predictor 类不改。

**Tech Stack:** NumPy、OpenCV、onnxruntime(现有 MobileSAM ONNX,CPU)、PyQt5。

## Global Constraints
- `SAM_CROP_PX = 1024`(裁块见方,1:1;可调常量)。
- 裁块由**首点固定**;取消/切图/清空重置(`_clear_sam_state`)。
- 点坐标全程存**全图坐标**;送 predict 前减裁块偏移并 clip 进窗口。
- 裁块掩膜按 `[y0:y1, x0:x1]` 贴进 `zeros((H,W),uint8)` 的 preview。
- predictor 类 / commit / undo / 负点 / 爆图剔除 / 画点 —— **不改**。
- TDD;`.venv/bin/python` 跑测试;canvas 测试用 `QT_QPA_PLATFORM=offscreen`。全量基线 152。

---

### Task 1: `crop_window` 纯函数 + `SAM_CROP_PX` 常量

**Files:**
- Modify: `labeling_tool/core/sam/predictor.py`(在 `apply_coords` 之后、`SAM_MAX_AREA_FRAC` 之前插入)
- Test: `labeling_tool/tests/test_sam_crop.py`

**Interfaces:**
- Produces: `SAM_CROP_PX: int = 1024`;`crop_window(h, w, cx, cy, side=SAM_CROP_PX) -> tuple[int,int,int,int]`(返回 `(x0,y0,x1,y1)`,全图坐标)。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_sam_crop.py`:

```python
from labeling_tool.core.sam.predictor import crop_window, SAM_CROP_PX


def test_default_side_is_1024():
    assert SAM_CROP_PX == 1024


def test_centered_window():
    assert crop_window(2000, 2000, 1000, 1000, 64) == (968, 968, 1032, 1032)


def test_clamp_top_left():
    assert crop_window(2000, 2000, 10, 10, 64) == (0, 0, 64, 64)


def test_clamp_bottom_right():
    assert crop_window(2000, 2000, 1995, 1995, 64) == (1936, 1936, 2000, 2000)


def test_small_image_returns_whole():
    # image (h=50, w=40) smaller than side -> whole image
    assert crop_window(50, 40, 20, 20, 64) == (0, 0, 40, 50)


def test_non_square_image():
    x0, y0, x1, y1 = crop_window(3000, 5000, 2500, 1500, 1024)
    assert (x1 - x0, y1 - y0) == (1024, 1024)
    assert 0 <= x0 and x1 <= 5000 and 0 <= y0 and y1 <= 3000
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_crop.py -q`
Expected: FAIL — `ImportError: cannot import name 'crop_window'`

- [ ] **Step 3: 实现**

在 `labeling_tool/core/sam/predictor.py` 中,`apply_coords(...)` 函数之后、`SAM_MAX_AREA_FRAC = 0.85` 之前插入(文件已 `import numpy as np`):

```python
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
```

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_crop.py -q`
Expected: PASS(6 passed)

Run: `.venv/bin/python -c "import labeling_tool.app; print('import ok')" && .venv/bin/python -m pytest labeling_tool/tests -q`
Expected: import ok;全量通过(≥152)。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/sam/predictor.py labeling_tool/tests/test_sam_crop.py
git commit -m "feat(sam): crop_window — native-res window around a click (large-image SAM)"
```

---

### Task 2: Canvas 裁块集成

**Files:**
- Modify: `labeling_tool/core/canvas/image_canvas.py`
- Test: `labeling_tool/tests/test_sam_canvas.py`(追加)

**Interfaces:**
- Consumes: `crop_window`, `SAM_CROP_PX`(Task 1);现有 `predictor.set_image(bgr)` / `predictor.predict(points, labels)`。
- Produces: `_sam_crop`(裁块 4 元组)+ 裁块化的 `_sam_add_point`/`_sam_recompute`。

- [ ] **Step 1: 写失败测试**

在 `labeling_tool/tests/test_sam_canvas.py` 末尾追加(复用文件顶部已有的 `_FakePredictor` / `_LeftClick`):

```python
def test_sam_crop_maps_preview_to_full_image(monkeypatch):
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 64)
    c = ImageCanvas(); c.resize(200, 200)
    c.set_image(np.full((200, 200, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(100, 100, 1)                 # image coords; crop centered here
    assert c._sam_crop == (68, 68, 132, 132)      # 64-window around (100,100)
    ys, xs = np.where(c._sam_preview > 0)
    # _FakePredictor puts a block at crop-local [10:20, 10:30]; +offset (68,68)
    assert (int(ys.min()), int(ys.max())) == (78, 87)
    assert (int(xs.min()), int(xs.max())) == (78, 97)
    assert c.commit_sam() is True
    assert int((c.brush_mask_spalling > 0).sum()) == 10 * 20   # placed, not whole image


def test_sam_crop_small_image_uses_whole(monkeypatch):
    import labeling_tool.core.canvas.image_canvas as IC
    monkeypatch.setattr(IC, "SAM_CROP_PX", 1024)   # image (120x80) < side -> whole
    c = ImageCanvas(); c.resize(120, 80)
    c.set_image(np.full((80, 120, 3), 30, np.uint8), None, None)
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c._sam_add_point(60, 40, 1)
    assert c._sam_crop == (0, 0, 120, 80)
    assert c.has_sam_preview()
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_sam_canvas.py -q`
Expected: FAIL(`AttributeError: '..._sam_crop'` / preview 偏移不符 —— 当前是整图路径)

- [ ] **Step 3: 加 import 与状态**

在 `image_canvas.py`:

顶部 import 区(与其它 `from labeling_tool.core...` 同处)加:
```python
from labeling_tool.core.sam.predictor import crop_window, SAM_CROP_PX
```
> `predictor.py` 顶层不 import onnxruntime(懒加载),此 import 安全。

`__init__` 里 `self._sam_image_set: bool = False` 这一行之后加:
```python
        self._sam_crop: tuple[int, int, int, int] | None = None
```

`_clear_sam_state` 里,在 `self._sam_image_set = False` 之后加:
```python
        self._sam_crop = None
```

- [ ] **Step 4: 裁块化 `_sam_add_point` 与 `_sam_recompute`**

把现有 `_sam_add_point` 与 `_sam_recompute` 整体替换为:

```python
    def _sam_add_point(self, ix: int, iy: int, label: int) -> None:
        if self._sam_predictor is None or self._origin_bgr is None:
            return
        if not self._sam_image_set:
            h, w = self._origin_bgr.shape[:2]
            self._sam_crop = crop_window(h, w, int(ix), int(iy), SAM_CROP_PX)
            x0, y0, x1, y1 = self._sam_crop
            # native-resolution crop -> SAM sees full detail at the click
            self._sam_predictor.set_image(self._origin_bgr[y0:y1, x0:x1])
            self._sam_image_set = True
        self._sam_points.append((int(ix), int(iy)))
        self._sam_labels.append(int(label))
        self._sam_recompute()

    def _sam_recompute(self) -> None:
        """Re-predict from the current points: map full-image coords into the
        native-res crop, run SAM, place the crop mask back into a full-size preview."""
        if not self._sam_points or self._sam_crop is None:
            self._sam_preview = None
            self.update()
            return
        x0, y0, x1, y1 = self._sam_crop
        cw, ch = x1 - x0, y1 - y0
        crop_pts = [(int(np.clip(px - x0, 0, cw - 1)),
                     int(np.clip(py - y0, 0, ch - 1)))
                    for (px, py) in self._sam_points]
        try:
            mask_crop = self._sam_predictor.predict(crop_pts, self._sam_labels)
            if mask_crop.shape[:2] != (ch, cw):     # defensive: never desync sizes
                mask_crop = cv2.resize(mask_crop, (cw, ch),
                                       interpolation=cv2.INTER_NEAREST)
            h, w = self._origin_bgr.shape[:2]
            preview = np.zeros((h, w), np.uint8)
            preview[y0:y1, x0:x1] = mask_crop
            self._sam_preview = preview
        except Exception:
            from labeling_tool.logging_setup import vlog
            vlog().exception("SAM predict failed")
            self._sam_preview = None
        self.update()
```

> `cv2` 已在 `image_canvas.py` 顶部 import。

- [ ] **Step 5: 运行确认通过 + 全量**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_sam_canvas.py -q`
Expected: PASS(含 2 个新测 + 原有 SAM 测试仍绿 —— 小图裁块=整图,行为不变)

Run: `.venv/bin/python -c "import labeling_tool.app; print('import ok')" && .venv/bin/python -m pytest labeling_tool/tests -q`
Expected: import ok;全量通过。

- [ ] **Step 6: 端到端亮块冒烟(真实模型,大图 —— 关键回归)**

Run(本地需有 MobileSAM ONNX;无则说明并跳过,靠上面的测试):
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import numpy as np
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.core.canvas.image_canvas import ImageCanvas
from labeling_tool.core.sam.predictor import MobileSamPredictor, models_available
if not models_available():
    print("no SAM models; skip"); raise SystemExit
c = ImageCanvas(); c.resize(400, 400)
big = np.full((3000, 4000, 3), 50, np.uint8)      # 大图,暗底
big[1400:1600, 1900:2200] = 220                   # 亮块(spalling 替身)
c.set_image(big, None, None)
c.set_sam_predictor(MobileSamPredictor.try_load())
c.set_sam_mode(True)
c._sam_add_point(2050, 1500, 1)                   # 点亮块中心
ys, xs = np.where(c._sam_preview > 0)
frac = (c._sam_preview > 0).mean()
print("preview bbox x[%d,%d] y[%d,%d] area_frac=%.4f (block ~ x[1900,2200] y[1400,1600])"
      % (xs.min(), xs.max(), ys.min(), ys.max(), frac))
assert frac < 0.05, "preview covers too much -> crop fix failed"
assert 1850 < xs.min() and xs.max() < 2260 and 1350 < ys.min() and ys.max() < 1660
print("crop-around-click SMOKE OK")
PY
```
Expected: 掩膜 bbox 贴合亮块、`area_frac` 很小(不再整片);`SMOKE OK`。

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/core/canvas/image_canvas.py labeling_tool/tests/test_sam_canvas.py
git commit -m "feat(sam): run SAM on a native-res crop around the click (large-image quality)"
```

---

## Self-Review

**Spec coverage:**
- `crop_window` + `SAM_CROP_PX=1024`(居中/贴边/小图取整图)→ Task 1 ✅
- 首点确定裁块并只对该块 `set_image` → Task 2 Step 4 ✅
- 点坐标全图↔裁块映射 + clip → Task 2 Step 4 ✅
- 裁块掩膜按偏移贴回全图 preview → Task 2 Step 4 ✅
- 裁块生命周期(`_clear_sam_state` 重置)→ Task 2 Step 3 ✅
- commit/undo/负点/爆图剔除/predictor 不改 → 未触及 ✅
- 端到端亮块回归 → Task 2 Step 6 ✅

**Placeholder scan:** 无 TBD;改代码 step 均含完整代码。

**Type consistency:** `crop_window(...)->(x0,y0,x1,y1)`;`_sam_crop: tuple[int,int,int,int]|None`;`predictor.set_image(bgr)`/`predict(points,labels)->uint8 mask` 与现有签名一致;monkeypatch `IC.SAM_CROP_PX` 生效因 canvas 以模块属性引用。
