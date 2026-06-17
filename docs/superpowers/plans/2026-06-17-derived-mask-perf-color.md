# 派生掩膜 颜色修复 + 加速 + 后台线程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复光晕显示成青色的颜色 bug、用距离变换消除 repair15 巨核 dilation 的卡顿、并把派生掩膜生成下后台线程(同时解决切图卡顿)。

**Architecture:** 颜色:`paint_single_color_overlay` 去掉通道反转。加速:`build_repair15` 用 `cv2.distanceTransform` 替代巨核 dilate。线程:抽 `generate_derived_masks` 纯函数,新增 `ui/derived_mask_worker.py`(QRunnable+Signals),`_save_all_artifacts` 用快照派发到 QThreadPool,done 回调按当前文件名 token 守卫刷新画布;closeEvent 同步生成。

**Tech Stack:** Python 3.10+、NumPy、OpenCV(distanceTransform)、PyQt5(QThreadPool/QRunnable)。测试 pytest(含离屏 Qt)。

## Global Constraints
- Python 3.10+;不新增运行时依赖。
- 颜色修复**只动** `paint_single_color_overlay`,不动 `paint_mask_overlay`(crack/spalling 配色保持)。
- `QImage.Format_RGBA8888` 在本机是标准 RGBA(byte0=R);highlight 传入 `(255,255,0)` 须渲染为黄。
- repair15 仍是**单通道 0/255 填充**的"15cm 区域",语义不变,只换更快的等价算法(distanceTransform DIST_L2,maskSize 5)。
- 线程范围:仅派生掩膜(highlight+repair15)生成+落盘;`closeEvent` 走同步路径以保证退出前落盘。
- 画布刷新按 token(当前文件名)守卫:切走的图不把旧 highlight 叠到新图。
- worker `run()` 内异常 `vlog().exception` 记录,不崩线程。
- GUI/线程接线沿用现状不单测(import 冒烟 + 全量 + 人工);纯函数 TDD。
- 全程 `.venv/bin/python` 跑测试。

---

### Task 1: `build_repair15` 改用距离变换(消除卡顿)

**Files:**
- Modify: `labeling_tool/core/derived_masks.py`(`build_repair15` 函数体)
- Test: `labeling_tool/tests/test_derived_masks.py`(追加精度用例)

**Interfaces:**
- Produces: `build_repair15(crack, spalling, px_per_cm) -> np.ndarray`(签名不变;单通道 0/255 填充;两层皆 None → ValueError)。

- [ ] **Step 1: 追加等价/精度守卫测试(行为不变的重构)**

> 说明:这是**性能重构**——距离变换与巨核 dilate 行为等价,故这些测试在改前改后都应通过(等价守卫,非"先红")。它们锁定 0/255、距离阈值、空前景行为不被改动破坏;性能提升本身不做计时单测。

在 `labeling_tool/tests/test_derived_masks.py` 末尾追加:

```python
def test_repair15_distance_accuracy():
    # single foreground pixel; px_per_cm=2 -> pad = round(15*2)=30 px radius
    m = np.zeros((200, 200), np.uint8)
    m[100, 100] = 255
    r = build_repair15(m, None, px_per_cm=2.0)
    assert set(np.unique(r)).issubset({0, 255})
    assert r[100, 100] == 255                      # foreground kept
    assert r[100, 100 + 20] == 255                 # within 30px -> set
    assert r[100, 100 + 60] == 0                   # well beyond 30px -> clear


def test_repair15_empty_foreground_is_blank():
    m = np.zeros((50, 50), np.uint8)               # both layers empty (not None)
    r = build_repair15(m, m, px_per_cm=2.0)
    assert int(r.sum()) == 0
```

- [ ] **Step 2: 运行(等价守卫——改前应已通过)**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q`
Expected: 全部通过(包括两个新用例;旧巨核 dilate 与新距离变换行为等价)。这一步确认守卫测试本身正确;下一步替换实现后应仍全绿。

- [ ] **Step 3: 改写 `build_repair15` 函数体**

把 `labeling_tool/core/derived_masks.py` 的 `build_repair15` 函数(第 58–79 行)整体替换为:

```python
def build_repair15(crack: np.ndarray | None,
                   spalling: np.ndarray | None,
                   px_per_cm: float) -> np.ndarray:
    """Foreground union expanded by round(15*px_per_cm) px, FILLED 0/255.

    Uses a distance transform (O(N), Euclidean) instead of a giant dilation
    kernel, so it stays fast even at large px/cm. Raises ValueError when both
    layers are None.
    """
    cb = _binary(crack)
    sb = _binary(spalling)
    if cb is None and sb is None:
        raise ValueError("build_repair15 requires at least one of crack/spalling")

    shape = cb.shape if cb is not None else sb.shape
    union = np.zeros(shape, dtype=np.uint8)
    if cb is not None:
        union |= cb
    if sb is not None:
        union |= sb
    if int(union.max()) == 0:
        return np.zeros(shape, dtype=np.uint8)

    pad_px = int(round(_REPAIR15_CM * float(px_per_cm)))
    # distance from each pixel to the nearest foreground pixel
    src = np.where(union > 0, np.uint8(0), np.uint8(255))
    dist = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    return np.where(dist <= pad_px, np.uint8(255), np.uint8(0)).astype(np.uint8)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q`
Expected: 全部通过(现有 repair15 用例 0/255、随 px/cm 增长仍成立 + 两个新用例)。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/derived_masks.py labeling_tool/tests/test_derived_masks.py
git commit -m "perf(masks): compute repair15 via distance transform (no giant kernel)"
```

---

### Task 2: `generate_derived_masks` 纯函数(build + 落盘)

**Files:**
- Modify: `labeling_tool/core/derived_masks.py`(追加函数)
- Test: `labeling_tool/tests/test_derived_masks.py`(追加)

**Interfaces:**
- Consumes: `build_highlight`、`build_repair15`。
- Produces: `generate_derived_masks(crack, spalling, px_per_cm, highlight_path, repair15_path) -> tuple[np.ndarray, np.ndarray | None]` —— 生成 highlight(必)与 repair15(`px_per_cm` 为真时);各自 `imwrite` 到对应路径(路径为 None 则跳过写,但仍返回数组);返回 `(highlight, repair15_or_None)`。

- [ ] **Step 1: 追加失败测试**

在 `labeling_tool/tests/test_derived_masks.py` 顶部确保有 `import cv2`、`from pathlib import Path`(若无则加),并追加:

```python
from labeling_tool.core.derived_masks import generate_derived_masks


def test_generate_writes_both_with_scale(tmp_path):
    crack = np.zeros((40, 40), np.uint8); crack[20, 5:35] = 255
    hi_p = tmp_path / "hi.png"
    r15_p = tmp_path / "r15.png"
    hi, r15 = generate_derived_masks(crack, None, 2.0, str(hi_p), str(r15_p))
    assert hi_p.exists() and r15_p.exists()
    assert hi is not None and r15 is not None
    assert set(np.unique(cv2.imread(str(r15_p), cv2.IMREAD_UNCHANGED))).issubset({0, 255})


def test_generate_skips_repair15_without_scale(tmp_path):
    crack = np.zeros((40, 40), np.uint8); crack[20, 5:35] = 255
    hi_p = tmp_path / "hi.png"
    r15_p = tmp_path / "r15.png"
    hi, r15 = generate_derived_masks(crack, None, 0.0, str(hi_p), str(r15_p))
    assert hi_p.exists()
    assert r15 is None and not r15_p.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -k generate -q`
Expected: FAIL — `ImportError: cannot import name 'generate_derived_masks'`

- [ ] **Step 3: 追加函数到 derived_masks.py 末尾**

```python
def generate_derived_masks(crack: np.ndarray | None,
                           spalling: np.ndarray | None,
                           px_per_cm: float,
                           highlight_path,
                           repair15_path
                           ) -> tuple[np.ndarray, np.ndarray | None]:
    """Build the highlight (+ scale-dependent repair15) and write them to disk.

    Returns (highlight, repair15_or_None). repair15 is built+written only when
    px_per_cm is truthy. A None path skips the write but the array is still
    returned (so the canvas can refresh). Callers ensure parent dirs exist.
    """
    highlight = build_highlight(crack, spalling)
    if highlight_path is not None:
        cv2.imwrite(str(highlight_path), highlight)
    repair15 = None
    if px_per_cm:
        repair15 = build_repair15(crack, spalling, px_per_cm)
        if repair15_path is not None:
            cv2.imwrite(str(repair15_path), repair15)
    return highlight, repair15
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_derived_masks.py -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/derived_masks.py labeling_tool/tests/test_derived_masks.py
git commit -m "feat(masks): add generate_derived_masks (build + write helper)"
```

---

### Task 3: 修复光晕颜色(去通道反转)+ 离屏颜色测试

**Files:**
- Modify: `labeling_tool/core/canvas/overlay_painter.py`(`paint_single_color_overlay`)
- Test: `labeling_tool/tests/test_overlay_color.py`(新建)

**Interfaces:**
- `paint_single_color_overlay(painter, viewport, widget_w, widget_h, mask, rgb, alpha=90)` 行为不变,仅修正通道映射使 `rgb` 按 RGB 直序写入。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_overlay_color.py`:

```python
import numpy as np
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.viewport import Viewport
from labeling_tool.core.canvas.overlay_painter import paint_single_color_overlay

_app = QApplication.instance() or QApplication([])


def test_single_color_overlay_renders_yellow():
    w = h = 20
    mask = np.zeros((h, w), np.uint8)
    mask[5:15, 5:15] = 255                      # a covered block

    target = QImage(w, h, QImage.Format_RGBA8888)
    target.fill(0)                              # transparent
    painter = QPainter(target)
    vp = Viewport()
    vp.set_image_size(w, h)
    vp.scale = 1.0
    vp.offset = QPoint(0, 0)
    paint_single_color_overlay(painter, vp, w, h, mask, (255, 255, 0), alpha=255)
    painter.end()

    c = target.pixelColor(10, 10)               # inside the covered block
    assert (c.red(), c.green(), c.blue()) == (255, 255, 0)   # YELLOW, not cyan
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_overlay_color.py -q`
Expected: FAIL —— 当前反转把黄渲染成青,得到 `(0, 255, 255)`。

- [ ] **Step 3: 去掉通道反转**

把 `labeling_tool/core/canvas/overlay_painter.py` 中 `paint_single_color_overlay` 里的:

```python
    rgba[..., 0] = rgb[2]
    rgba[..., 1] = rgb[1]
    rgba[..., 2] = rgb[0]
```

替换为:

```python
    rgba[..., 0] = rgb[0]
    rgba[..., 1] = rgb[1]
    rgba[..., 2] = rgb[2]
```

(只改 `paint_single_color_overlay`;`paint_mask_overlay` 的反转保持不动。)

- [ ] **Step 4: 运行确认通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_overlay_color.py -q`
Expected: PASS(像素为黄)。

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/canvas/overlay_painter.py labeling_tool/tests/test_overlay_color.py
git commit -m "fix(canvas): render highlight halo in yellow (drop channel reversal)"
```

---

### Task 4: 后台 worker `ui/derived_mask_worker.py`

**Files:**
- Create: `labeling_tool/ui/derived_mask_worker.py`

**Interfaces:**
- Consumes: `core.derived_masks.generate_derived_masks`、`logging_setup.vlog`。
- Produces:
  - `DerivedMaskSignals(QObject)`,信号 `done = pyqtSignal(str, object, object)`(token, highlight, repair15|None)。
  - `DerivedMaskRunnable(QRunnable)`,构造 kw:`crack, spalling, px_per_cm, highlight_path, repair15_path, token, signals`;`run()` 调 `generate_derived_masks` 后 `signals.done.emit(...)`;异常 `vlog().exception` 不崩线程。

- [ ] **Step 1: 创建文件**

新建 `labeling_tool/ui/derived_mask_worker.py`:

```python
"""Background generation of the derived (highlight + repair15) masks.

Runs generate_derived_masks off the UI thread via QThreadPool so saving a
large image never freezes the GUI. Emits done(token, highlight, repair15)
back to the UI thread, where the controller refreshes the canvas only if the
token still matches the on-screen image.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from labeling_tool.core.derived_masks import generate_derived_masks
from labeling_tool.logging_setup import vlog


class DerivedMaskSignals(QObject):
    done = pyqtSignal(str, object, object)   # token, highlight, repair15|None


class DerivedMaskRunnable(QRunnable):
    def __init__(self, *, crack, spalling, px_per_cm,
                 highlight_path, repair15_path, token, signals):
        super().__init__()
        self._crack = crack
        self._spalling = spalling
        self._px_per_cm = px_per_cm
        self._highlight_path = highlight_path
        self._repair15_path = repair15_path
        self._token = token
        self._signals = signals

    def run(self):
        try:
            hi, r15 = generate_derived_masks(
                self._crack, self._spalling, self._px_per_cm,
                self._highlight_path, self._repair15_path)
            self._signals.done.emit(self._token, hi, r15)
        except Exception as e:  # noqa: BLE001 - never crash the pool thread
            vlog().exception("derived mask worker failed: %s", e)
```

- [ ] **Step 2: import 冒烟**

Run: `.venv/bin/python -c "from labeling_tool.ui.derived_mask_worker import DerivedMaskSignals, DerivedMaskRunnable; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: 提交**

```bash
git add labeling_tool/ui/derived_mask_worker.py
git commit -m "feat(ui): add DerivedMaskRunnable for off-thread derived-mask gen"
```

---

### Task 5: 主窗口异步派发 + 槽 + closeEvent 同步

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`

**Interfaces:**
- Consumes: `DerivedMaskSignals`/`DerivedMaskRunnable`、`generate_derived_masks`、`QThreadPool`。

- [ ] **Step 1: __init__ 建 signals 并连槽**

在 `MainWindow.__init__`(信号连接附近,如 `self.canvas.mask_edited.connect(...)` 一带,或 `__init__` 末尾)新增:

```python
        from labeling_tool.ui.derived_mask_worker import DerivedMaskSignals
        self._derived_signals = DerivedMaskSignals()
        self._derived_signals.done.connect(self._on_derived_ready)
```

- [ ] **Step 2: `_save_all_artifacts` 增参 + 派生块改为快照派发/同步**

把方法签名(第 298–299 行):

```python
    def _save_all_artifacts(self, silent: bool = False,
                            only_if_edited: bool = False) -> bool:
```

改为:

```python
    def _save_all_artifacts(self, silent: bool = False,
                            only_if_edited: bool = False,
                            async_derived: bool = True) -> bool:
```

把派生掩膜块(第 334–358 行,从 `# ----- 1b. Derived masks` 到 `self.canvas.set_repair15(None)` 那段)整体替换为:

```python
            # ----- 1b. Derived masks: highlight + (scale-dependent) repair15 --
            # Heavy on big panoramas, so snapshot the layers and run off the UI
            # thread (closeEvent uses async_derived=False to flush synchronously).
            if self.highlight_dir is not None:
                self.highlight_dir.mkdir(parents=True, exist_ok=True)
            if self.repair15_dir is not None:
                self.repair15_dir.mkdir(parents=True, exist_ok=True)
            hi_path = (str(self.highlight_dir / mask_store.mask_name(filename))
                       if self.highlight_dir is not None else None)
            r15_path = (str(self.repair15_dir / mask_store.mask_name(filename))
                        if self.repair15_dir is not None else None)
            crack_snap = mc.copy() if mc is not None else None
            spall_snap = ms.copy() if ms is not None else None
            scale = self.current_scale or 0.0
            if async_derived:
                from PyQt5.QtCore import QThreadPool
                from labeling_tool.ui.derived_mask_worker import DerivedMaskRunnable
                QThreadPool.globalInstance().start(DerivedMaskRunnable(
                    crack=crack_snap, spalling=spall_snap, px_per_cm=scale,
                    highlight_path=hi_path, repair15_path=r15_path,
                    token=filename, signals=self._derived_signals))
            else:
                from labeling_tool.core.derived_masks import generate_derived_masks
                hi, r15 = generate_derived_masks(
                    crack_snap, spall_snap, scale, hi_path, r15_path)
                self.canvas.set_highlight(hi)
                self.canvas.set_repair15(r15)
```

(注:删除了原块里 `from ... import build_highlight, build_repair15`、`try/except ValueError`、内联 imwrite 与 `set_highlight/set_repair15`——这些现由 worker/同步分支与 generate_derived_masks 承担。`import cv2 as _cv2` 仍用于上面第 1 节 mask 落盘,保留。)

- [ ] **Step 3: 加 `_on_derived_ready` 槽**

在 `_save_all_artifacts` 方法之后(或 BBox callbacks 之前)新增:

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
```

- [ ] **Step 4: closeEvent 走同步派生**

把 `closeEvent`(第 690–694 行)里的:

```python
        self._save_all_artifacts(silent=True, only_if_edited=True)
```

改为:

```python
        self._save_all_artifacts(silent=True, only_if_edited=True,
                                 async_derived=False)
```

- [ ] **Step 5: import 冒烟 + 全量**

Run: `.venv/bin/python -c "import labeling_tool.app; import labeling_tool.core.window.main_window; print('ok')"`
Expected: 输出 `ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(GUI 路径无单测,改动不破坏现有)。

- [ ] **Step 6: 离屏冒烟(同步 + 异步路径不崩)**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import numpy as np, tempfile, os, time
from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.ui.derived_mask_worker import DerivedMaskSignals, DerivedMaskRunnable
d = tempfile.mkdtemp()
got = []
sig = DerivedMaskSignals(); sig.done.connect(lambda t,h,r: got.append((t, h is not None, r is not None)))
crack = np.zeros((60,60), np.uint8); crack[30,10:50]=255
QThreadPool.globalInstance().start(DerivedMaskRunnable(
    crack=crack, spalling=None, px_per_cm=2.0,
    highlight_path=os.path.join(d,"hi.png"), repair15_path=os.path.join(d,"r15.png"),
    token="stitched_1.jpg", signals=sig))
QThreadPool.globalInstance().waitForDone(5000)
app.processEvents()
assert got and got[0]==("stitched_1.jpg", True, True), got
assert os.path.exists(os.path.join(d,"hi.png")) and os.path.exists(os.path.join(d,"r15.png"))
print("worker offscreen ok:", got)
PY
```
Expected: `worker offscreen ok: [('stitched_1.jpg', True, True)]`

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/core/window/main_window.py
git commit -m "perf(ui): generate derived masks off the UI thread; sync on close"
```

---

### Task 6: GUI 冒烟(人工)

**Files:** 无(仅运行验证)

- [ ] **Step 1: 启动并实测**

Run: `DISPLAY=:1 .venv/bin/python -m labeling_tool.app`
- 离线打开 session_18,画裂缝 + 设比例尺,**保存**:界面**不卡顿**(派生在后台);稍后光晕/15cm 自动出现。
- 「显示 하이라이트」→ **黄色**光晕(不是青色);「显示 15cm」→ 青色外轮廓。
- **切换图片**:不卡顿,且切走前的编辑被自动保存(回切能看到保存结果)。
- 确认 `data/session_18/HighLight/`、`Repair15/` 文件写出。

---

## Self-Review

**Spec coverage:**
- 颜色去反转 + 离屏断言 → Task 3 ✅
- repair15 距离变换加速 → Task 1 ✅
- generate_derived_masks 纯函数 → Task 2 ✅
- worker(QRunnable+Signals)→ Task 4 ✅
- 主窗口快照派发 + token 守卫刷新 + closeEvent 同步 → Task 5 ✅
- 切图卡顿(随派生异步化一并解决)→ Task 5 ✅
- 测试(distance 精度 / generate / 颜色 / worker 离屏)→ Task 1/2/3/5 ✅

**Placeholder scan:** 无 TBD/TODO;每个改代码 step 均含完整代码或精确行号替换。

**Type consistency:** `generate_derived_masks(crack, spalling, px_per_cm, highlight_path, repair15_path) -> (hi, r15|None)` 在 Task 2 定义,Task 4(worker)与 Task 5(同步分支)消费一致;`DerivedMaskSignals.done(str, object, object)` 与 `_on_derived_ready(token, hi, r15)` 一致;`DerivedMaskRunnable(crack=,spalling=,px_per_cm=,highlight_path=,repair15_path=,token=,signals=)` 在 Task 4 定义、Task 5 同 kw 调用;`build_repair15` 签名不变。

**说明:** repair15 距离变换对空前景短路返回全 0;`dist <= pad_px` 含前景(dist=0),与"填充 15cm 区域"语义一致;maskSize 5 的 DIST_L2 为近似欧氏,测试用安全余量(20px 内置位、60px 外清零,pad=30)避免边界抖动。
