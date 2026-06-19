"""MainWindow class — application orchestration and state management."""

from pathlib import Path

import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QStatusBar, QMessageBox, QFileDialog, QApplication, QInputDialog,
)
from PyQt5.QtGui import QColor

from labeling_tool.core.constants import (
    CATEGORIES, DEFAULT_CATEGORY, OUTPUT_DIR_NAME,
    IMAGE_EXTENSIONS, MASK_NAME_SUFFIXES,
)
from labeling_tool.core.i18n import TRANSLATIONS, LANG_DISPLAY_NAMES, DEFAULT_LANG
from labeling_tool.core.mask_io import load_origin_and_masks
from labeling_tool.core.mask_codec import encode_label_mask
from labeling_tool.core.canvas import ImageCanvas
from labeling_tool.core.bbox import (
    ScaleTracker, save_bboxes, load_bboxes,
    scale_from_two_points, MARKER_PHYSICAL_CM,
)
from labeling_tool.session import mask_store
from labeling_tool.core.result import export_result
from labeling_tool.core.window.styles import STYLESHEET
from labeling_tool.core.window.ui_builder import build_side_panel
from labeling_tool.core.window.shortcuts import register_shortcuts


class MainWindow(QMainWindow):
    # When True, saving also writes Result/<stem>.{png,txt} — a full-res preview
    # image plus a crack-metrics text report. That step re-reads the origin,
    # runs the full skeleton+width metric, and encodes a large PNG (~2s on a
    # panorama), so the Viewer API tool turns it OFF: there, metrics are computed at
    # upload time (register step) and Result/ is never consumed.
    export_result_on_save: bool = True

    def __init__(self):
        super().__init__()

        self.lang: str = DEFAULT_LANG

        self.origin_dir: Path | None = None
        self.detected_dir: Path | None = None
        self.output_dir: Path | None = None
        self.result_dir: Path | None = None
        self.highlight_dir: Path | None = None
        self.repair15_dir: Path | None = None

        if Path("Origin").exists():
            self.origin_dir = Path("Origin").resolve()
        if Path("Detected").exists():
            self.detected_dir = Path("Detected").resolve()
        self._sync_output_dir()

        self.image_files: list[str] = []
        self.current_idx: int = -1
        self._edited: dict[str, bool] = {}

        # ----- new state for bbox / rebuild / result -----
        self.scale_tracker = ScaleTracker()
        self.current_scale: float | None = None
        self.current_scale_source: str = "none"
        self._bbox_edited: dict[str, bool] = {}

        self._build_ui()
        self.setWindowTitle(self.tr_("window_title"))
        self.setMinimumSize(820, 560)
        self._apply_initial_geometry()

        from labeling_tool.ui.derived_mask_worker import DerivedMaskSignals
        self._derived_signals = DerivedMaskSignals()
        self._derived_signals.done.connect(self._on_derived_ready)

        if self.origin_dir is not None:
            self._load_data()

    def _apply_initial_geometry(self):
        """Size the window to the available screen, centered.

        Replaces the old hard-coded 1440x900, which overflowed small laptop
        displays and looked oversized elsewhere. Caps at a comfortable max
        and never exceeds ~86% of the usable screen.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 820)
            return
        avail = screen.availableGeometry()
        w = max(820, min(1440, int(avail.width() * 0.86)))
        h = max(560, min(900, int(avail.height() * 0.86)))
        self.resize(w, h)
        self.move(avail.left() + (avail.width() - w) // 2,
                  avail.top() + (avail.height() - h) // 2)

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------
    def tr_(self, key: str, **kwargs) -> str:
        s = TRANSLATIONS.get(self.lang, {}).get(key)
        if s is None:
            s = TRANSLATIONS["en"].get(key, key)
        return s.format(**kwargs) if kwargs else s

    def _change_language(self, idx: int):
        codes = list(LANG_DISPLAY_NAMES.keys())
        if 0 <= idx < len(codes):
            self.lang = codes[idx]
            self._retranslate_ui()

    def _retranslate_ui(self):
        self.setWindowTitle(self.tr_("window_title"))
        self._lbl_app_title.setText(self.tr_("window_title"))
        self._grp_settings.setTitle(self.tr_("settings"))
        self._lbl_lang.setText(self.tr_("language") + ":")
        self._btn_select_origin.setText(self.tr_("btn_select_origin"))
        self._btn_select_detected.setText(self.tr_("btn_select_detected"))
        self._grp_category.setTitle(self.tr_("lbl_category"))
        self._btn_cat_crack.setText(self.tr_("cat_crack"))
        self._btn_cat_spalling.setText(self.tr_("cat_spalling"))
        self._btn_sam_toggle.setText(self.tr_("btn_sam"))
        self._btn_sam_commit.setText(self.tr_("btn_sam_commit"))
        self._btn_sam_cancel.setText(self.tr_("btn_sam_cancel"))
        self._btn_sam_undo.setText(self.tr_("btn_sam_undo"))
        self._refresh_path_labels()

        self._grp_brush.setTitle(self.tr_("group_brush"))
        self._btn_brush_toggle.setText(
            self.tr_("btn_brush_off") if self.canvas.brush_mode
            else self.tr_("btn_brush_on"))
        self._lbl_brush_size.setText(self.tr_("lbl_brush_size"))
        self._chk_fine_annotation.setText(self.tr_("btn_fine_annotation"))
        self._btn_brush_reset.setText(self.tr_("btn_brush_reset"))
        self._btn_brush_save.setText(self.tr_("btn_brush_save"))

        self._grp_scale.setTitle(self.tr_("group_scale"))
        self._btn_measure.setText(
            self.tr_("btn_measure_cancel") if self.canvas.measure_mode
            else self.tr_("btn_measure"))
        self._refresh_scale_label()

        self._grp_bbox.setTitle(self.tr_("group_bbox"))
        self._btn_bbox_toggle.setText(
            self.tr_("btn_bbox_off") if self.canvas.bbox_mode
            else self.tr_("btn_bbox_on"))
        self._btn_show_highlight.setText(self.tr_("btn_show_highlight"))
        self._btn_show_repair15.setText(self.tr_("btn_show_repair15"))

        self._grp_list.setTitle(self.tr_("group_list"))
        self._grp_nav.setTitle(self.tr_("group_nav"))
        self._grp_hint.setTitle(self.tr_("group_hint"))
        self.btn_prev.setText(self.tr_("btn_prev"))
        self.btn_next.setText(self.tr_("btn_next"))
        self.btn_save.setText(self.tr_("btn_save"))
        self._lbl_hint.setText(self.tr_("hint_text"))

        if self.current_idx >= 0:
            self._update_status_for_current()
        else:
            self.status.showMessage(self.tr_("ready"))

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------
    def _sync_output_dir(self):
        """Derive output_dir, result_dir, highlight_dir, repair15_dir from origin_dir.parent."""
        if self.origin_dir is not None:
            parent = self.origin_dir.parent
            self.output_dir   = parent / OUTPUT_DIR_NAME
            self.result_dir   = parent / "Result"
            self.highlight_dir = parent / "HighLight"
            self.repair15_dir  = parent / "Repair15"
        else:
            self.output_dir = self.result_dir = None
            self.highlight_dir = self.repair15_dir = None

    def _select_origin_folder(self):
        start = str(self.origin_dir) if self.origin_dir else str(Path.cwd())
        d = QFileDialog.getExistingDirectory(self, self.tr_("dlg_origin"), start)
        if d:
            self.origin_dir = Path(d).resolve()
            self._sync_output_dir()
            self._refresh_path_labels()
            self._reload_data()

    def _select_detected_folder(self):
        start = str(self.detected_dir) if self.detected_dir else str(Path.cwd())
        d = QFileDialog.getExistingDirectory(self, self.tr_("dlg_detected"), start)
        if d:
            self.detected_dir = Path(d).resolve()
            self._refresh_path_labels()
            self._reload_data()

    def _refresh_path_labels(self):
        no_p = self.tr_("no_path")

        def short(p: Path | None) -> str:
            if p is None:
                return no_p
            # Show only the last two path segments to keep the label tidy;
            # the full path lands in the tooltip for users who need it.
            parts = p.parts
            return str(Path(*parts[-2:])) if len(parts) >= 2 else str(p)

        for lbl, key, p in (
            (self._lbl_origin_path,   "lbl_origin",   self.origin_dir),
            (self._lbl_detected_path, "lbl_detected", self.detected_dir),
            (self._lbl_output_path,   "lbl_output",   self.output_dir),
        ):
            lbl.setText(self.tr_(key, p=short(p)))
            lbl.setToolTip(str(p) if p else "")

    # ------------------------------------------------------------------
    # Brush callbacks
    # ------------------------------------------------------------------
    def _on_brush_toggle(self, checked: bool):
        # Mutually exclusive with bbox and measure modes
        if checked and self.canvas.bbox_mode:
            self._btn_bbox_toggle.setChecked(False)
        if checked and self._btn_measure.isChecked():
            self._btn_measure.setChecked(False)   # leave measure mode
        if checked and self.canvas.sam_mode:
            self._btn_sam_toggle.setChecked(False)
        self.canvas.brush_mode = bool(checked)
        self._btn_brush_toggle.setText(
            self.tr_("btn_brush_off") if checked else self.tr_("btn_brush_on"))
        self.canvas.update()

    def _on_fine_annotation_toggle(self, checked: bool):
        """Fine mode: keep the crack stroke's painted thickness (skip the 1px
        thinning) so width metrics reflect the real drawn width."""
        self.canvas.fine_annotation = bool(checked)

    # ------------------------------------------------------------------
    # Manual scale measurement (fallback when ArUco is not auto-detected)
    # ------------------------------------------------------------------
    def _on_measure_toggle(self, checked: bool):
        if checked:
            # Mutually exclusive with brush / bbox editing.
            if self.canvas.brush_mode:
                self._btn_brush_toggle.setChecked(False)
            if self.canvas.bbox_mode:
                self._btn_bbox_toggle.setChecked(False)
            if self.canvas.sam_mode:
                self._btn_sam_toggle.setChecked(False)
        self._btn_measure.setText(
            self.tr_("btn_measure_cancel") if checked
            else self.tr_("btn_measure"))
        self.canvas.set_measure_mode(bool(checked))
        if checked:
            self.status.showMessage(self.tr_("measure_hint"))

    def _on_measure_completed(self, pixel_dist: float):
        """Two points clicked: ask the real length and set px/cm manually."""
        cm, ok = QInputDialog.getDouble(
            self, self.tr_("measure_dialog_title"),
            self.tr_("measure_dialog_label"),
            float(MARKER_PHYSICAL_CM), 0.1, 100000.0, 2)
        if not ok:
            self.canvas.clear_measurement()
            return
        scale = scale_from_two_points((0.0, 0.0), (pixel_dist, 0.0), cm)
        if scale is None:
            return
        self.current_scale = scale
        self.current_scale_source = "manual"
        # Feed the session tracker so later images without ArUco fall back to it.
        self.scale_tracker.last_known_scale = scale
        self.canvas.set_bbox_padding_px(scale * 15.0)
        self._btn_bbox_toggle.setEnabled(True)
        self._refresh_scale_label()
        mm_per_px = 10.0 / scale
        self.status.showMessage(
            self.tr_("measure_done", scale=f"{mm_per_px:.4f}"))
        # Persist immediately so the manual scale survives an image switch /
        # is used at upload even if the user doesn't redraw the mask.
        if self.current_idx >= 0:
            self._save_all_artifacts(silent=True)
        self._btn_measure.setChecked(False)

    def _on_brush_size_changed(self, value: int):
        self.canvas.brush_size = int(value)
        self.canvas.update()

    def _on_category_changed(self, index: int):
        cat = CATEGORIES[index] if 0 <= index < len(CATEGORIES) else DEFAULT_CATEGORY
        self.canvas.current_category = cat
        self.canvas.update()
        self.status.showMessage(f"Category -> {cat}")

    def _select_category_btn(self, idx: int):
        """Select a category from a keyboard shortcut (1=crack, 2=spalling)."""
        btn = self._cat_group.button(idx)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
            self._on_category_changed(idx)

    def _nudge_brush_size(self, delta: int):
        """Bump brush size from the [/ ] shortcuts; spinbox clamps the range."""
        self._spn_brush_size.setValue(self._spn_brush_size.value() + delta)

    def _on_brush_reset(self):
        """Reload the detected mask for the current image, discarding edits."""
        if self.current_idx < 0:
            self.status.showMessage(self.tr_("brush_no_image"))
            return
        filename = self.image_files[self.current_idx]
        self._show_image(self.current_idx, force_reload=True)
        self._edited.pop(filename, None)
        self._refresh_list_colors()
        self.status.showMessage(self.tr_("brush_reset"))

    def _save_all_artifacts(self, silent: bool = False,
                            only_if_edited: bool = False,
                            async_derived: bool = True) -> bool:
        """
        Persist mask + bbox JSON + Result/<stem>.{png,txt}.

        only_if_edited: if True (auto-save on switch), do nothing when neither
            mask nor bbox was touched this session.

        Returns True on success or "nothing to save", False on hard error.
        """
        if self.current_idx < 0 or self.origin_dir is None:
            if not silent:
                self.status.showMessage(self.tr_("brush_no_image"))
            return False
        filename = self.image_files[self.current_idx]
        mask_dirty = bool(self._edited.get(filename))
        bbox_dirty = bool(self._bbox_edited.get(filename))
        if only_if_edited and not (mask_dirty or bbox_dirty):
            return True
        if self.output_dir is None:
            self._sync_output_dir()
        if self.output_dir is None:
            return False

        import cv2 as _cv2

        mc = self.canvas.brush_mask_crack
        ms = self.canvas.brush_mask_spalling

        # ----- 1. Mask (single-channel integer label: 0=bg, 1=crack, 2=spalling) -----
        if mc is not None or ms is not None:
            label = encode_label_mask(mc, ms)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mask_out = self.output_dir / mask_store.mask_name(filename)
            _cv2.imwrite(str(mask_out), label)

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

        # ----- 2. BBox JSON -----
        bbox_path = self.output_dir / mask_store.bbox_name(filename)
        save_bboxes(
            bbox_path,
            filename,
            self.canvas.bbox_interaction.boxes,
            self.current_scale,
            self.current_scale_source,
        )

        # ----- 3. Result/<stem>.png + .txt (heavy: re-reads origin, runs the
        #         full crack-metric, encodes a big PNG — skipped by the Viewer API
        #         tool, which computes metrics at upload time instead) -----
        if self.export_result_on_save and self.result_dir is not None:
            origin_path = str(self.origin_dir / filename)
            origin = _cv2.imread(origin_path)
            if origin is not None:
                export_result(
                    self.result_dir, filename, origin,
                    mc, ms,
                    list(self.canvas.bbox_interaction.boxes),
                    self.current_scale,
                )

        # ----- 4. Bookkeeping -----
        self._edited.pop(filename, None)
        self._bbox_edited.pop(filename, None)
        self._refresh_list_colors()
        if not silent:
            self.status.showMessage(self.tr_("brush_saved", p=str(self.output_dir)))
        return True

    def _on_derived_ready(self, token: str, hi, r15):
        """Refresh the canvas overlays from a background derived-mask result,
        but only if that image is still on screen (else the file is written
        and we skip the stale overlay)."""
        if self.current_idx < 0:
            return
        if token == self.image_files[self.current_idx]:
            self.canvas.set_highlight(hi)
            self.canvas.set_repair15(r15)

    def _on_brush_save(self):
        self._save_all_artifacts(silent=False)

    def _on_mask_edited(self):
        if self.current_idx < 0:
            return
        filename = self.image_files[self.current_idx]
        if not self._edited.get(filename):
            self._edited[filename] = True
            self._refresh_list_colors()

    def _on_toggle_highlight(self, checked: bool):
        self.canvas.show_highlight = bool(checked)
        self.canvas.update()

    def _on_toggle_repair15(self, checked: bool):
        self.canvas.show_repair15 = bool(checked)
        self.canvas.update()

    # ------------------------------------------------------------------
    # BBox callbacks
    # ------------------------------------------------------------------
    def _on_bbox_toggle(self, checked: bool):
        # Mutually exclusive with brush and measure modes
        if checked and self.canvas.brush_mode:
            self._btn_brush_toggle.setChecked(False)
        if checked and self._btn_measure.isChecked():
            self._btn_measure.setChecked(False)
        if checked and self.canvas.sam_mode:
            self._btn_sam_toggle.setChecked(False)
        self.canvas.set_bbox_mode(bool(checked))
        self._btn_bbox_toggle.setText(
            self.tr_("btn_bbox_off") if checked else self.tr_("btn_bbox_on"))

    def _on_bbox_commit(self):
        if not self.canvas.bbox_mode:
            return
        if self.canvas.bbox_padding_px <= 0:
            self.status.showMessage(self.tr_("bbox_no_scale"))
            return
        ok = self.canvas.bbox_interaction.commit(self.canvas.bbox_padding_px)
        if not ok:
            self.status.showMessage(self.tr_("bbox_need_more_clicks"))
            return
        self._mark_bbox_edited()
        self.canvas.update()

    def _on_bbox_cancel(self):
        if not self.canvas.bbox_mode:
            return
        if self.canvas.bbox_interaction.cancel():
            self.canvas.update()

    def _on_bbox_delete(self):
        if not self.canvas.bbox_mode:
            return
        if self.canvas.bbox_interaction.delete_selected():
            self._mark_bbox_edited()
            self.canvas.update()

    def _on_bbox_edited(self):
        self._mark_bbox_edited()

    def _mark_bbox_edited(self):
        if self.current_idx < 0:
            return
        fname = self.image_files[self.current_idx]
        if not self._bbox_edited.get(fname):
            self._bbox_edited[fname] = True

    # ------------------------------------------------------------------
    # SAM callbacks
    # ------------------------------------------------------------------
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
        self._btn_sam_undo.setEnabled(bool(checked))
        if checked:
            self.status.showMessage(self.tr_("sam_hint"))

    def _on_sam_commit(self):
        if self.canvas.commit_sam():
            self.status.showMessage(self.tr_("sam_committed"))

    def _on_sam_cancel(self):
        self.canvas.cancel_sam()

    def _on_sam_undo(self):
        """되돌리기 button: drop the last SAM point (no-op outside SAM mode)."""
        if self.canvas.sam_mode and self.canvas.undo_sam_point():
            self.status.showMessage(self.tr_("sam_undone"))

    def _on_escape(self):
        """Esc dispatcher: undo a SAM point in SAM mode, else cancel a bbox.

        Esc is a single global shortcut (shortcuts.py); routing it by mode here
        avoids two conflicting Esc bindings (which fire ambiguously / not at all)."""
        if self.canvas.sam_mode:
            self._on_sam_undo()
        else:
            self._on_bbox_cancel()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = ImageCanvas()
        self.canvas.mask_edited.connect(self._on_mask_edited)
        self.canvas.bbox_edited.connect(self._on_bbox_edited)
        self.canvas.measure_completed.connect(self._on_measure_completed)

        panel_scroll = build_side_panel(self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.canvas)
        splitter.addWidget(panel_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        # Give the panel a comfortable starting width; the canvas absorbs all
        # window resizing so the panel no longer jumps around on resize.
        splitter.setSizes([1100, 360])
        self._splitter = splitter
        root.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(self.tr_("ready"))

        register_shortcuts(self)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _reload_data(self):
        self.image_files = []
        self.current_idx = -1
        self._edited.clear()
        self.file_list.clear()
        self.canvas.clear()
        if self.origin_dir is not None:
            self._load_data()

    def _load_data(self):
        if self.origin_dir is None:
            self.status.showMessage(self.tr_("warn_select_first"))
            return
        if not self.origin_dir.exists():
            QMessageBox.critical(self,
                self.tr_("err_no_origin_title"), self.tr_("err_no_origin_msg"))
            return

        files = sorted([
            f.name for f in self.origin_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ])
        if not files:
            QMessageBox.warning(self,
                self.tr_("warn_title"),
                self.tr_("warn_no_images", dir=str(self.origin_dir)))
            return

        self.image_files = files
        self.file_list.clear()
        for name in files:
            self.file_list.addItem(name)

        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.file_list.setCurrentRow(0)
        self._refresh_list_colors()
        self.status.showMessage(self.tr_("loaded_n_images", n=len(files)))

    # ------------------------------------------------------------------
    # Image switching
    # ------------------------------------------------------------------
    @staticmethod
    def _base_stem(name: str) -> str:
        """Strip known annotation suffixes to get the bare photo stem."""
        stem = Path(name).stem
        for suffix in MASK_NAME_SUFFIXES:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem

    def _show_image(self, idx: int, force_reload: bool = False):
        if idx < 0 or idx >= len(self.image_files):
            return

        if (not force_reload) and self.current_idx >= 0 and self.current_idx != idx:
            self._save_all_artifacts(silent=True, only_if_edited=True)

        filename = self.image_files[idx]
        origin_path = str(self.origin_dir / filename)
        import sys as _sys

        mask_path = None
        source = "none"

        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        mask_path = str(resolved) if resolved is not None else None

        print(f"[load] {filename} -> {source}: {mask_path}", file=_sys.stderr)

        try:
            origin, crack_mask, spalling_mask = load_origin_and_masks(
                origin_path, mask_path)
        except FileNotFoundError as e:
            self.status.showMessage(f"[ERROR] {e}")
            return

        self.current_idx = idx
        self.canvas.set_image(origin, crack_mask, spalling_mask)

        # ----- derived-mask overlays (read saved files; else clear) -----
        import cv2 as _cv2_load
        hi_name = mask_store.mask_name(filename)
        if self.highlight_dir is not None and (self.highlight_dir / hi_name).exists():
            arr = _cv2_load.imread(str(self.highlight_dir / hi_name),
                                   _cv2_load.IMREAD_UNCHANGED)
            self.canvas.set_highlight(arr)
        else:
            self.canvas.set_highlight(None)
        if self.repair15_dir is not None and (self.repair15_dir / hi_name).exists():
            arr = _cv2_load.imread(str(self.repair15_dir / hi_name),
                                   _cv2_load.IMREAD_UNCHANGED)
            self.canvas.set_repair15(arr)
        else:
            self.canvas.set_repair15(None)

        # ----- ArUco scale + outline overlay -----
        scale, source, aruco_corners = self.scale_tracker.update_for_image(origin)
        self.current_scale = scale
        self.current_scale_source = source
        self.canvas.set_bbox_padding_px(scale * 15.0 if scale else 0.0)
        # Display-only outline; None when no fresh detection on this image,
        # so we never show stale ArUco from a previous load.
        self.canvas.set_aruco_corners(aruco_corners)
        self._refresh_scale_label()
        self._btn_bbox_toggle.setEnabled(scale is not None)

        # ----- BBox JSON -----
        if self.output_dir is not None:
            bbox_path = self.output_dir / mask_store.bbox_name(filename)
            self.canvas.bbox_interaction.boxes = load_bboxes(bbox_path)
        else:
            self.canvas.bbox_interaction.boxes = []

        # File list selection
        self.file_list.blockSignals(True)
        self.file_list.setCurrentRow(idx)
        self.file_list.blockSignals(False)

        if force_reload:
            self._edited.pop(filename, None)
            self._bbox_edited.pop(filename, None)

        self._refresh_list_colors()
        self._update_status_for_current()

    def _refresh_scale_label(self):
        # Internal canonical scale is px/cm (from ArUco). The right-side
        # label shows mm/px = 10 / (px/cm).
        if self.current_scale is None or self.current_scale <= 0:
            txt = self.tr_("lbl_scale_template",
                           scale="--",
                           source=self.tr_("scale_source_none"))
        else:
            mm_per_px = 10.0 / self.current_scale
            src_key = f"scale_source_{self.current_scale_source}"
            txt = self.tr_("lbl_scale_template",
                           scale=f"{mm_per_px:.4f}",
                           source=self.tr_(src_key))
        self._lbl_scale.setText(txt)

    def _update_status_for_current(self):
        if self.current_idx < 0:
            return
        filename = self.image_files[self.current_idx]
        edited = "yes" if self._edited.get(filename) else "no"
        self.status.showMessage(self.tr_(
            "status_template",
            i=self.current_idx + 1, n=len(self.image_files),
            f=filename, edited=edited))

    def _has_labeling_file(self, filename: str) -> bool:
        """True if a mask for this image already exists in Labeling/."""
        if self.output_dir is None or not self.output_dir.exists():
            return False
        return (self.output_dir / mask_store.mask_name(filename)).exists()

    def _refresh_list_colors(self):
        """
        Color priority:
            edited (unsaved this session) -> yellow
            already labeled on disk       -> green
            otherwise                     -> default gray
        """
        for i, fname in enumerate(self.image_files):
            item = self.file_list.item(i)
            if item is None:
                continue
            if self._edited.get(fname):
                item.setForeground(QColor(240, 220, 80))   # yellow
            elif self._has_labeling_file(fname):
                item.setForeground(QColor(120, 220, 120))  # green
            else:
                item.setForeground(QColor(220, 220, 220))  # gray

    def _on_list_row_changed(self, row: int):
        if row != self.current_idx:
            self._show_image(row)

    def go_prev(self):
        if self.current_idx > 0:
            self._show_image(self.current_idx - 1)

    def go_next(self):
        if 0 <= self.current_idx < len(self.image_files) - 1:
            self._show_image(self.current_idx + 1)

    def closeEvent(self, event):
        # Persist the in-flight image one last time before exit, but only
        # if the user actually edited it this session.
        self._save_all_artifacts(silent=True, only_if_edited=True,
                                 async_derived=False)
        super().closeEvent(event)
