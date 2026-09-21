# 独立离线文件夹标注版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `standalone-local-labeler` 分支上做一个精简本地版:选 image+mask 两文件夹、去登录/API/上传/highlight/15cm,其余(画笔/bbox/SAM/比例尺)与当前一致。

**Architecture:** core `MainWindow` 抽 3 个行为不变的可重写钩子(图片列表/掩膜加载路径/掩膜保存路径);`LocalMainWindow(MainWindow)` 重写它们走"文件夹+stem+.png"约定,禁用派生/Result、注入 SAM、无 API;文件夹对话框 + `app_local.py` 入口。在线版(ViewerMainWindow)行为完全不变。

**Tech Stack:** PyQt5、NumPy、OpenCV、onnxruntime(MobileSAM ONNX)。

## Global Constraints
- 类别与当前一致:整数标签 PNG(0 背景/1 crack/2 spalling),复用 `encode_label_mask`/`decode_mask`。
- 配对:同 stem 不同后缀,mask 取该 stem 下图片(优先 `.png`)。保存 `output/<stem>.png`(非破坏)。
- 输出默认 `<image父目录>/Labeling/`。
- core 改动**行为不变**:仅抽取方法 + 改调用点,默认返回原路径/原列表;在线版不受影响。
- 保留 bbox/SAM/比例尺;highlight/15cm 优雅无效化(不设目录)。
- TDD;`.venv/bin/python`;GUI 测试用 `QT_QPA_PLATFORM=offscreen`。全量基线 163。全部工作在分支 `standalone-local-labeler`(已 checkout)。

---

### Task 1: `pair_by_stem` / `mask_for_stem` 纯函数

**Files:**
- Create: `labeling_tool/session/local_pairing.py`
- Test: `labeling_tool/tests/test_local_pairing.py`

**Interfaces:**
- Produces: `mask_for_stem(mask_dir, stem) -> Path|None`;`pair_by_stem(image_dir, mask_dir) -> list[tuple[str, Path|None]]`。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_local_pairing.py`:

```python
from labeling_tool.session.local_pairing import pair_by_stem, mask_for_stem


def _touch(p):
    p.write_bytes(b"x")


def test_pairs_same_stem_png(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "foo.jpg"); _touch(msk / "foo.png")
    pairs = pair_by_stem(img, msk)
    assert pairs == [("foo.jpg", msk / "foo.png")]


def test_missing_mask_is_none(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "bar.jpg")
    assert pair_by_stem(img, msk) == [("bar.jpg", None)]


def test_png_preferred_and_sorted(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    _touch(img / "b.jpg"); _touch(img / "a.jpg")
    _touch(msk / "a.png"); _touch(msk / "a.bmp"); _touch(msk / "b.bmp")
    pairs = pair_by_stem(img, msk)
    assert [n for n, _ in pairs] == ["a.jpg", "b.jpg"]      # sorted
    assert pairs[0][1] == msk / "a.png"                     # png preferred
    assert pairs[1][1] == msk / "b.bmp"


def test_mask_for_stem_none(tmp_path):
    assert mask_for_stem(tmp_path, "nope") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_local_pairing.py -q`
Expected: FAIL — `ModuleNotFoundError: ... local_pairing`

- [ ] **Step 3: 实现**

新建 `labeling_tool/session/local_pairing.py`:

```python
"""Pair image files with same-stem mask files across two folders (offline
folder-based labeling). Mask is any image file sharing the stem, .png preferred."""

from __future__ import annotations

from pathlib import Path

from labeling_tool.core.constants import IMAGE_EXTENSIONS


def mask_for_stem(mask_dir, stem: str) -> Path | None:
    """The mask in mask_dir matching `stem` (.png preferred, else any image ext)."""
    mask_dir = Path(mask_dir)
    png = mask_dir / f"{stem}.png"
    if png.exists():
        return png
    for ext in sorted(IMAGE_EXTENSIONS):
        p = mask_dir / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def pair_by_stem(image_dir, mask_dir) -> list[tuple[str, Path | None]]:
    """(image_filename, mask_path|None) for each image in image_dir, sorted by name."""
    image_dir = Path(image_dir)
    out: list[tuple[str, Path | None]] = []
    for f in sorted(image_dir.iterdir(), key=lambda p: p.name):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
            out.append((f.name, mask_for_stem(mask_dir, f.stem)))
    return out
```

- [ ] **Step 4: 通过 + 全量**

Run: `.venv/bin/python -m pytest labeling_tool/tests/test_local_pairing.py -q`
Expected: PASS(4 passed)

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全量通过(≥163)。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/session/local_pairing.py labeling_tool/tests/test_local_pairing.py
git commit -m "feat(local): pair_by_stem/mask_for_stem for folder-based labeling"
```

---

### Task 2: core `MainWindow` 可重写钩子(behavior-preserving)

**Files:**
- Modify: `labeling_tool/core/window/main_window.py`
- Test: `labeling_tool/tests/test_mainwindow_hooks.py`

**Interfaces:**
- Produces(可重写,默认=现有行为):`_build_image_list() -> list[str]`;`_display_mask_path(filename) -> tuple[str|None, str]`;`_save_mask_path(filename) -> Path`。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_mainwindow_hooks.py`:

```python
from pathlib import Path
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.window.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _win():
    return MainWindow()


def test_default_save_mask_path(tmp_path):
    w = _win(); w.output_dir = tmp_path
    assert w._save_mask_path("foo.jpg") == tmp_path / "foo_mask.png"


def test_default_build_image_list(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "note.txt").write_bytes(b"x")
    w = _win(); w.origin_dir = tmp_path
    assert w._build_image_list() == ["a.jpg", "b.png"]


def test_default_display_mask_path_finds_labeling(tmp_path):
    lab = tmp_path / "Labeling"; det = tmp_path / "Detected"
    lab.mkdir(); det.mkdir()
    (lab / "foo_mask.png").write_bytes(b"x")
    w = _win(); w.output_dir = lab; w.detected_dir = det
    path, source = w._display_mask_path("foo.jpg")
    assert path == str(lab / "foo_mask.png")
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_mainwindow_hooks.py -q`
Expected: FAIL — `AttributeError: ... _save_mask_path`

- [ ] **Step 3: 抽取钩子 + 改调用点**

在 `labeling_tool/core/window/main_window.py`:

(a) `_load_data` 里,把
```python
        files = sorted([
            f.name for f in self.origin_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ])
```
改为
```python
        files = self._build_image_list()
```
并在 `_load_data` 方法之后新增:
```python
    def _build_image_list(self) -> list[str]:
        """Filenames to list. Default: images in origin_dir. Overridable."""
        return sorted([
            f.name for f in self.origin_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ])
```

(b) `_show_image` 里,把
```python
        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        mask_path = str(resolved) if resolved is not None else None
```
改为
```python
        mask_path, source = self._display_mask_path(filename)
```
并新增方法(放在 `_show_image` 之后或 `_save_mask_path` 旁):
```python
    def _display_mask_path(self, filename: str) -> tuple[str | None, str]:
        """(mask_path|None, source) to display. Default: Labeling then Detected
        via <stem>_mask.png. Overridable."""
        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        return (str(resolved) if resolved is not None else None), source
```

(c) `_save_all_artifacts` 里,把
```python
            mask_out = self.output_dir / mask_store.mask_name(filename)
```
改为
```python
            mask_out = self._save_mask_path(filename)
```
并新增方法:
```python
    def _save_mask_path(self, filename: str) -> Path:
        """Output path for the edited mask. Default: <stem>_mask.png in
        output_dir. Overridable."""
        return self.output_dir / mask_store.mask_name(filename)
```

> 仅抽取+改调用,默认行为不变。`Path` 已在文件顶部 import。

- [ ] **Step 4: 通过 + 全量 + 在线版不回归冒烟**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_mainwindow_hooks.py -q`
Expected: PASS(3 passed)

Run: `.venv/bin/python -c "import labeling_tool.app; print('import ok')" && .venv/bin/python -m pytest labeling_tool/tests -q`
Expected: import ok;全量通过。

Run(在线版不回归;依赖本地 session_18 数据,无则说明并跳过):
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
ws = Workspace.default(18); ws.ensure()
w = ViewerMainWindow(ws, Manifest(session_id=18, base="x"), None)
assert w.image_files, "online image list empty (regression!)"
fn = w.image_files[0]
assert w._save_mask_path(fn).name.endswith("_mask.png")
print("online OK:", len(w.image_files), "imgs; save name", w._save_mask_path(fn).name)
PY
```
Expected: `online OK: ... _mask.png`(在线版路径不变)。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/core/window/main_window.py labeling_tool/tests/test_mainwindow_hooks.py
git commit -m "refactor(window): overridable image-list/mask-path hooks (behavior-preserving)"
```

---

### Task 3: `LocalMainWindow`

**Files:**
- Create: `labeling_tool/ui/local_main_window.py`
- Test: `labeling_tool/tests/test_local_main_window.py`

**Interfaces:**
- Consumes: `MainWindow` 钩子(Task 2);`pair_by_stem`/`mask_for_stem`(Task 1);`MobileSamPredictor.try_load`;`encode_label_mask`/`decode_mask`。
- Produces: `LocalMainWindow(image_dir, mask_dir, output_dir)`。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_local_main_window.py`:

```python
from pathlib import Path
import cv2, numpy as np
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def _setup(tmp_path):
    img = tmp_path / "img"; msk = tmp_path / "msk"; out = tmp_path / "out"
    img.mkdir(); msk.mkdir()
    cv2.imwrite(str(img / "foo.jpg"), np.full((40, 60, 3), 100, np.uint8))
    label = np.zeros((40, 60), np.uint8); label[5:15, 5:20] = 2   # spalling region
    cv2.imwrite(str(msk / "foo.png"), label)
    return img, msk, out


def test_lists_paired_and_loads(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(img, msk, out)
    assert w.image_files == ["foo.jpg"]
    w._show_image(0)
    assert w.canvas.brush_mask_spalling is not None
    assert int((w.canvas.brush_mask_spalling > 0).sum()) == 10 * 15   # loaded mask


def test_save_writes_output_png(tmp_path):
    from labeling_tool.ui.local_main_window import LocalMainWindow
    from labeling_tool.core.mask_codec import decode_mask
    img, msk, out = _setup(tmp_path)
    w = LocalMainWindow(img, msk, out)
    w._show_image(0)
    w._save_all_artifacts(silent=True)
    saved = out / "foo.png"
    assert saved.exists()
    raw = cv2.imread(str(saved), cv2.IMREAD_UNCHANGED)
    crack, spall = decode_mask(raw, mask_path=str(saved))
    assert int((spall > 0).sum()) == 10 * 15         # round-trips spalling
    # no derived/result dirs were created
    assert not (out.parent / "HighLight").exists()
    assert not (out.parent / "Repair15").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_local_main_window.py -q`
Expected: FAIL — `ModuleNotFoundError: ... local_main_window`

- [ ] **Step 3: 实现**

新建 `labeling_tool/ui/local_main_window.py`:

```python
"""Standalone offline labeling window: pick an image folder + a mask folder,
edit crack/spalling masks (brush/bbox/SAM/scale), save to an output folder.
No login/API/upload, no highlight/15cm derived masks."""

from __future__ import annotations

from pathlib import Path

from labeling_tool.core.window.main_window import MainWindow
from labeling_tool.session.local_pairing import pair_by_stem, mask_for_stem
from labeling_tool.logging_setup import vlog


class LocalMainWindow(MainWindow):
    def __init__(self, image_dir, mask_dir, output_dir):
        super().__init__()
        self.image_dir = Path(image_dir)
        self.mask_dir = Path(mask_dir)
        self.origin_dir = self.image_dir
        self.detected_dir = self.mask_dir
        self.output_dir = Path(output_dir)
        self.highlight_dir = None            # skip derived masks
        self.repair15_dir = None
        self.export_result_on_save = False   # skip Result/<stem>.png export
        self._init_sam()
        self._reload_data()

    def _init_sam(self) -> None:
        from labeling_tool.core.sam.predictor import MobileSamPredictor
        predictor = MobileSamPredictor.try_load()
        if predictor is not None:
            self.canvas.set_sam_predictor(predictor)
            return
        btn = getattr(self, "_btn_sam_toggle", None)
        if btn is not None:
            btn.setEnabled(False)
            btn.setToolTip(self.tr_("sam_unavailable"))

    # ----- folder/stem/.png convention (overrides core defaults) -----
    def _build_image_list(self) -> list[str]:
        pairs = pair_by_stem(self.image_dir, self.mask_dir)
        missing = [img for img, m in pairs if m is None]
        if missing:
            vlog().warning("skip %d image(s) with no mask: %s",
                           len(missing), missing[:5])
        return [img for img, m in pairs if m is not None]

    def _display_mask_path(self, filename: str) -> tuple[str | None, str]:
        stem = Path(filename).stem
        edited = self.output_dir / f"{stem}.png"          # already-edited wins
        if edited.exists():
            return str(edited), "labeling"
        m = mask_for_stem(self.mask_dir, stem)             # input mask
        return (str(m) if m else None), ("detected" if m else "none")

    def _save_mask_path(self, filename: str) -> Path:
        return self.output_dir / f"{Path(filename).stem}.png"
```

- [ ] **Step 4: 通过 + 全量**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_local_main_window.py -q`
Expected: PASS(2 passed)

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全量通过。

- [ ] **Step 5: 提交**

```bash
git add labeling_tool/ui/local_main_window.py labeling_tool/tests/test_local_main_window.py
git commit -m "feat(local): LocalMainWindow — folder-based offline labeling window"
```

---

### Task 4: 文件夹对话框 + `app_local.py` 入口

**Files:**
- Create: `labeling_tool/ui/folder_dialog.py`
- Create: `labeling_tool/app_local.py`
- Test: `labeling_tool/tests/test_folder_dialog.py`

**Interfaces:**
- Consumes: `LocalMainWindow`(Task 3);`pair_by_stem`(Task 1)。
- Produces: `FolderDialog`(暴露 `.image_dir/.mask_dir/.output_dir`);`app_local.main()`。

- [ ] **Step 1: 写失败测试**

新建 `labeling_tool/tests/test_folder_dialog.py`:

```python
from pathlib import Path
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def test_dialog_exposes_dirs_and_count(tmp_path):
    from labeling_tool.ui.folder_dialog import FolderDialog
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    (img / "foo.jpg").write_bytes(b"x"); (msk / "foo.png").write_bytes(b"x")
    (img / "bar.jpg").write_bytes(b"x")                 # unpaired
    d = FolderDialog()
    d.set_dirs(str(img), str(msk))                      # test hook (no native picker)
    assert d.image_dir == img and d.mask_dir == msk
    assert d.output_dir == img.parent / "Labeling"      # default output
    assert d.paired_count() == 1                         # only foo paired
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_folder_dialog.py -q`
Expected: FAIL — `ModuleNotFoundError: ... folder_dialog`

- [ ] **Step 3: 实现对话框**

新建 `labeling_tool/ui/folder_dialog.py`:

```python
"""Startup dialog for the standalone labeler: pick an image folder and a mask
folder (output defaults to a Labeling/ folder beside the image folder)."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QMessageBox,
)

from labeling_tool.session.local_pairing import pair_by_stem


class FolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지/마스크 폴더 선택")
        self.image_dir: Path | None = None
        self.mask_dir: Path | None = None
        self.output_dir: Path | None = None

        self.ed_img = QLineEdit(); self.ed_img.setReadOnly(True)
        self.ed_msk = QLineEdit(); self.ed_msk.setReadOnly(True)
        self.lbl_count = QLabel("페어: -")
        btn_img = QPushButton("이미지 폴더…"); btn_img.clicked.connect(self._pick_img)
        btn_msk = QPushButton("마스크 폴더…"); btn_msk.clicked.connect(self._pick_msk)
        self.btn_ok = QPushButton("열기"); self.btn_ok.setDefault(True)
        self.btn_ok.setEnabled(False); self.btn_ok.clicked.connect(self._accept)

        root = QVBoxLayout(self)
        for lbl, ed, btn in (("이미지", self.ed_img, btn_img),
                             ("마스크", self.ed_msk, btn_msk)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl)); row.addWidget(ed, 1); row.addWidget(btn)
            root.addLayout(row)
        root.addWidget(self.lbl_count)
        root.addWidget(self.btn_ok)

    def _pick_img(self):
        d = QFileDialog.getExistingDirectory(self, "이미지 폴더")
        if d:
            self.set_dirs(d, str(self.mask_dir) if self.mask_dir else None)

    def _pick_msk(self):
        d = QFileDialog.getExistingDirectory(self, "마스크 폴더")
        if d:
            self.set_dirs(str(self.image_dir) if self.image_dir else None, d)

    def set_dirs(self, image_dir, mask_dir):
        """Set image/mask dirs (also the test hook — bypasses native pickers)."""
        if image_dir:
            self.image_dir = Path(image_dir)
            self.ed_img.setText(str(self.image_dir))
            self.output_dir = self.image_dir.parent / "Labeling"
        if mask_dir:
            self.mask_dir = Path(mask_dir)
            self.ed_msk.setText(str(self.mask_dir))
        n = self.paired_count()
        self.lbl_count.setText(f"페어: {n if n is not None else '-'}")
        self.btn_ok.setEnabled(bool(n))

    def paired_count(self):
        if not (self.image_dir and self.mask_dir):
            return None
        return sum(1 for _, m in pair_by_stem(self.image_dir, self.mask_dir)
                   if m is not None)

    def _accept(self):
        if not self.paired_count():
            QMessageBox.warning(self, "없음", "페어되는 이미지/마스크가 없습니다.")
            return
        self.accept()
```

- [ ] **Step 4: 实现入口 `app_local.py`**

新建 `labeling_tool/app_local.py`:

```python
"""Standalone offline labeling entry point: pick image + mask folders, edit
crack/spalling masks locally, save to an output folder. No login/API."""

from __future__ import annotations

import os
import sys

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.folder_dialog import FolderDialog
from labeling_tool.ui.local_main_window import LocalMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    dlg = FolderDialog()
    if not dlg.exec_():
        return 0
    dlg.output_dir.mkdir(parents=True, exist_ok=True)
    win = LocalMainWindow(dlg.image_dir, dlg.mask_dir, dlg.output_dir)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 通过 + import 冒烟 + 全量**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest labeling_tool/tests/test_folder_dialog.py -q`
Expected: PASS

Run: `.venv/bin/python -c "import labeling_tool.app_local, labeling_tool.ui.folder_dialog; print('import ok')"`
Expected: `import ok`

Run: `.venv/bin/python -m pytest labeling_tool/tests -q`
Expected: 全量通过。

- [ ] **Step 6: 提交**

```bash
git add labeling_tool/ui/folder_dialog.py labeling_tool/app_local.py labeling_tool/tests/test_folder_dialog.py
git commit -m "feat(local): folder-select dialog + app_local entry point"
```

---

## Self-Review

**Spec coverage:**
- 选 image+mask 文件夹 → Task 4(FolderDialog)✅
- 同 stem 不同后缀配对 + 保存 output/<stem>.png → Task 1 + Task 3 钩子 ✅
- 去登录/API/上传/manifest → 新入口不引入(app_local 不含 login/fetch/client)✅
- 去 highlight/15cm/Result → Task 3(dir=None,export=False)✅
- 保留画笔/bbox/SAM/比例尺 → 继承 core + `_init_sam` ✅
- core 行为不变 → Task 2 钩子默认 + 在线版冒烟 ✅
- 新分支推送 → 执行完由主控推送 ✅

**Placeholder scan:** 无 TBD;改代码 step 均含完整代码。

**Type consistency:** `pair_by_stem->list[(str,Path|None)]`、`mask_for_stem->Path|None`、`_build_image_list->list[str]`、`_display_mask_path->(str|None,str)`、`_save_mask_path->Path`、`LocalMainWindow(image_dir,mask_dir,output_dir)`、`FolderDialog.set_dirs/paired_count/image_dir/mask_dir/output_dir` 跨任务一致。
