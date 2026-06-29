# 默认 15cm 外轮廓 + 自动 bbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 手动标注时默认显示 15cm 外轮廓,并从该轮廓自动拟合可编辑的 bbox(首次加载生成、随 mask 修改在保存时重算、弹窗确认后重拟合)。

**Architecture:** 新增纯函数 `bboxes_from_contours`(对每个 repair15 外轮廓 `cv2.minAreaRect` 拟合 OBB)。画布 `show_repair15` 默认开。主窗口在"repair15 轮廓被设置之后"调 `_maybe_auto_bbox`:无 bbox 静默拟合;mask 改后重算且已有 bbox 时弹窗确认重拟合。复用现有异步派生设施(后台线程,不卡 UI)。

**Tech Stack:** PyQt5、NumPy、OpenCV(`cv2.minAreaRect`)。

## Global Constraints
- 自动 bbox = 每个 15cm 外轮廓的 `cv2.minAreaRect` → `OrientedBox`,**不额外加 padding**(15cm 已在掩膜内)。
- 自动 bbox 与手动 OBB 同质:存 bbox.json、bbox 模式可编辑、计入 `bboxAreaMm2`。
- `show_repair15` 默认 **True**;启动时按钮勾选态同步为 True。
- 生成/更新时机与现有 15cm 轮廓一致:加载读盘 /(磁盘无则)用 mask+PPM 后台现算 / 保存后异步重算。
- 编辑保护:无 bbox→静默拟合;已有 bbox 且本次是"mask 改后的重算"→弹窗确认后**全部重拟合**,取消则保留;普通加载/切图不弹窗。
- PPM ≤ 0 或无轮廓 → 不自动 bbox。异步回调用 token 防过期。
- TDD;`.venv/bin/python` 跑测试,全量基线 139。GUI/数据相关行为用离屏冒烟验证(不入 CI 套件,因依赖会话数据)。

---

### Task 1: `bboxes_from_contours` 纯函数

**Files:**
- Modify: `labeling_tool/core/bbox/oriented_box.py`
- Modify: `labeling_tool/core/bbox/__init__.py`
- Test: `labeling_tool/tests/test_bboxes_from_contours.py`

**Interfaces:**
- Produces: `bboxes_from_contours(contours, min_area_px=1.0) -> list[OrientedBox]`(从 `labeling_tool.core.bbox` 导出)。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_bboxes_from_contours.py`:

```python
import numpy as np

from labeling_tool.core.bbox import bboxes_from_contours
from labeling_tool.core.bbox.oriented_box import OrientedBox


def _rect_contour(x0, y0, w, h):
    return np.array([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]],
                    dtype=np.int32)


def test_one_contour_one_box():
    boxes = bboxes_from_contours([_rect_contour(0, 0, 100, 50)])
    assert len(boxes) == 1
    b = boxes[0]
    assert isinstance(b, OrientedBox)
    assert abs(b.w * b.h - 100 * 50) / (100 * 50) < 0.05   # area ~ contour
    assert abs(b.cx - 50) < 2 and abs(b.cy - 25) < 2        # center


def test_multiple_contours():
    boxes = bboxes_from_contours([_rect_contour(0, 0, 40, 40),
                                  _rect_contour(200, 200, 60, 30)])
    assert len(boxes) == 2


def test_degenerate_contours_skipped():
    assert bboxes_from_contours([np.array([[0, 0], [10, 10]], np.int32)]) == []  # <3 pts
    assert bboxes_from_contours([]) == []
    assert bboxes_from_contours(None) == []


def test_tiny_area_skipped():
    assert bboxes_from_contours([_rect_contour(0, 0, 1, 1)], min_area_px=10.0) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_bboxes_from_contours.py -q`
Expected: FAIL — `ImportError: cannot import name 'bboxes_from_contours'`

- [ ] **Step 3: 实现函数**

在 `labeling_tool/core/bbox/oriented_box.py` 末尾追加(文件已 `import cv2`、`import numpy as np`):

```python
def bboxes_from_contours(contours, min_area_px: float = 1.0) -> list["OrientedBox"]:
    """Fit one OrientedBox to each contour via cv2.minAreaRect.

    Used to auto-generate repair bboxes from the 15cm (repair15) outer contours.
    No padding is added — the 15cm expansion is already baked into the mask.
    Degenerate contours (<3 points, zero/!tiny area) are skipped.
    """
    out: list[OrientedBox] = []
    for c in contours or []:
        pts = np.asarray(c, dtype=np.float32).reshape(-1, 2)
        if len(pts) < 3:
            continue
        (cx, cy), (w, h), angle = cv2.minAreaRect(pts)
        if w <= 0 or h <= 0 or (w * h) < min_area_px:
            continue
        out.append(OrientedBox(cx=float(cx), cy=float(cy),
                               w=float(w), h=float(h), angle_deg=float(angle)))
    return out
```

- [ ] **Step 4: 导出**

在 `labeling_tool/core/bbox/__init__.py`:第 1 行当前是
```python
from labeling_tool.core.bbox.oriented_box import OrientedBox
```
改为
```python
from labeling_tool.core.bbox.oriented_box import OrientedBox, bboxes_from_contours
```
并在 `__all__` 列表(现含 `"OrientedBox",` 等)里加一项 `"bboxes_from_contours",`。其它项不动。

- [ ] **Step 5: 运行确认通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_bboxes_from_contours.py -q`
Expected: PASS(4 passed)

Run: `.venv/bin/python -c "import labeling_tool.app; print('import ok')" && .venv/bin/python -m pytest labeling_tool/tests -q`
Expected: import ok;全量通过。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/core/bbox/oriented_box.py labeling_tool/core/bbox/__init__.py labeling_tool/tests/test_bboxes_from_contours.py
git commit -m "feat(bbox): bboxes_from_contours — fit OBB per contour (for 15cm auto-bbox)"
```

---

### Task 2: 15cm 外轮廓默认显示

**Files:**
- Modify: `labeling_tool/core/canvas/image_canvas.py`
- Modify: `labeling_tool/core/window/main_window.py`
- Test: `labeling_tool/tests/test_repair15_default_on.py`

**Interfaces:**
- Produces: 画布默认 `show_repair15 == True`;启动时 `_btn_show_repair15` 勾选态为 True。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_repair15_default_on.py`:

```python
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


def test_repair15_shown_by_default():
    c = ImageCanvas()
    assert c.show_repair15 is True          # 15cm contour shown by default
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_repair15_default_on.py -q`
Expected: FAIL（`assert False is True`,当前默认 False）

- [ ] **Step 3: 画布默认 True**

在 `labeling_tool/core/canvas/image_canvas.py` 的 `__init__` 中,把
```python
        self.show_repair15: bool = False
```
改为
```python
        self.show_repair15: bool = True
```

- [ ] **Step 4: 启动时同步按钮勾选态**

在 `labeling_tool/core/window/main_window.py` 的 `MainWindow.__init__` 里,`self._derived_signals.done.connect(self._on_derived_ready)` 这一行之后加一行(此时 `_build_ui()` 已建好按钮与画布):

```python
        self._btn_show_repair15.setChecked(True)   # 15cm contour on by default
```

- [ ] **Step 5: 运行确认通过 + 全量 + 离屏冒烟(按钮勾选)**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_repair15_default_on.py -q`
Expected: PASS

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全量通过。

Run（离屏确认按钮态与画布一致;依赖本地 session_18 数据）:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
ws = Workspace.default(18); ws.ensure()
w = ViewerMainWindow(ws, Manifest(session_id=18, base="x"), None)
print("btn checked:", w._btn_show_repair15.isChecked(), "canvas:", w.canvas.show_repair15)
assert w._btn_show_repair15.isChecked() and w.canvas.show_repair15
print("OK")
PY
```
Expected: `btn checked: True canvas: True` / `OK`(若本地无 session_18 数据则跳过此条,前两条已足够)。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/core/canvas/image_canvas.py labeling_tool/core/window/main_window.py labeling_tool/tests/test_repair15_default_on.py
git commit -m "feat(canvas): show the 15cm contour by default"
```

---

### Task 3: 主窗口接线 — 自动 bbox 生成/更新/重拟合

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`
- Modify: `labeling_tool/core/i18n.py`

**Interfaces:**
- Consumes: `bboxes_from_contours`(Task 1);`canvas.repair15_contours`、`canvas.bbox_interaction.boxes`、`canvas.set_repair15`、`canvas.brush_mask_crack/spalling`、`self.current_scale`、`self._edited`、`self._mark_bbox_edited()`、现有 `_derived_signals`/`DerivedMaskRunnable`。
- Produces: `_dispatch_derived(filename, crack, spall, scale)`、`_maybe_auto_bbox(token)`、`self._offer_refit_for`。

- [ ] **Step 1: `__init__` 加状态**

在 `MainWindow.__init__` 里(紧接 Task 2 加的 `self._btn_show_repair15.setChecked(True)` 之后)加:

```python
        self._offer_refit_for: str | None = None   # filename awaiting refit-confirm
```

- [ ] **Step 2: 加 `_dispatch_derived` 与 `_maybe_auto_bbox`**

在 `_on_derived_ready` 方法之前(或之后)加这两个方法:

```python
    def _dispatch_derived(self, filename: str, crack, spall, scale: float) -> None:
        """Start the async highlight+repair15 generation for one image."""
        from PyQt5.QtCore import QThreadPool
        from labeling_tool.ui.derived_mask_worker import DerivedMaskRunnable
        if self.highlight_dir is not None:
            self.highlight_dir.mkdir(parents=True, exist_ok=True)
        if self.repair15_dir is not None:
            self.repair15_dir.mkdir(parents=True, exist_ok=True)
        hi_path = (str(self.highlight_dir / mask_store.mask_name(filename))
                   if self.highlight_dir is not None else None)
        r15_path = (str(self.repair15_dir / mask_store.mask_name(filename))
                    if self.repair15_dir is not None else None)
        QThreadPool.globalInstance().start(DerivedMaskRunnable(
            crack=crack, spalling=spall, px_per_cm=scale,
            highlight_path=hi_path, repair15_path=r15_path,
            token=filename, signals=self._derived_signals))

    def _maybe_auto_bbox(self, token: str) -> None:
        """Auto-fit bboxes from the current 15cm contour. Silent when there are
        no bboxes; otherwise re-fit only on a confirmed mask-edit regeneration."""
        if self.current_idx < 0 or token != self.image_files[self.current_idx]:
            return
        contours = self.canvas.repair15_contours
        if not contours:
            return
        from labeling_tool.core.bbox import bboxes_from_contours
        new_boxes = bboxes_from_contours(contours)
        if not new_boxes:
            return
        if not self.canvas.bbox_interaction.boxes:
            self.canvas.bbox_interaction.boxes = new_boxes
            self._mark_bbox_edited()
            self.canvas.update()
            return
        if self._offer_refit_for == token:
            self._offer_refit_for = None
            ans = QMessageBox.question(
                self, self.tr_("bbox_refit_confirm_title"),
                self.tr_("bbox_refit_confirm"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans == QMessageBox.Yes:
                self.canvas.bbox_interaction.boxes = new_boxes
                self._mark_bbox_edited()
                self.canvas.update()
```

> `QMessageBox` 已在 `main_window.py` 顶部导入(`_on_measure_completed` 用了 `QInputDialog`;确认 `QMessageBox` 已 import,没有则加到现有 `from PyQt5.QtWidgets import (...)`)。

- [ ] **Step 3: `_on_derived_ready` 末尾触发自动 bbox**

把 `_on_derived_ready` 改为(在 set_repair15 之后调 `_maybe_auto_bbox`):

```python
    def _on_derived_ready(self, token: str, hi, r15):
        """Refresh the canvas overlays from a background derived-mask result,
        but only if that image is still on screen (else the file is written
        and we skip the stale overlay)."""
        if self.current_idx < 0:
            return
        if token == self.image_files[self.current_idx]:
            self.canvas.set_highlight(hi)
            self.canvas.set_repair15(r15)
            self._maybe_auto_bbox(token)
```

- [ ] **Step 4: `_save_all_artifacts` 用 helper + 置 refit 标记**

把 `_save_all_artifacts` 中派生掩膜那段(从 `# ----- 1b. Derived masks` 注释到 `self.canvas.set_repair15(r15)` 结束的整块)替换为:

```python
            # ----- 1b. Derived masks: highlight + (scale-dependent) repair15 --
            crack_snap = mc.copy() if mc is not None else None
            spall_snap = ms.copy() if ms is not None else None
            scale = self.current_scale or 0.0
            if async_derived:
                # Offer to re-fit bboxes from the new 15cm contour only when the
                # mask actually changed and bboxes already exist.
                if mask_dirty and self.canvas.bbox_interaction.boxes:
                    self._offer_refit_for = filename
                self._dispatch_derived(filename, crack_snap, spall_snap, scale)
            else:
                from labeling_tool.core.derived_masks import generate_derived_masks
                hi_path = (str(self.highlight_dir / mask_store.mask_name(filename))
                           if self.highlight_dir is not None else None)
                r15_path = (str(self.repair15_dir / mask_store.mask_name(filename))
                            if self.repair15_dir is not None else None)
                if self.highlight_dir is not None:
                    self.highlight_dir.mkdir(parents=True, exist_ok=True)
                if self.repair15_dir is not None:
                    self.repair15_dir.mkdir(parents=True, exist_ok=True)
                hi, r15 = generate_derived_masks(
                    crack_snap, spall_snap, scale, hi_path, r15_path)
                self.canvas.set_highlight(hi)
                self.canvas.set_repair15(r15)
```

> `mask_dirty` 已在 `_save_all_artifacts` 开头计算(`mask_dirty = bool(self._edited.get(filename))`)。

- [ ] **Step 5: `_show_image` 加 自动 bbox / 缺失则现算**

在 `_show_image` 里 **BBox JSON 加载之后**(`self.canvas.bbox_interaction.boxes = load_bboxes(bbox_path)` / `= []` 那个 if/else 块之后),加:

```python
        # ----- auto-bbox from the 15cm contour (default-shown) -----
        if self.canvas.repair15_contours:
            self._maybe_auto_bbox(filename)            # fit-if-empty (no dialog on load)
        elif self.current_scale and self.current_scale > 0:
            mc = self.canvas.brush_mask_crack
            ms = self.canvas.brush_mask_spalling
            if mc is not None or ms is not None:
                # No Repair15 on disk yet -> generate it (and the contour) async;
                # the callback fits bboxes when ready.
                self._dispatch_derived(
                    filename,
                    mc.copy() if mc is not None else None,
                    ms.copy() if ms is not None else None,
                    float(self.current_scale))
```

> 此处 `repair15_contours` 已由前面"读盘 set_repair15"填充(磁盘有则非空)。`_show_image` 切图时开头已 `_save_all_artifacts(only_if_edited=True)`,与此互不冲突。

- [ ] **Step 6: i18n 两键 × 三语**

在 `labeling_tool/core/i18n.py` 三个语言字典里各加(放在 bbox/measure 相关键附近):

en:
```python
        "bbox_refit_confirm_title": "Regenerate bboxes?",
        "bbox_refit_confirm":       "The 15cm region changed. Re-fit all bboxes from it? Manual edits will be lost.",
```
zh:
```python
        "bbox_refit_confirm_title": "重新生成 bbox?",
        "bbox_refit_confirm":       "15cm 区域已变化。是否按它重新拟合全部 bbox?手动调整将丢失。",
```
ko:
```python
        "bbox_refit_confirm_title": "bbox 다시 생성?",
        "bbox_refit_confirm":       "15cm 영역이 바뀌었습니다. 이 영역으로 bbox를 다시 생성할까요? 수동 편집은 사라집니다.",
```

- [ ] **Step 7: import 冒烟 + 全量**

Run: `.venv/bin/python -c "import labeling_tool.app, labeling_tool.core.window.main_window; print('import ok')"`
Expected: `import ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全量通过(无回归)。

- [ ] **Step 8: 离屏冒烟(本地 session_18 数据)**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import glob, os, numpy as np
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
ws = Workspace.default(18); ws.ensure()
imgs = sorted(glob.glob(str(ws.origin_dir / "stitched_*.jpg")))
if not imgs:
    print("no data; skip"); raise SystemExit
fn = os.path.basename(imgs[0]); ts = int(fn.replace("stitched_","").replace(".jpg",""))
mf = Manifest(session_id=18, base="x")
mf.add(PhotoEntry(filename=fn, timestamp=ts, photo_id=1, report_photo_num=1,
                  px_per_cm=25.0, scale_source="aruco"))
w = ViewerMainWindow(ws, mf, None)
w._show_image(0)
# force-clear bboxes then re-fit from the (loaded/disk) contour to prove the path
import time
print("repair15 contours:", None if not w.canvas.repair15_contours else len(w.canvas.repair15_contours))
w.canvas.bbox_interaction.boxes = []
w._maybe_auto_bbox(fn)
print("auto-fit boxes:", len(w.canvas.bbox_interaction.boxes))
print("OK")
PY
```
Expected: 打印轮廓数与自动拟合的 box 数(若该图有 repair15);无报错。

- [ ] **Step 9: 提交**

```bash
git add labeling_tool/core/window/main_window.py labeling_tool/core/i18n.py
git commit -m "feat(bbox): auto-fit bboxes from the 15cm contour (load + on-save refit w/ confirm)"
```

---

## Self-Review

**Spec coverage:**
- 默认显示 15cm → Task 2 ✅
- `bboxes_from_contours`(minAreaRect,无 padding)→ Task 1 ✅
- 首次加载生成(含磁盘无则后台现算)→ Task 3 Step 5 ✅
- 随 mask 修改在保存时重算 → Task 3 Step 4(`_offer_refit_for` + `_dispatch_derived`)+ Step 3(回调触发)✅
- 弹窗确认后全部重拟合;无 bbox 静默拟合;普通加载不弹窗 → Task 3 Step 2 `_maybe_auto_bbox` ✅
- 自动 bbox 同质、可编辑、计入并集面积 → 直接进 `bbox_interaction.boxes`,下游不变 ✅
- i18n → Task 3 Step 6 ✅

**Placeholder scan:** 无 TBD;改代码 step 均含完整代码。两处"先确认现有 import/导入行形式"是为避免重复 import,已给出合并指引。

**Type consistency:** `bboxes_from_contours(contours, min_area_px)->list[OrientedBox]`、`_dispatch_derived(filename,crack,spall,scale)`、`_maybe_auto_bbox(token)`、`_offer_refit_for: str|None`、`_mark_bbox_edited()`、`mask_dirty` 跨步骤一致;`DerivedMaskRunnable(crack,spalling,px_per_cm,highlight_path,repair15_path,token,signals)` 与现有 worker 签名一致。
