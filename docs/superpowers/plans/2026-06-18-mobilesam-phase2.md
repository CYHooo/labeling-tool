# MobileSAM Phase 2 (画布 SAM 模式 + UI 接线) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 1 的 `MobileSamPredictor` 接进 GUI:新增「SAM 분할」画布模式(迭代点选 → 实时预览 → 확정 写入 spalling),并做依赖/模型缺失时的防御性退化。

**Architecture:** 画布 `ImageCanvas` 新增 `sam_mode` 与点/预览状态,通过注入的 predictor 做推理;`ViewerMainWindow` 在启动时尝试构造 predictor(模型/onnxruntime 缺失则置 None),注入画布并据此启用/置灰 SAM 开关。SAM 只产出 spalling 像素,下游(保存/上传/计测)零改动。

**Tech Stack:** PyQt5、NumPy、OpenCV;Phase 1 的 `labeling_tool.core.sam.predictor.MobileSamPredictor`;onnxruntime(运行时,惰性)。

## Global Constraints
- 输出**仅写入** `brush_mask_spalling`(spalling=2 由现有 codec 处理);不碰 crack。
- 模式互斥:`sam_mode` 与 `brush_mode`/`bbox_mode`/`measure_mode` 互斥(开一个关其余),沿用现有「打开时把别的 toggle `setChecked(False)`」模式。
- 编码器**懒加载**:仅在某张图首次 SAM 点击时 `predictor.set_image(origin_bgr)`;切图清空 SAM 状态。
- 交互:左键=正点(label 1)、右键=负点(label 0),每次点击后 `predict` 刷新预览;「확정」把 `_sam_preview>0` OR 进 spalling 并 `mask_edited.emit()`;「취소」只清空。
- 预览叠加为**半透明绿色**(表示将成为 spalling);正点画绿点、负点画红点。
- 防御退化:`onnxruntime` 未装或 `models/sam/*.onnx` 缺失 → predictor=None → SAM 开关**置灰 + tooltip**,其余功能照常,绝不崩溃。
- 模型路径:`labeling_tool/models/sam/mobile_sam_encoder.onnx`、`mobile_sam_decoder.onnx`(相对包目录解析)。
- i18n 键三语(en/zh/ko),与现有 `core/i18n.py` 三个字典对齐。
- TDD:画布逻辑用注入的 fake predictor 离屏单测(`QT_QPA_PLATFORM=offscreen`);UI/接线用 import 冒烟 + 离屏构造;真实模型效果由用户人工冒烟。`.venv/bin/python` 跑测试,全量基线 113。

---

### Task 1: 画布 SAM 模式(状态 + 交互 + 预览渲染)

**Files:**
- Modify: `labeling_tool/core/canvas/image_canvas.py`
- Test: `labeling_tool/tests/test_sam_canvas.py`

**Interfaces:**
- Consumes: 注入对象需有 `set_image(bgr)` 与 `predict(points_xy, labels) -> np.ndarray(uint8 0/255, HxW)`(Phase 1 的 `MobileSamPredictor`,或测试用 fake)。
- Produces:
  - 画布属性 `sam_mode: bool`、`_origin_bgr: np.ndarray|None`、`_sam_points: list[tuple[int,int]]`、`_sam_labels: list[int]`、`_sam_preview: np.ndarray|None`、`_sam_predictor`、`_sam_image_set: bool`。
  - 方法 `set_sam_predictor(predictor)`、`set_sam_mode(enabled: bool)`、`commit_sam() -> bool`、`cancel_sam()`、`has_sam_preview() -> bool`。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_sam_canvas.py`:

```python
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


class _FakePredictor:
    """Returns a fixed block mask; records that set_image ran once."""
    def __init__(self):
        self.set_image_calls = 0
        self.last_points = None

    def set_image(self, bgr):
        self.set_image_calls += 1
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        self.last_points = (list(points), list(labels))
        h, w = self._hw
        m = np.zeros((h, w), np.uint8)
        m[10:20, 10:30] = 255
        return m


class _LeftClick:
    def __init__(self, x, y):
        self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y
    def button(self): return Qt.LeftButton
    def modifiers(self): return Qt.NoModifier


class _RightClick(_LeftClick):
    def button(self): return Qt.RightButton


def _canvas():
    c = ImageCanvas()
    c.resize(120, 80)
    c.set_image(np.full((80, 120, 3), 50, np.uint8), None, None)
    return c


def test_sam_first_click_sets_image_then_predicts():
    c = _canvas()
    pred = _FakePredictor()
    c.set_sam_predictor(pred)
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))     # image coords ~ widget coords here
    assert pred.set_image_calls == 1          # lazy encode on first click
    assert c.has_sam_preview()
    assert c._sam_labels[-1] == 1             # left = foreground


def test_sam_right_click_is_background_point():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.mousePressEvent(_RightClick(40, 40))
    assert c._sam_labels == [1, 0]
    assert c._sam_predictor.set_image_calls == 1   # not re-encoded on 2nd click


def test_commit_writes_into_spalling_only():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    edited = []
    c.mask_edited.connect(lambda: edited.append(1))
    ok = c.commit_sam()
    assert ok
    assert int((c.brush_mask_spalling > 0).sum()) == 10 * 20   # the block
    assert int((c.brush_mask_crack > 0).sum()) == 0            # crack untouched
    assert not c.has_sam_preview()                             # cleared after commit
    assert edited                                              # mask_edited emitted


def test_cancel_clears_without_writing():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.cancel_sam()
    assert not c.has_sam_preview()
    assert int((c.brush_mask_spalling > 0).sum()) == 0


def test_image_switch_clears_sam_state():
    c = _canvas()
    c.set_sam_predictor(_FakePredictor())
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))
    c.set_image(np.full((80, 120, 3), 70, np.uint8), None, None)
    assert not c.has_sam_preview()
    assert c._sam_points == [] and c._sam_image_set is False


def test_sam_noop_without_predictor():
    c = _canvas()                              # no predictor injected
    c.set_sam_mode(True)
    c.mousePressEvent(_LeftClick(15, 15))      # must not raise
    assert not c.has_sam_preview()
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_sam_canvas.py -q`
Expected: FAIL — `AttributeError: 'ImageCanvas' object has no attribute 'set_sam_predictor'`(或类似)。

- [ ] **Step 3: 加 SAM 状态(__init__)**

在 `image_canvas.py` 的 `__init__`,紧接现有 derived-mask 状态块之后(`self.show_repair15: bool = False` 那几行后)加入:

```python
        # ----- SAM (MobileSAM point-select for spalling) -----
        self.sam_mode: bool = False
        self._sam_predictor = None                 # injected; None = unavailable
        self._origin_bgr: np.ndarray | None = None  # kept for predictor.set_image
        self._sam_points: list[tuple[int, int]] = []
        self._sam_labels: list[int] = []
        self._sam_preview: np.ndarray | None = None
        self._sam_image_set: bool = False           # encoder run for current image
```

- [ ] **Step 4: set_image 保存原图 BGR + 清空 SAM 状态**

在 `set_image` 方法里,把 `self._pixmap = numpy_to_qpixmap(origin_bgr)` 这一行下面补一行保存原图:

```python
        self._pixmap = numpy_to_qpixmap(origin_bgr)
        self._origin_bgr = origin_bgr.copy()
```

并在 `set_image` 末尾的清理块(`self.repair15_contours = None` 之后、`self._touch_mask()` 之前)加入 SAM 清理:

```python
        self.repair15_contours = None
        self._clear_sam_state()
        self._touch_mask()
```

- [ ] **Step 5: 加 SAM 方法(public API 区,放在 set_measure_mode 之后)**

```python
    def set_sam_predictor(self, predictor) -> None:
        """Inject the MobileSAM predictor (None when unavailable)."""
        self._sam_predictor = predictor

    def set_sam_mode(self, enabled: bool) -> None:
        self.sam_mode = bool(enabled)
        if not enabled:
            self._clear_sam_state()
        self.update()

    def _clear_sam_state(self) -> None:
        self._sam_points = []
        self._sam_labels = []
        self._sam_preview = None
        self._sam_image_set = False

    def has_sam_preview(self) -> bool:
        return self._sam_preview is not None

    def _sam_add_point(self, ix: int, iy: int, label: int) -> None:
        if self._sam_predictor is None or self._origin_bgr is None:
            return
        if not self._sam_image_set:
            self._sam_predictor.set_image(self._origin_bgr)   # lazy encode
            self._sam_image_set = True
        self._sam_points.append((int(ix), int(iy)))
        self._sam_labels.append(int(label))
        try:
            self._sam_preview = self._sam_predictor.predict(
                self._sam_points, self._sam_labels)
        except Exception:
            from labeling_tool.logging_setup import vlog
            vlog().exception("SAM predict failed")
            self._sam_preview = None
        self.update()

    def commit_sam(self) -> bool:
        """OR the preview into the spalling layer; returns True if anything written."""
        if self._sam_preview is None or self.brush_mask_spalling is None:
            return False
        self.brush_mask_spalling[self._sam_preview > 0] = 255
        self._clear_sam_state()
        self._touch_mask()
        self.mask_edited.emit()
        self.update()
        return True

    def cancel_sam(self) -> None:
        self._clear_sam_state()
        self.update()
```

- [ ] **Step 6: mousePressEvent 加 SAM 分支(排在 measure/bbox/brush 之前)**

在 `mousePressEvent` 里,Ctrl-pan 那段 `return` 之后、`if self.measure_mode:` 之前插入:

```python
        if self.sam_mode:
            if event.button() == Qt.LeftButton:
                self._sam_add_point(ix, iy, 1)     # foreground
            elif event.button() == Qt.RightButton:
                self._sam_add_point(ix, iy, 0)     # background
            return
```

- [ ] **Step 7: paintEvent 画 SAM 预览(绿色叠加 + 点标记)**

在 `paintEvent` 中,repair15 叠加块之后、bbox overlay 之前,插入:

```python
        if (self._pixmap is not None and self.sam_mode
                and self._sam_preview is not None):
            from labeling_tool.core.canvas.overlay_painter import (
                paint_single_color_overlay,
            )
            paint_single_color_overlay(
                painter, self.viewport, self.width(), self.height(),
                self._sam_preview, (60, 220, 90), alpha=110)
            self._paint_sam_points(painter)
```

并新增渲染辅助(放在 `_paint_repair15` 附近):

```python
    def _paint_sam_points(self, painter: QPainter):
        from PyQt5.QtGui import QColor, QPen
        from PyQt5.QtCore import QPointF
        for (ix, iy), lab in zip(self._sam_points, self._sam_labels):
            wx, wy = self.viewport.image_to_widget(ix, iy)
            color = QColor(60, 220, 90) if lab == 1 else QColor(230, 70, 70)
            painter.setPen(QPen(QColor(20, 20, 20), 2))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(wx, wy), 5, 5)
```

> 注:`paint_single_color_overlay(painter, viewport, widget_w, widget_h, mask, rgb, alpha)` 与 `viewport.image_to_widget(ix, iy)` 均为现有 API(highlight/measure 已用)。若 `image_to_widget` 名称不符,读 `viewport` 模块确认对应方法并使用之。

- [ ] **Step 8: 运行确认通过 + 全量**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_sam_canvas.py -q`
Expected: PASS(6 passed)

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(≥119)。

- [ ] **Step 9: 提交**

```bash
git add labeling_tool/core/canvas/image_canvas.py labeling_tool/tests/test_sam_canvas.py
git commit -m "feat(sam): canvas SAM mode — iterative points, preview, commit into spalling"
```

---

### Task 2: UI 接线(SAM 开关 + 확정/취소 + 互斥 + i18n + 样式)

**Files:**
- Modify: `labeling_tool/core/window/ui_builder.py`
- Modify: `labeling_tool/core/window/main_window.py`
- Modify: `labeling_tool/core/window/styles.py`
- Modify: `labeling_tool/core/i18n.py`

**Interfaces:**
- Consumes: Task 1 的 `canvas.set_sam_mode(bool)`、`canvas.commit_sam()`、`canvas.cancel_sam()`、`canvas.sam_mode`。
- Produces: `window._btn_sam_toggle`(checkable, objectName `samToggle`)、`window._btn_sam_commit`、`window._btn_sam_cancel`;handlers `_on_sam_toggle`、`_on_sam_commit`、`_on_sam_cancel`。

- [ ] **Step 1: ui_builder 加 SAM 控件**

在 `build_category_group`(类别组,crack/spalling 按钮之后、`return window._grp_category` 之前)追加 SAM 控件;若该函数结构不便,改为在画笔组 `gbr` 末尾追加。插入:

```python
    window._btn_sam_toggle = QPushButton(window.tr_("btn_sam"))
    window._btn_sam_toggle.setObjectName("samToggle")
    window._btn_sam_toggle.setCheckable(True)
    window._btn_sam_toggle.toggled.connect(window._on_sam_toggle)
    window._btn_sam_commit = QPushButton(window.tr_("btn_sam_commit"))
    window._btn_sam_commit.clicked.connect(window._on_sam_commit)
    window._btn_sam_cancel = QPushButton(window.tr_("btn_sam_cancel"))
    window._btn_sam_cancel.clicked.connect(window._on_sam_cancel)
    window._btn_sam_commit.setEnabled(False)
    window._btn_sam_cancel.setEnabled(False)
```

并把这三个控件 `addWidget` 进所在组的布局(紧随类别/画笔控件,使用该组现有的 layout 变量,如 `gc` 或 `gbr`):

```python
    gc.addWidget(window._btn_sam_toggle)
    sam_row = QHBoxLayout()
    sam_row.addWidget(window._btn_sam_commit)
    sam_row.addWidget(window._btn_sam_cancel)
    gc.addLayout(sam_row)
```

> 读该函数确认 layout 变量名(`build_category_group` 用 `gc = QHBoxLayout(...)`;若是水平布局不便加行,可改用所在组的垂直布局或画笔组 `gbr`)。`QHBoxLayout` 已在 ui_builder 顶部导入。

- [ ] **Step 2: main_window 加 SAM handlers + 互斥**

在 `core/window/main_window.py` 的 Brush callbacks 区附近,新增:

```python
    def _on_sam_toggle(self, checked: bool):
        # Mutually exclusive with brush / bbox / measure.
        if checked:
            if self.canvas.brush_mode:
                self._btn_brush_toggle.setChecked(False)
            if self.canvas.bbox_mode:
                self._btn_bbox_toggle.setChecked(False)
            if self._btn_measure.isChecked():
                self._btn_measure.setChecked(False)
        self.canvas.set_sam_mode(bool(checked))
        self._btn_sam_commit.setEnabled(bool(checked))
        self._btn_sam_cancel.setEnabled(bool(checked))
        if checked:
            self.status.showMessage(self.tr_("sam_hint"))

    def _on_sam_commit(self):
        if self.canvas.commit_sam():
            self.status.showMessage(self.tr_("sam_committed"))

    def _on_sam_cancel(self):
        self.canvas.cancel_sam()
```

并在现有 `_on_brush_toggle`、`_on_bbox_toggle`、`_on_measure_toggle` 三个 handler 的「开启时关掉其它模式」分支里,各加一行关掉 SAM(与它们关掉彼此的写法一致):

```python
            if self.canvas.sam_mode:
                self._btn_sam_toggle.setChecked(False)
```

- [ ] **Step 3: retranslate 加 SAM 文案**

在 `core/window/main_window.py` 的 retranslate 里(brush 文案附近),加:

```python
        self._btn_sam_toggle.setText(self.tr_("btn_sam"))
        self._btn_sam_commit.setText(self.tr_("btn_sam_commit"))
        self._btn_sam_cancel.setText(self.tr_("btn_sam_cancel"))
```

- [ ] **Step 4: i18n 三语键**

在 `core/i18n.py` 的 **三个**语言字典(en / zh / ko)里各加 5 个键(放在画笔相关键附近),值如下:

en:
```python
        "btn_sam":         "SAM segment (spalling)",
        "btn_sam_commit":  "Confirm (write spalling)",
        "btn_sam_cancel":  "Cancel",
        "sam_hint":        "Left-click = include, right-click = exclude; Confirm writes the region to spalling.",
        "sam_committed":   "SAM region written to spalling.",
```
zh:
```python
        "btn_sam":         "SAM 分割 (剥离)",
        "btn_sam_commit":  "确认 (写入剥离)",
        "btn_sam_cancel":  "取消",
        "sam_hint":        "左键=加入、右键=排除;确认将区域写入剥离层。",
        "sam_committed":   "SAM 区域已写入剥离层。",
```
ko:
```python
        "btn_sam":         "SAM 분할 (박리)",
        "btn_sam_commit":  "확정 (박리 기록)",
        "btn_sam_cancel":  "취소",
        "sam_hint":        "좌클릭=포함, 우클릭=제외; 확정 시 영역을 박리로 기록합니다.",
        "sam_committed":   "SAM 영역을 박리에 기록했습니다.",
```

> zh 的 commit/cancel 文案修正为中文:`"确认 (写入剥离)"` / `"取消"`(上面的 zh 块请用这两个中文值,不要韩文)。

- [ ] **Step 5: styles 加 SAM 开关选中态**

在 `core/window/styles.py` 现有 toggle 选中态附近加:

```python
        QPushButton#samToggle:checked {
            background-color: #2a9d8f;
            border-color: #2a9d8f;
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#samToggle:checked:hover { background-color: #33b3a3; }
```

- [ ] **Step 6: import 冒烟 + 全量**

Run: `.venv/bin/python -c "import labeling_tool.app, labeling_tool.core.window.ui_builder; print('import ok')"`
Expected: `import ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过(无回归)。

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/core/window/ui_builder.py labeling_tool/core/window/main_window.py labeling_tool/core/window/styles.py labeling_tool/core/i18n.py
git commit -m "feat(sam): UI — SAM toggle + confirm/cancel, mutual exclusion, i18n, style"
```

---

### Task 3: Predictor 构造 + 注入 + 防御退化

**Files:**
- Modify: `labeling_tool/core/sam/predictor.py`(加 `default_model_paths()` / `available()` 辅助)
- Modify: `labeling_tool/ui/main_window.py`(构造 predictor、注入画布、缺失则置灰 SAM 开关)
- Test: `labeling_tool/tests/test_sam_predictor.py`(加 helper 测试)

**Interfaces:**
- Consumes: Task 1 的 `canvas.set_sam_predictor(predictor)`;Task 2 的 `window._btn_sam_toggle`。
- Produces: `predictor.default_model_paths() -> tuple[Path, Path]`、`predictor.models_available() -> bool`;`MobileSamPredictor.try_load() -> MobileSamPredictor | None`。

- [ ] **Step 1: 写失败测试(helper)**

在 `labeling_tool/tests/test_sam_predictor.py` 末尾追加:

```python
def test_default_model_paths_point_into_models_sam():
    from labeling_tool.core.sam import predictor as P
    enc, dec = P.default_model_paths()
    assert enc.name == "mobile_sam_encoder.onnx"
    assert dec.name == "mobile_sam_decoder.onnx"
    assert enc.parent.name == "sam" and enc.parent.parent.name == "models"


def test_try_load_returns_none_when_models_missing(tmp_path):
    from labeling_tool.core.sam.predictor import MobileSamPredictor
    missing_enc = tmp_path / "nope_enc.onnx"
    missing_dec = tmp_path / "nope_dec.onnx"
    assert MobileSamPredictor.try_load(missing_enc, missing_dec) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_predictor.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'default_model_paths'`

- [ ] **Step 3: 实现 helper(predictor.py)**

在 `predictor.py` 顶部 import 区加 `from pathlib import Path`,并在文件末尾(类之后)加:

```python
def default_model_paths() -> tuple[Path, Path]:
    """(encoder, decoder) ONNX paths under labeling_tool/models/sam/."""
    base = Path(__file__).resolve().parent.parent.parent / "models" / "sam"
    return base / "mobile_sam_encoder.onnx", base / "mobile_sam_decoder.onnx"


def models_available() -> bool:
    enc, dec = default_model_paths()
    return enc.exists() and dec.exists()
```

并给 `MobileSamPredictor` 加类方法(放在 `from_paths` 之后):

```python
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
```

> `core/sam/predictor.py` 路径:`__file__` = `.../labeling_tool/core/sam/predictor.py`,`parent.parent.parent` = `.../labeling_tool`,故 `/models/sam` 正确。

- [ ] **Step 4: 运行确认通过**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_sam_predictor.py -q`
Expected: PASS(原有 + 2 新 = 7 passed)

- [ ] **Step 5: ViewerMainWindow 构造 + 注入 + 退化**

在 `labeling_tool/ui/main_window.py` 的 `__init__` 末尾(`self._add_upload_button()` 之后)加:

```python
        self._init_sam()

    def _init_sam(self):
        """Load the MobileSAM predictor and wire it to the canvas; if it's
        unavailable (onnxruntime/models missing), disable the SAM toggle."""
        from labeling_tool.core.sam.predictor import MobileSamPredictor
        predictor = None
        try:
            predictor = MobileSamPredictor.try_load()
        except Exception:
            predictor = None
        self.canvas.set_sam_predictor(predictor)
        btn = getattr(self, "_btn_sam_toggle", None)
        if btn is not None and predictor is None:
            btn.setEnabled(False)
            btn.setToolTip(self.tr_("sam_unavailable"))
```

并在 `core/i18n.py` 三个字典各加一键:
- en: `"sam_unavailable": "SAM unavailable (onnxruntime or models/sam/*.onnx missing).",`
- zh: `"sam_unavailable": "SAM 不可用(缺 onnxruntime 或 models/sam/*.onnx)。",`
- ko: `"sam_unavailable": "SAM 사용 불가 (onnxruntime 또는 models/sam/*.onnx 없음).",`

- [ ] **Step 6: 离屏构造冒烟 + 全量**

Run（验证注入 + 模型存在时 predictor 非 None,SAM 开关可用）:
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.core.window.styles import STYLESHEET
app.setStyleSheet(STYLESHEET)
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
ws = Workspace.default(18); ws.ensure()
w = ViewerMainWindow(ws, Manifest(session_id=18, base="x"), None)
print("predictor injected:", w.canvas._sam_predictor is not None)
print("sam toggle enabled:", w._btn_sam_toggle.isEnabled())
PY
```
Expected: 两行均为 `True`(models/sam/*.onnx 已在仓库)。

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全部通过。

- [ ] **Step 7: 提交**

```bash
git add labeling_tool/core/sam/predictor.py labeling_tool/ui/main_window.py labeling_tool/core/i18n.py labeling_tool/tests/test_sam_predictor.py
git commit -m "feat(sam): load predictor from models/sam + inject into canvas, graceful disable"
```

---

## Self-Review

**Spec coverage(spec §3、§4):**
- 画布 sam_mode + 点/预览状态 + set_sam_mode/set_sam_predictor → Task 1 ✅
- mousePress 左正/右负、懒加载 set_image、predict 刷新预览 → Task 1 ✅
- paintEvent 绿色预览 + 点标记 → Task 1 ✅
- commit 写入 brush_mask_spalling + mask_edited;cancel 清空;切图清空 → Task 1 ✅
- UI SAM 开关 + 확정/취소 + 互斥 + i18n + 选中态样式 → Task 2 ✅
- predictor 构造/注入/缺失置灰退化 → Task 3 ✅
- 仅写 spalling、下游不改 → Task 1 测试断言 crack 不变 ✅

**Placeholder scan:** 无 TBD;每个改代码 step 均给完整代码。少数"读该文件确认 layout 变量名/方法名"是因 ui_builder 分组/viewport API 名需就地核对,已给出确认指引与现有 API 名(`paint_single_color_overlay`、`image_to_widget`)。

**Type consistency:** `set_sam_predictor`/`set_sam_mode`/`commit_sam`/`cancel_sam`/`has_sam_preview`、`default_model_paths`/`models_available`/`try_load`、`_btn_sam_toggle`/`_btn_sam_commit`/`_btn_sam_cancel` 跨任务一致。注入对象契约 `set_image(bgr)`+`predict(points,labels)->uint8` 与 Phase 1 `MobileSamPredictor` 一致。

**已知需就地核对项(非缺陷):** ui_builder 分组 layout 变量名(`build_category_group` 用 `gc`)。`viewport.image_to_widget(ix,iy)->tuple` 已确认存在(measure/aruco 渲染用 `QPointF(*self.viewport.image_to_widget(...))`),Task 1 Step 7 据此实现。
