# 移除 rebuild 子系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除工具侧冗余的 rebuild 子系统(AI 端已出最终结果),保留两个双用工具(画笔细化 `thin_stroke_into`、计测 `measure_length_px`)。

**Architecture:** 先把两个幸存工具迁出 `core/rebuild/`,再停掉对话框预构,然后原子切除 mask_store/main_window/workspace 等处的 rebuild 用法,最后整删 `core/rebuild/` 与 `rebuild_cache.py`。每步保持全量测试绿。

**Tech Stack:** Python 3.10+、NumPy、OpenCV、scikit-image、PyQt5;测试 pytest。

## Global Constraints

- Python 3.10+;不新增运行时依赖。
- **保留**画笔细化(`thin_stroke_into`)与 crack 计测(`measure_length_px`)的行为,仅换代码落点。
- 加载显示改为 **Labeling > Detected**(去掉 rebuilt 分支与 needs_rebuild)。
- GUI 路径不单测,验证用 import 冒烟 + 全量 pytest;纯函数沿用既有测试。
- 全程 `.venv/bin/python` 跑测试。

---

### Task 1: 迁出画笔细化到 `core/canvas/stroke_thinning.py`

**Files:**
- Create: `labeling_tool/core/canvas/stroke_thinning.py`
- Modify: `labeling_tool/core/canvas/image_canvas.py:14`
- Modify: `labeling_tool/tests/test_stroke_thinning.py:3`

**Interfaces:**
- Produces: `stroke_thinning.thin_stroke_into(crack_mask, stroke_mask, pad=2, prune_min_branch=0) -> None`(行为与原 `core/rebuild/thinning.py` 完全一致),及其依赖 `skeletonize_mask`、`prune_skeleton`、`_neighbor_count`。

- [ ] **Step 1: 创建新模块(从 thinning.py 原样搬运 4 个函数)**

新建 `labeling_tool/core/canvas/stroke_thinning.py`:

```python
"""1-px stroke thinning for the brush (relocated out of the former rebuild pkg).

ImageCanvas reduces a roughly-painted crack stroke to its 1-px skeleton on
mouse release. Pure numpy / OpenCV / scikit-image (no opencv-contrib, no scipy).
"""

import numpy as np
import cv2
from skimage.morphology import skeletonize as _sk_skel


def skeletonize_mask(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Binarize (>=127) and extract a strict 1-px skeleton. Returns (bin, skel)."""
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    skel = (_sk_skel(bin_mask > 0).astype(np.uint8)) * 255
    return bin_mask, skel


def _neighbor_count(skel: np.ndarray) -> np.ndarray:
    """Count 8-connected skeleton neighbors at each skeleton pixel."""
    k = np.ones((3, 3), np.uint8)
    k[1, 1] = 0
    s = (skel > 0).astype(np.uint8)
    return cv2.filter2D(s, -1, k, borderType=cv2.BORDER_CONSTANT) * s


def prune_skeleton(skel: np.ndarray, min_branch: int = 20) -> np.ndarray:
    """Remove short spur branches from a 1-px skeleton (keeps the main trunk)."""
    s = (skel > 0).astype(np.uint8)
    nb = _neighbor_count(s)
    branch_pts = (nb >= 3) & (s > 0)

    seg = s.copy()
    seg[branch_pts] = 0
    n, labels = cv2.connectedComponents(seg)

    out = s.copy()
    for lab in range(1, n):
        comp = labels == lab
        if comp.sum() < min_branch and np.any((nb == 1) & comp):
            out[comp] = 0
    out[branch_pts] = 1
    return (out * 255).astype(np.uint8)


def thin_stroke_into(crack_mask: np.ndarray, stroke_mask: np.ndarray,
                     pad: int = 2, prune_min_branch: int = 0) -> None:
    """Replace a freshly-painted thick brush stroke with its 1-px skeleton.

    Operates in place on `crack_mask`, limited to the stroke's bounding box, and
    only touches the stroke region — pre-existing crack outside it is preserved.
    """
    ys, xs = np.where(stroke_mask > 0)
    if len(ys) == 0:
        return
    h, w = crack_mask.shape
    y0, y1 = max(0, int(ys.min()) - pad), min(h, int(ys.max()) + 1 + pad)
    x0, x1 = max(0, int(xs.min()) - pad), min(w, int(xs.max()) + 1 + pad)

    crop = stroke_mask[y0:y1, x0:x1]
    _, skel = skeletonize_mask(crop)
    if prune_min_branch:
        skel = prune_skeleton(skel, min_branch=prune_min_branch)

    region = crack_mask[y0:y1, x0:x1]   # view -> writes back into crack_mask
    region[crop > 0] = 0                # drop the thick stroke
    region[skel > 0] = 255             # keep the 1-px centerline
```

- [ ] **Step 2: 更新两个导入**

`labeling_tool/core/canvas/image_canvas.py` 第 14 行:

```python
from labeling_tool.core.rebuild.thinning import thin_stroke_into
```
改为:
```python
from labeling_tool.core.canvas.stroke_thinning import thin_stroke_into
```

`labeling_tool/tests/test_stroke_thinning.py` 第 3 行同样改为:
```python
from labeling_tool.core.canvas.stroke_thinning import thin_stroke_into
```

- [ ] **Step 3: 运行细化测试 + import 冒烟**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_stroke_thinning.py -q`
Expected: PASS(行为未变)。

Run: `.venv/bin/python -c "import labeling_tool.core.canvas.image_canvas; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 4: 提交**

```bash
git add labeling_tool/core/canvas/stroke_thinning.py labeling_tool/core/canvas/image_canvas.py labeling_tool/tests/test_stroke_thinning.py
git commit -m "refactor: relocate brush thin_stroke_into out of rebuild package"
```

---

### Task 2: 内联 `measure_length_px` 进 `crack_metrics.py`

**Files:**
- Modify: `labeling_tool/core/result/crack_metrics.py`

**Interfaces:**
- Consumes: 无(自包含)。
- Produces: `crack_metrics.measure_length_px(centerline) -> float`(模块内私有使用,行为同原 length_centerline 版本)。

- [ ] **Step 1: 加函数 + 删旧导入**

在 `labeling_tool/core/result/crack_metrics.py` 删除这一行(第 19 行):

```python
from labeling_tool.core.rebuild import measure_length_px
```

在文件的 import 段之后、首个函数之前,插入(原样搬自 length_centerline.py 52–64):

```python
def measure_length_px(centerline: np.ndarray) -> float:
    """
    Estimate centerline length in pixels with sqrt(2) diagonal weighting.

    Counts orthogonal vs diagonal adjacencies inside the skeleton:
        length = #orthogonal_pairs + sqrt(2) * #diagonal_pairs
    """
    s = (centerline > 0).astype(np.uint8)
    ortho_k = np.array([[0, 1, 0], [1, 0, 0], [0, 0, 0]], np.uint8)
    diag_k  = np.array([[1, 0, 0], [0, 0, 0], [0, 0, 0]], np.uint8)
    ortho = float(np.sum(cv2.filter2D(s, -1, ortho_k) * s))
    diag  = float(np.sum(cv2.filter2D(s, -1, diag_k) * s))
    return ortho + diag * float(np.sqrt(2))
```

(crack_metrics.py 已 import numpy/cv2;`measure_length_px` 在 `compute_crack_metrics` 内被调用,位置在前即可。)

- [ ] **Step 2: 运行计测测试 + import 冒烟**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_crack_metrics_minwidth.py labeling_tool/tests/test_annotation_payload.py -q`
Expected: PASS(长度计算行为未变)。

Run: `.venv/bin/python -c "import labeling_tool.core.result.crack_metrics; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: 提交**

```bash
git add labeling_tool/core/result/crack_metrics.py
git commit -m "refactor: inline measure_length_px into crack_metrics"
```

---

### Task 3: 对话框停止预构(移除 `run_prebuild`)

**Files:**
- Modify: `labeling_tool/ui/dialog_helpers.py`
- Modify: `labeling_tool/ui/login_dialog.py`
- Modify: `labeling_tool/ui/fetch_dialog.py`

**Interfaces:**
- 移除 `dialog_helpers.run_prebuild`;login/fetch 打开/拉取后直接进主界面,不再预构 `Rebuilt/`。

- [ ] **Step 1: dialog_helpers 删 run_prebuild 与 rebuild_cache 导入**

`labeling_tool/ui/dialog_helpers.py`:删除 `from labeling_tool.rebuild_cache import prebuild_rebuilt` 这一行,并删除整个 `run_prebuild` 函数(`def run_prebuild(ws, timestamps, progress, status_label) -> None:` 起至其结束)。`load_config`/`save_config` 保留不动。

- [ ] **Step 2: login_dialog 去掉预构调用**

`labeling_tool/ui/login_dialog.py`:
- 第 16 行导入改为(去掉 `run_prebuild`):
```python
from labeling_tool.ui.dialog_helpers import load_config, save_config
```
- 删除离线打开里的预构调用块(第 99–102 行):
```python
        run_prebuild(ws, [
            self.manifest.get(fn).timestamp
            for fn in self.manifest.filenames_in_order()],
            self.progress, self.lbl_status)
```
(删除后,`self.accept()` 紧接 `vlog().info(...)`。`self.progress`/`self.lbl_status` 控件保留声明,无害。)

- [ ] **Step 3: fetch_dialog 去掉预构调用**

`labeling_tool/ui/fetch_dialog.py`:
- 第 15 行导入改为:
```python
from labeling_tool.ui.dialog_helpers import save_config
```
- 删除拉取后的预构调用(第 154–155 行):
```python
        run_prebuild(ws, [int(p["timestamp"]) for p in photos],
                     self.progress, self.lbl_status)
```
(下载进度仍用 `self.progress`;删除后直接进入 `manifest.save(...)`。)

- [ ] **Step 4: import 冒烟 + 全量**

Run: `.venv/bin/python -c "import labeling_tool.ui.login_dialog, labeling_tool.ui.fetch_dialog, labeling_tool.ui.dialog_helpers; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(rebuild_cache 现仅被其自身测试引用)。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/ui/dialog_helpers.py labeling_tool/ui/login_dialog.py labeling_tool/ui/fetch_dialog.py
git commit -m "refactor: drop Rebuilt prebuild step from login/fetch dialogs"
```

---

### Task 4: 切除 rebuild 用法(mask_store / main_window / workspace / ui_builder / i18n)

**Files:**
- Modify: `labeling_tool/session/mask_store.py`
- Modify: `labeling_tool/session/workspace.py`
- Modify: `labeling_tool/core/window/main_window.py`
- Modify: `labeling_tool/core/window/ui_builder.py`
- Modify: `labeling_tool/ui/main_window.py`
- Modify: `labeling_tool/core/i18n.py`
- Test: `labeling_tool/tests/test_mask_store.py`、`labeling_tool/tests/test_workspace.py`

**Interfaces:**
- `mask_store.resolve_display_mask(*, labeling_dir, detected_dir, origin_filename) -> tuple[Path | None, str]`(**去掉 `rebuilt_dir` 参数**;来源值为 `"labeling"` / `"detected"` / `"none"`)。
- `build_rebuilt_label_mask`、`_rebuilt_is_fresh`、`workspace.rebuilt_dir` 被移除。

- [ ] **Step 1: 更新 test_mask_store.py(先改测试到新签名/语义)**

把 `labeling_tool/tests/test_mask_store.py` 中 4 个 `resolve_*` 用例(第 21–57 行)整体替换为:

```python
def test_resolve_labeling_wins(tmp_path):
    lab, det = tmp_path / "L", tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(lab / name); _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=lab, detected_dir=det, origin_filename="stitched_1.jpg")
    assert src == "labeling" and path == lab / name


def test_resolve_detected_when_no_labeling(tmp_path):
    det = tmp_path / "D"
    name = mask_store.mask_name("stitched_1.jpg")
    _touch(det / name)
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", detected_dir=det,
        origin_filename="stitched_1.jpg")
    assert src == "detected" and path == det / name


def test_resolve_none(tmp_path):
    path, src = mask_store.resolve_display_mask(
        labeling_dir=tmp_path / "L", detected_dir=tmp_path / "D",
        origin_filename="stitched_1.jpg")
    assert src == "none" and path is None
```

并删除 `test_build_rebuilt_label_refines_crack_and_keeps_spalling` 与
`test_build_rebuilt_label_resizes_spalling_to_guided` 两个函数(第 60–78 行)。

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py -q`
Expected: FAIL —— `resolve_display_mask` 仍要求 `rebuilt_dir`(或 build_rebuilt 已被测试引用移除)。

- [ ] **Step 3: 改写 mask_store.py**

把 `labeling_tool/session/mask_store.py` 顶部 import(第 11–18 行附近)改为(删 cv2/numpy/process_one,只留 Path):

```python
from __future__ import annotations

from pathlib import Path
```

把模块 docstring 中关于 Rebuilt/重建的描述精简(第 1–9 行)为:

```python
"""Deterministic per-session mask layout + display resolution.

  * where each layer's mask lives (keyed off the origin filename): Detected and
    Labeling both use ``{origin_stem}_mask.png``;
  * which layer to display: Labeling (edits) > Detected (AI final result).
"""
```

删除 `_rebuilt_is_fresh` 函数,并把 `resolve_display_mask` 整个函数替换为:

```python
def resolve_display_mask(*, labeling_dir, detected_dir,
                         origin_filename) -> tuple[Path | None, str]:
    """Pick the mask to display for an origin image.

    Returns (path, source):
      Labeling/<name> exists  -> (path, "labeling")
      Detected/<name> exists  -> (path, "detected")
      otherwise               -> (None, "none")
    A None dir means that layer is unavailable.
    """
    name = mask_name(origin_filename)
    if labeling_dir is not None:
        lab = Path(labeling_dir) / name
        if lab.exists():
            return lab, "labeling"
    if detected_dir is not None:
        det = Path(detected_dir) / name
        if det.exists():
            return det, "detected"
    return None, "none"
```

删除 `build_rebuilt_label_mask` 整个函数(从 `def build_rebuilt_label_mask(` 到其 `return out`)。

- [ ] **Step 4: workspace.py 删 rebuilt_dir**

`labeling_tool/session/workspace.py`:删除 `rebuilt_dir` 属性:

```python
    @property
    def rebuilt_dir(self) -> Path:
        return self.session_dir / "Rebuilt"
```

并把 `ensure()` 的创建列表去掉 `self.rebuilt_dir`:

```python
    def ensure(self) -> None:
        for d in (self.origin_dir, self.detected_dir,
                  self.labeling_dir, self.result_dir):
            d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: test_workspace.py 去掉 rebuilt_dir 断言**

`labeling_tool/tests/test_workspace.py`:删除第 11 行 `assert ws.rebuilt_dir == ...`;把 ensure 检查里的目录元组(第 19 行)去掉 `ws.rebuilt_dir`(改为 `ws.origin_dir, ws.detected_dir, ws.labeling_dir, ws.result_dir` 视该行原样删 `ws.rebuilt_dir` 一项)。

- [ ] **Step 6: core main_window.py 切除 rebuild**

`labeling_tool/core/window/main_window.py`:
1. 删第 49 行 `self.rebuilt_dir: Path | None = None`。
2. 删第 139 行 `self._btn_rebuild_force.setText(self.tr_("btn_rebuild_force"))`。
3. `_sync_output_dir`(第 157–165 行)改为(去掉 rebuilt_dir):
```python
    def _sync_output_dir(self):
        """Derive output_dir, result_dir from origin_dir.parent."""
        if self.origin_dir is not None:
            parent = self.origin_dir.parent
            self.output_dir  = parent / OUTPUT_DIR_NAME
            self.result_dir  = parent / "Result"
        else:
            self.output_dir = self.result_dir = None
```
4. 删除整个 `_on_rebuild_force` 方法(第 425–483 行,从 `def _on_rebuild_force(self):` 到 `self._show_image(self.current_idx, force_reload=True)`)。
5. `resolve_display_mask` 调用(第 591–593 行)改为(去掉 rebuilt_dir):
```python
        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        mask_path = str(resolved) if resolved is not None else None
```
6. 删除整个 `if source == "needs_rebuild":` 块(第 596–627 行)。删除后,`mask_path` 之后紧接第 629 行 `print(f"[load] {filename} -> {source}: {mask_path}", file=_sys.stderr)`。

- [ ] **Step 7: ui_builder.py 删「重新重建」按钮**

`labeling_tool/core/window/ui_builder.py`:删除第 173–175 行:

```python
    window._btn_rebuild_force = QPushButton(window.tr_("btn_rebuild_force"))
    window._btn_rebuild_force.clicked.connect(window._on_rebuild_force)
    gb.addWidget(window._btn_rebuild_force)
```

- [ ] **Step 8: ui/main_window.py 删 rebuilt_dir 赋值**

`labeling_tool/ui/main_window.py`:删除第 43 行 `self.rebuilt_dir = workspace.rebuilt_dir.resolve()`。

- [ ] **Step 9: i18n.py 删 6 个 rebuild 键(三种语言)**

在 `labeling_tool/core/i18n.py` 三个语言块里各删除这 6 个键:
`"btn_rebuild_force"`、`"status_rebuilding"`、`"rebuild_done"`、`"rebuild_failed"`、`"rebuild_confirm_title"`、`"rebuild_confirm_msg"`(英/中/韩共 18 行)。

- [ ] **Step 10: 运行测试 + import 冒烟 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_mask_store.py labeling_tool/tests/test_workspace.py -q`
Expected: 全部通过。

Run: `.venv/bin/python -c "import labeling_tool.app; import labeling_tool.core.window.main_window; import labeling_tool.ui.main_window; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 11: 提交**

```bash
git add labeling_tool/session/mask_store.py labeling_tool/session/workspace.py labeling_tool/core/window/main_window.py labeling_tool/core/window/ui_builder.py labeling_tool/ui/main_window.py labeling_tool/core/i18n.py labeling_tool/tests/test_mask_store.py labeling_tool/tests/test_workspace.py
git commit -m "refactor: display Detected directly, remove all rebuild usage"
```

---

### Task 5: 删除 rebuild 包与缓存

**Files:**
- Delete: `labeling_tool/core/rebuild/`(整个目录)
- Delete: `labeling_tool/rebuild_cache.py`
- Delete: `labeling_tool/tests/test_rebuild_cache.py`

- [ ] **Step 1: 删除文件**

Run:
```bash
git rm -r labeling_tool/core/rebuild labeling_tool/rebuild_cache.py labeling_tool/tests/test_rebuild_cache.py
```

- [ ] **Step 2: 确认无残留引用**

Run: `grep -rn "core\.rebuild\|rebuild_cache\|build_rebuilt\|process_one\|prebuild_rebuilt\|rebuilt_dir\|run_prebuild\|build_length_centerline" labeling_tool`
Expected: 无输出(全部清理干净)。

- [ ] **Step 3: import 冒烟 + 全量**

Run: `.venv/bin/python -c "import labeling_tool.app; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(数量较前减少:删了 test_rebuild_cache 的若干用例)。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "chore: delete rebuild package and rebuild_cache"
```

---

### Task 6: GUI 冒烟(可选,人工)

**Files:** 无(仅运行验证)

- [ ] **Step 1: 启动 GUI 离线打开 session_18**

Run: `DISPLAY=:1 .venv/bin/python -m labeling_tool.app`
Expected:
- 登录页「이미 받은 세션 열기」选 session_18 → **直接进主界面**(无"재구성/rebuild"进度阶段)。
- 主界面无「重新重建」按钮;有 Labeling 用 Labeling,否则直接显示 Detected。
- 画笔画一笔松开仍细化为 1px;无未捕获异常(libjpeg 的 `Invalid SOS` 警告可忽略)。

- [ ] **Step 2: 记录结果**

人工确认离线/在线两条路径进入主界面正常、画笔细化与显示无回归。

---

## Self-Review

**Spec coverage:**
- 迁出 thin_stroke_into → Task 1 ✅;内联 measure_length_px → Task 2 ✅
- 对话框停预构(run_prebuild)→ Task 3 ✅
- resolve_display_mask 改 Labeling>Detected、删 build_rebuilt/_rebuilt_is_fresh/process_one → Task 4 ✅
- workspace 删 rebuilt_dir → Task 4 ✅;main_window 删 rebuilt 状态/方法/加载块/按钮 → Task 4 ✅
- i18n 删键 → Task 4 ✅(含 spec 未逐一列出的 btn_rebuild_force/rebuild_confirm_* —— 同属"rebuild 相关",见下)
- 整删 core/rebuild + rebuild_cache + test_rebuild_cache → Task 5 ✅
- 测试更新(stroke_thinning 导入、mask_store、workspace)→ Task 1/4 ✅

**Placeholder scan:** 无 TBD/TODO;每个改代码 step 均含完整代码或精确行号删除指令。

**Type consistency:** `resolve_display_mask(*, labeling_dir, detected_dir, origin_filename)` 在 Task 4 定义并同步更新唯一调用方(main_window)与测试;`thin_stroke_into`/`measure_length_px` 签名保持不变,仅换落点。

**相对 spec 的细化(已在切除范围内):** spec 写"删 rebuild_done/rebuild_failed/status_rebuilding",实现发现还有手动「重新重건」按钮链路 `_on_rebuild_force` + `_btn_rebuild_force` + i18n 键 `btn_rebuild_force`/`rebuild_confirm_title`/`rebuild_confirm_msg`,同属"rebuild 相关工作",一并在 Task 4 删除(否则按钮点击会调用已删方法)。
