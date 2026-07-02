# annotation_tool/ui/main_window.py
"""Main window: file list + canvas + class panel, wiring worker & IO."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QButtonGroup, QRadioButton, QSlider,
    QDockWidget, QMessageBox, QShortcut, QFileDialog,
)
from PyQt5.QtGui import QKeySequence

from annotation_tool import configs
from annotation_tool.core import dataset_io
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
        self.active_class = configs.CLASS_IDS[0]
        self.state: MaskState | None = None
        self.current_item = None
        self.current_image = None
        self._candidate = None
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
                "请用 File ▸ Open Folder (Ctrl+O) 选择包含 images/ 的数据集文件夹")

    # --- UI construction ---
    def _build_class_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        self._class_group = QButtonGroup(self)
        self._stat_labels = {}
        for c in configs.CLASS_IDS:
            rb = QRadioButton(f"{c}: {configs.CLASSES[c]}")
            rb.setChecked(c == self.active_class)
            rb.clicked.connect(lambda _=False, cid=c: self.set_active_class(cid))
            self._class_group.addButton(rb, c)
            lay.addWidget(rb)
            sl = QLabel("0.0%")
            self._stat_labels[c] = sl
            lay.addWidget(sl)
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
            self, "Select dataset folder (must contain an images/ subfolder)", start)
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
                    self, "Invalid folder",
                    f"No 'images/' subfolder found in:\n{dataset_dir}")
            return

        # commit the switch and reset per-image editing state
        self.dataset_dir = dataset_dir
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
        if self.items:
            self.list_widget.setCurrentRow(0)  # triggers load_index(0)
        elif warn_if_empty:
            QMessageBox.information(
                self, "No images", f"No .jpg images found in {dataset_dir / 'images'}")

    def _install_shortcuts(self):
        for c in configs.CLASS_IDS:  # number keys 1..N select each class
            QShortcut(QKeySequence(str(c)), self, lambda cid=c: self.set_active_class(cid))
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
        self.state = MaskState(h, w)
        mask_path = dataset_io.mask_dir_of(self.dataset_dir) / dataset_io.mask_filename(it.name)
        if mask_path.exists():
            self.state.load_from(dataset_io.load_mask(mask_path))
        self.segmenter.set_image(self.current_image)
        self._refresh_layers()

    def set_active_class(self, cid):
        self.active_class = cid
        btn = self._class_group.button(cid)
        if btn is not None:
            btn.setChecked(True)
        self.canvas.set_brush_color(configs.CLASS_COLORS[cid])
        self.canvas.clear_prompt()
        self.canvas.set_candidate(None)
        self._candidate = None

    # --- manual brush / eraser ---
    def set_tool(self, tool):
        self._tool_buttons[tool].setChecked(True)
        self.canvas.set_brush_color(configs.CLASS_COLORS[self.active_class])
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
        # are already labelled (priority: scalebar > joint > concrete), so
        # subtract the higher-priority layers from the candidate before merging.
        cand = self._restrict_to_priority(cand, self.active_class)
        self.state.add(self.active_class, cand)
        self._candidate = None
        self.canvas.set_candidate(None)
        self.canvas.clear_prompt()
        self._refresh_layers()

    def _restrict_to_priority(self, cand, cls):
        order = configs.EXPORT_ORDER  # low -> high priority
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
        self.canvas.set_committed_layers(self.state.layers)
        for c, frac in self.state.stats().items():
            self._stat_labels[c].setText(f"{100 * frac:.2f}%")

    # --- save ---
    def save_current(self):
        if self.state is None or self.current_item is None:
            return
        flat = self.state.flatten()
        mask_path = dataset_io.mask_dir_of(self.dataset_dir) / dataset_io.mask_filename(self.current_item.name)
        dataset_io.save_mask(mask_path, flat)
        if configs.EXPORT_OVERLAY:
            ov_path = dataset_io.overlay_dir_of(self.dataset_dir) / f"{self.current_item.name}_overlay.jpg"
            dataset_io.save_overlay(ov_path, self.current_image, flat)
        row = getattr(self, "_current_row", self.list_widget.currentRow())
        item = self.list_widget.item(row)
        if item is not None:
            item.setText("✓ " + self.current_item.name)
        self.statusBar().showMessage(f"saved {mask_path.name}", 3000)

    def closeEvent(self, event):
        if hasattr(self, "worker"):
            self.worker.stop()
        super().closeEvent(event)
