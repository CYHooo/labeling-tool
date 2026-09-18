# annotation_tool/ui/main_window.py
"""Main window: file list + canvas + class panel, wiring worker & IO."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QButtonGroup, QRadioButton, QSlider,
    QDockWidget, QMessageBox, QShortcut, QFileDialog, QInputDialog, QColorDialog,
)
from PyQt5.QtGui import QKeySequence, QColor

from annotation_tool import configs
from annotation_tool.core import dataset_io
from annotation_tool.core.class_registry import ClassRegistry
from annotation_tool.core.mask_state import MaskState
from annotation_tool.segmenter import base as seg_base
from annotation_tool.ui.canvas import ImageCanvas
from annotation_tool.ui.worker import InferenceWorker
from annotation_tool.ui.styles import STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self, dataset_dir=None, backend=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLESHEET)
        self.setWindowTitle("ConcJoint Annotator")
        self.dataset_dir = Path(dataset_dir) if dataset_dir else Path(configs.DEFAULT_DATASET_DIR)
        self._load_registry()
        self.active_class = self.registry.class_ids[0]
        self._class_shortcuts = []
        self.state: MaskState | None = None
        self.current_item = None
        self.current_image = None
        self._candidate = None
        self._mask_load_error = None  # set when an existing mask can't be loaded
        self.items = []

        # --- central canvas ---
        self.canvas = ImageCanvas()
        self.setCentralWidget(self.canvas)
        self.canvas.promptChanged.connect(self._on_prompt_changed)
        self.canvas.strokeFinished.connect(self._on_stroke)

        # --- left: file list (populated by load_dataset) ---
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.load_index)
        dock_l = QDockWidget("Images", self)
        dock_l.setWidget(self.list_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock_l)

        # --- right: class panel ---
        self._build_class_panel()

        # --- menu ---
        self._build_menu()

        # --- backend + worker ---
        self.segmenter = seg_base.build_segmenter(backend)
        self.segmenter.load()
        self.worker = InferenceWorker(self.segmenter)
        self.worker.result.connect(self._on_candidate)
        self.worker.error.connect(self._on_error)
        self.worker.start()

        self._install_shortcuts()

        # Only auto-load when a dataset dir was explicitly provided. Otherwise we
        # show nothing on launch and let the user pick a folder via File > Open
        # Folder (the dataset_dir above is just the dialog's starting point).
        if dataset_dir:
            self.load_dataset(self.dataset_dir, warn_if_empty=False)
        else:
            self.statusBar().showMessage(
                "请用 File ▸ Open Folder (Ctrl+O) 选择存放图片的文件夹")
        if self._classes_error:
            self.statusBar().showMessage(self._classes_error)

    # --- class registry (global, user-editable classes) ---
    def _load_registry(self):
        """Load classes from the global JSON; fall back to configs defaults.

        A malformed file is never overwritten: edits then stay session-only and
        the user is told why, so hand-edited definitions are not lost."""
        self._classes_error = None
        try:
            self.registry = ClassRegistry.load(configs.CLASSES_FILE, ClassRegistry.from_configs())
        except ValueError as exc:
            self.registry = ClassRegistry.from_configs()
            self._classes_error = (f"类别文件损坏，已使用默认类别，修改不会被保存: {exc}")

    def _persist_classes(self):
        if self._classes_error:
            self.statusBar().showMessage(self._classes_error, 5000)
            return
        try:
            self.registry.save(configs.CLASSES_FILE)
        except OSError as exc:
            QMessageBox.warning(self, "Save classes failed", str(exc))

    def _on_classes_changed(self):
        """Common follow-up after any registry edit: persist, rebuild UI, redraw."""
        self._persist_classes()
        self._rebuild_class_list()
        self.canvas.set_brush_color(self.registry.color(self.active_class))
        self._refresh_layers()

    def add_class(self, name, color):
        """Add a new class (raises ValueError on bad name) and make it active."""
        cid = self.registry.add(name, color)
        if self.state is not None:
            self.state.ensure_layer(cid)
        self._on_classes_changed()
        self.set_active_class(cid)
        return cid

    def rename_class(self, cid, name):
        self.registry.rename(cid, name)
        self._on_classes_changed()

    def set_class_color(self, cid, color):
        self.registry.set_color(cid, color)
        self._on_classes_changed()

    def move_active_priority(self, delta):
        self.registry.move_priority(self.active_class, delta)
        self._on_classes_changed()

    def _suggest_color(self):
        # golden-ratio hue stepping gives well-separated colors for new classes
        hue = (len(self.registry.class_ids) * 0.618034) % 1.0
        return QColor.fromHsvF(hue, 0.85, 0.95)

    def _on_add_class_clicked(self):
        name, ok = QInputDialog.getText(self, "添加类别", "类别名称:")
        if not ok:
            return
        color = QColorDialog.getColor(self._suggest_color(), self, "选择类别颜色")
        if not color.isValid():
            return
        try:
            cid = self.add_class(name, color.getRgb()[:3])
        except ValueError as exc:
            QMessageBox.warning(self, "添加类别失败", str(exc))
            return
        self.statusBar().showMessage(f"已添加类别 {cid}: {self.registry.name(cid)}", 3000)

    def _on_rename_clicked(self):
        cid = self.active_class
        name, ok = QInputDialog.getText(
            self, "重命名类别", f"类别 {cid} 的新名称:", text=self.registry.name(cid))
        if not ok:
            return
        try:
            self.rename_class(cid, name)
        except ValueError as exc:
            QMessageBox.warning(self, "重命名失败", str(exc))

    def _on_swatch_clicked(self, cid):
        color = QColorDialog.getColor(QColor(*self.registry.color(cid)), self,
                                      f"类别 {cid}: {self.registry.name(cid)} 的颜色")
        if color.isValid():
            self.set_class_color(cid, color.getRgb()[:3])

    # --- UI construction ---
    def _build_class_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        self._class_group = QButtonGroup(self)
        self._stat_labels = {}
        # class rows live in their own container so they can be rebuilt
        # whenever classes are added / renamed / recolored
        self._class_list_widget = QWidget()
        self._class_list_layout = QVBoxLayout(self._class_list_widget)
        self._class_list_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._class_list_widget)

        manage_row = QHBoxLayout()
        for text, tip, slot in (
                ("+ 添加", "添加新类别", self._on_add_class_clicked),
                ("重命名", "重命名当前类别", self._on_rename_clicked),
                ("优先级 ↑", "提高当前类别的导出优先级（覆盖其他类）",
                 lambda: self.move_active_priority(+1)),
                ("↓", "降低当前类别的导出优先级", lambda: self.move_active_priority(-1))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            manage_row.addWidget(b)
        lay.addLayout(manage_row)
        self._lbl_order = QLabel()
        self._lbl_order.setWordWrap(True)
        self._lbl_order.setStyleSheet("color:#9ea3aa;")
        lay.addWidget(self._lbl_order)
        self._rebuild_class_list()
        # --- tool selection: SAM point/box vs manual brush / eraser ---
        lay.addWidget(self._hline_label("工具 Tool"))
        tool_row = QHBoxLayout()
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons = {}
        for key, text in (("sam", "SAM 点/框 [V]"),
                          ("brush", "画笔 [B]"),
                          ("eraser", "橡皮擦 [E]")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            self._tool_group.addButton(b)
            self._tool_buttons[key] = b
            tool_row.addWidget(b)
        self._tool_buttons["sam"].setChecked(True)
        lay.addLayout(tool_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("笔刷"))
        self._sld_brush = QSlider(Qt.Horizontal)
        self._sld_brush.setRange(2, 200)
        self._sld_brush.setValue(40)
        self._sld_brush.valueChanged.connect(self._on_brush_size)
        self._lbl_brush = QLabel("40")
        self._lbl_brush.setFixedWidth(32)
        size_row.addWidget(self._sld_brush, stretch=1)
        size_row.addWidget(self._lbl_brush)
        lay.addLayout(size_row)

        self.btn_commit = QPushButton("Confirm (Enter)")
        self.btn_commit.setObjectName("primaryAction")
        self.btn_commit.setMinimumHeight(34)
        self.btn_commit.clicked.connect(self.commit_candidate)
        self.btn_save = QPushButton("Save (Ctrl+S)")
        self.btn_save.setObjectName("primaryAction")
        self.btn_save.setMinimumHeight(34)
        self.btn_save.clicked.connect(self.save_current)
        lay.addWidget(self.btn_commit)
        lay.addWidget(self.btn_save)
        lay.addStretch(1)
        dock_r = QDockWidget("Classes", self)
        dock_r.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock_r)

    def _rebuild_class_list(self):
        """(Re)create one row per class: radio + coverage % + color swatch."""
        for btn in self._class_group.buttons():
            self._class_group.removeButton(btn)
        while self._class_list_layout.count():
            w = self._class_list_layout.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._stat_labels = {}
        for c in self.registry.class_ids:
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            rb = QRadioButton(f"{c}: {self.registry.name(c)}")
            rb.setChecked(c == self.active_class)
            rb.clicked.connect(lambda _=False, cid=c: self.set_active_class(cid))
            self._class_group.addButton(rb, c)
            row_lay.addWidget(rb, stretch=1)
            sl = QLabel("0.00%")
            self._stat_labels[c] = sl
            row_lay.addWidget(sl)
            swatch = QPushButton()
            swatch.setFixedSize(22, 22)
            swatch.setToolTip("点击修改颜色")
            r, g, b = self.registry.color(c)
            swatch.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border: 1px solid #5a6270;"
                "border-radius: 3px; padding: 0; min-width: 0;")
            swatch.clicked.connect(lambda _=False, cid=c: self._on_swatch_clicked(cid))
            row_lay.addWidget(swatch)
            self._class_list_layout.addWidget(row)
        order = " < ".join(self.registry.name(c) for c in self.registry.export_order)
        self._lbl_order.setText(f"导出优先级（低→高）: {order}")
        self._install_class_shortcuts()

    def _install_class_shortcuts(self):
        """Number keys 1..9 select the class with that pixel value."""
        for sc in self._class_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._class_shortcuts = [
            QShortcut(QKeySequence(str(c)), self, lambda cid=c: self.set_active_class(cid))
            for c in self.registry.class_ids if c <= 9
        ]

    def _hline_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#9ea3aa; padding-top:6px;")
        return lbl

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        act_open = file_menu.addAction("Open Folder…")
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_folder)

    # --- dataset selection ---
    def open_folder(self):
        start = str(self.dataset_dir) if self.dataset_dir.exists() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Select an image folder (images are read directly from it)", start)
        if chosen:
            self.load_dataset(Path(chosen), warn_if_empty=True)

    def load_dataset(self, dataset_dir, warn_if_empty=True):
        """Load (or switch to) a dataset folder and repopulate the file list."""
        dataset_dir = Path(dataset_dir)
        try:
            items = dataset_io.list_images(dataset_dir)
        except FileNotFoundError:
            if warn_if_empty:
                QMessageBox.warning(
                    self, "Invalid folder", f"Folder not found:\n{dataset_dir}")
            return

        # commit the switch and reset per-image editing state
        self.dataset_dir = dataset_dir
        self.mask_dir = dataset_io.resolve_mask_dir(dataset_dir)
        self.items = items
        self.state = None
        self.current_item = None
        self.current_image = None
        self._candidate = None
        self.canvas.set_candidate(None)

        # repopulate list without triggering load_index during the clear
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for it in self.items:
            li = QListWidgetItem(("✓ " if it.has_mask else "  ") + it.name)
            self.list_widget.addItem(li)
        self.list_widget.blockSignals(False)

        self.setWindowTitle(
            f"ConcJoint Annotator — {dataset_dir.name} ({len(self.items)} images)")
        n_masks = sum(it.has_mask for it in self.items)
        self.statusBar().showMessage(
            f"{len(self.items)} 张图片，{n_masks} 张已有标注；mask 目录: {self.mask_dir}")
        if self.items:
            self.list_widget.setCurrentRow(0)  # triggers load_index(0)
        elif warn_if_empty:
            QMessageBox.information(
                self, "No images", f"No image files found directly in {dataset_dir}")

    def _install_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Return), self, self.commit_candidate)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.cancel_candidate)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_current)
        QShortcut(QKeySequence("D"), self, lambda: self._step(1))
        QShortcut(QKeySequence("A"), self, lambda: self._step(-1))
        QShortcut(QKeySequence("V"), self, lambda: self.set_tool("sam"))
        QShortcut(QKeySequence("B"), self, lambda: self.set_tool("brush"))
        QShortcut(QKeySequence("E"), self, lambda: self.set_tool("eraser"))
        QShortcut(QKeySequence("["), self, lambda: self._nudge_brush(-8))
        QShortcut(QKeySequence("]"), self, lambda: self._nudge_brush(8))

    # --- navigation / loading ---
    def _step(self, delta):
        row = self.list_widget.currentRow()
        new = max(0, min(row + delta, self.list_widget.count() - 1))
        self.list_widget.setCurrentRow(new)

    def load_index(self, idx):
        if idx < 0 or idx >= len(self.items):
            return
        it = self.items[idx]
        self._current_row = idx
        self._candidate = None
        self.current_item = it
        self.current_image = dataset_io.load_image_rgb(it.image_path)
        self.canvas.set_image(self.current_image)
        self.canvas.set_candidate(None)
        w, h = self.current_image.size
        self.state = MaskState(h, w, class_ids=self.registry.class_ids)
        self._mask_load_error = None
        if it.mask_path is not None and it.mask_path.exists():
            self._load_existing_mask(it.mask_path, h, w)
        self.segmenter.set_image(self.current_image)
        self._refresh_layers()

    def _load_existing_mask(self, mask_path, h, w):
        """Load a saved mask into the fresh MaskState, without ever crashing.

        On failure the image stays editable but saving is blocked, so a broken
        or mismatched mask on disk is never overwritten with an empty one."""
        try:
            mask = dataset_io.load_mask(mask_path)
        except OSError as exc:
            self._mask_load_error = f"无法读取 mask {mask_path.name}: {exc}"
        else:
            if mask.shape != (h, w):
                self._mask_load_error = (
                    f"mask {mask_path.name} 尺寸 {mask.shape[1]}x{mask.shape[0]} 与图片 "
                    f"{w}x{h} 不一致，未加载；为保护原文件，本图禁止保存")
            else:
                self.state.load_from(mask)
                unknown = sorted(set(np.unique(mask).tolist()) - {0} - set(self.registry.class_ids))
                if unknown:
                    # these pixels have no class definition and would be dropped on save
                    self.statusBar().showMessage(
                        f"警告: mask 中含未定义的像素值 {unknown}，保存时会被清除；请先添加对应类别")
        if self._mask_load_error:
            self.statusBar().showMessage(self._mask_load_error)

    def set_active_class(self, cid):
        self.active_class = cid
        btn = self._class_group.button(cid)
        if btn is not None:
            btn.setChecked(True)
        self.canvas.set_brush_color(self.registry.color(cid))
        self.canvas.clear_prompt()
        self.canvas.set_candidate(None)
        self._candidate = None

    # --- manual brush / eraser ---
    def set_tool(self, tool):
        self._tool_buttons[tool].setChecked(True)
        self.canvas.set_brush_color(self.registry.color(self.active_class))
        self.canvas.set_tool(tool)
        self._candidate = None

    def _on_brush_size(self, px):
        self._lbl_brush.setText(str(px))
        self.canvas.set_brush_size(px)

    def _nudge_brush(self, delta):
        self._sld_brush.setValue(self._sld_brush.value() + delta)

    def _on_stroke(self, stroke, is_erase):
        """A finished manual brush/eraser stroke -> current class layer."""
        if self.state is None:
            return
        if is_erase:
            self.state.erase(self.active_class, stroke)
        else:
            # a brush stroke must still respect priority (don't paint over a
            # higher-priority class), matching commit_candidate's behaviour
            self.state.add(self.active_class,
                           self._restrict_to_priority(stroke, self.active_class))
        self._refresh_layers()

    # --- inference flow ---
    def _on_prompt_changed(self, points, labels, box):
        if points or box:
            self.worker.request(points, labels, box)

    def _on_candidate(self, mask):
        if self.state is None:
            return  # image unloaded since the request was issued
        try:
            self._candidate = mask
            self.canvas.set_candidate(mask)
        except AssertionError:
            # stale result whose shape no longer matches the current image; discard
            self._candidate = None

    def _on_error(self, msg):
        QMessageBox.warning(self, "Inference error", msg)

    def commit_candidate(self):
        cand = getattr(self, "_candidate", None)
        if cand is None or self.state is None:
            return
        # A lower-priority class must not overwrite higher-priority pixels that
        # are already labelled (priority from registry.export_order), so
        # subtract the higher-priority layers from the candidate before merging.
        cand = self._restrict_to_priority(cand, self.active_class)
        self.state.add(self.active_class, cand)
        self._candidate = None
        self.canvas.set_candidate(None)
        self.canvas.clear_prompt()
        self._refresh_layers()

    def _restrict_to_priority(self, cand, cls):
        order = self.registry.export_order  # low -> high priority
        higher = order[order.index(cls) + 1:]
        out = cand.copy()
        for h in higher:
            out = out & ~self.state.layers[h]
        return out

    def cancel_candidate(self):
        self._candidate = None
        self.canvas.set_candidate(None)
        self.canvas.clear_prompt()

    def undo(self):
        if self.state and self.state.can_undo:
            self.state.undo()
            self._refresh_layers()

    def redo(self):
        if self.state and self.state.can_redo:
            self.state.redo()
            self._refresh_layers()

    def _refresh_layers(self):
        if self.state is None:
            return
        self.canvas.set_committed_layers(
            self.state.layers, self.registry.colors(), self.registry.export_order)
        for c, frac in self.state.stats().items():
            if c in self._stat_labels:
                self._stat_labels[c].setText(f"{100 * frac:.2f}%")

    # --- save ---
    def save_current(self):
        if self.state is None or self.current_item is None:
            return
        if self._mask_load_error:
            QMessageBox.warning(self, "禁止保存", self._mask_load_error)
            return
        flat = self.state.flatten(self.registry.export_order)
        # overwrite the mask where it was found; new masks go to the resolved dir
        mask_path = (self.current_item.mask_path
                     or self.mask_dir / dataset_io.mask_filename(self.current_item.name))
        dataset_io.save_mask(mask_path, flat)
        self.current_item.mask_path = mask_path
        self.current_item.has_mask = True
        if configs.EXPORT_OVERLAY:
            ov_path = dataset_io.overlay_dir_for_mask(mask_path) / f"{self.current_item.name}_overlay.jpg"
            dataset_io.save_overlay(ov_path, self.current_image, flat, self.registry.colors())
        row = getattr(self, "_current_row", self.list_widget.currentRow())
        item = self.list_widget.item(row)
        if item is not None:
            item.setText("✓ " + self.current_item.name)
        self.statusBar().showMessage(f"saved {mask_path.name}", 3000)

    def closeEvent(self, event):
        if hasattr(self, "worker"):
            self.worker.stop()
        super().closeEvent(event)
