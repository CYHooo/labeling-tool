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
from labeling_tool.core.mask_io import find_mask_path, load_origin_and_masks
from labeling_tool.core.canvas import ImageCanvas
from labeling_tool.core.bbox import (
    ScaleTracker, save_bboxes, load_bboxes,
    scale_from_two_points, MARKER_PHYSICAL_CM,
)
from labeling_tool.core.rebuild import process_one
from labeling_tool.core.result import export_result
from labeling_tool.core.window.styles import STYLESHEET
from labeling_tool.core.window.ui_builder import build_side_panel
from labeling_tool.core.window.shortcuts import register_shortcuts


class MainWindow(QMainWindow):
    # When True, saving also writes Result/<stem>.{png,txt} — a full-res preview
    # image plus a crack-metrics text report. That step re-reads the origin,
    # runs the full skeleton+width metric, and encodes a large PNG (~2s on a
    # panorama), so the V API tool turns it OFF: there, metrics are computed at
    # upload time (V4) and Result/ is never consumed.
    export_result_on_save: bool = True

    def __init__(self):
        super().__init__()

        self.lang: str = DEFAULT_LANG

        self.origin_dir: Path | None = None
        self.detected_dir: Path | None = None
        self.output_dir: Path | None = None
        self.rebuilt_dir: Path | None = None
        self.result_dir: Path | None = None

        if Path("Origin").exists():
            self.origin_dir = Path("Origin").resolve()
        if Path("Detected").exists():
            self.detected_dir = Path("Detected").resolve()
        self._sync_output_dir()

        self.image_files: list[str] = []
        self.current_idx: int = -1
        self._edited: dict[str, bool] = {}
        self._mask_filename: dict[str, str | None] = {}

        # ----- new state for bbox / rebuild / result -----
        self.scale_tracker = ScaleTracker()
        self.current_scale: float | None = None
        self.current_scale_source: str = "none"
        self._bbox_edited: dict[str, bool] = {}

        self._build_ui()
        self.setWindowTitle(self.tr_("window_title"))
        self.setMinimumSize(820, 560)
        self._apply_initial_geometry()

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
        self._refresh_path_labels()

        self._grp_brush.setTitle(self.tr_("group_brush"))
        self._btn_brush_toggle.setText(
            self.tr_("btn_brush_off") if self.canvas.brush_mode
            else self.tr_("btn_brush_on"))
        self._lbl_brush_size.setText(self.tr_("lbl_brush_size"))
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
        self._btn_rebuild_force.setText(self.tr_("btn_rebuild_force"))

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
        """Derive output_dir, rebuilt_dir, result_dir from origin_dir.parent."""
        if self.origin_dir is not None:
            parent = self.origin_dir.parent
            self.output_dir  = parent / OUTPUT_DIR_NAME
            self.rebuilt_dir = parent / "Rebuilt"
            self.result_dir  = parent / "Result"
        else:
            self.output_dir = self.rebuilt_dir = self.result_dir = None

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
        if checked and self._btn_measure.isChecked():
            self._btn_measure.setChecked(False)   # leave measure mode
        self.canvas.brush_mode = bool(checked)
        self._btn_brush_toggle.setText(
            self.tr_("btn_brush_off") if checked else self.tr_("btn_brush_on"))
        self.canvas.update()

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
                            only_if_edited: bool = False) -> bool:
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
            out_name = self._mask_filename.get(filename)
            if not out_name:
                out_name = f"{Path(filename).stem}.png"
            mask_out = self.output_dir / out_name
            _cv2.imwrite(str(mask_out), bgr)

        # ----- 2. BBox JSON -----
        bbox_path = self.output_dir / f"{Path(filename).stem}.bbox.json"
        save_bboxes(
            bbox_path,
            filename,
            self.canvas.bbox_interaction.boxes,
            self.current_scale,
            self.current_scale_source,
        )

        # ----- 3. Result/<stem>.png + .txt (heavy: re-reads origin, runs the
        #         full crack-metric, encodes a big PNG — skipped by the V API
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

    def _on_brush_save(self):
        self._save_all_artifacts(silent=False)

    def _on_mask_edited(self):
        if self.current_idx < 0:
            return
        filename = self.image_files[self.current_idx]
        if not self._edited.get(filename):
            self._edited[filename] = True
            self._refresh_list_colors()

    # ------------------------------------------------------------------
    # BBox callbacks
    # ------------------------------------------------------------------
    def _on_bbox_toggle(self, checked: bool):
        # Mutually exclusive with brush and measure modes
        if checked and self.canvas.brush_mode:
            self._btn_brush_toggle.setChecked(False)
        if checked and self._btn_measure.isChecked():
            self._btn_measure.setChecked(False)
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
    # Rebuild callbacks
    # ------------------------------------------------------------------
    def _on_rebuild_force(self):
        """Re-run intensity-guided rebuild on the current image.

        Coarse source priority: Labeling/<mask> (current edits) > Detected/<mask>.
        Using Labeling/ as input means each manual rebuild refines on top of
        the user's edits instead of regressing to the raw AI detection.
        The rebuild result OVERWRITES Labeling/<mask> so it becomes the new
        editing baseline; a copy is also cached in Rebuilt/<mask>.
        """
        if self.current_idx < 0:
            return
        if self.origin_dir is None:
            return
        filename = self.image_files[self.current_idx]
        ans = QMessageBox.question(
            self,
            self.tr_("rebuild_confirm_title"),
            self.tr_("rebuild_confirm_msg"),
        )
        if ans != QMessageBox.Yes:
            return

        # Pick coarse source: prefer Labeling/ over Detected/
        coarse_path = None
        if self.output_dir is not None and self.output_dir.exists():
            coarse_path = find_mask_path(filename, str(self.output_dir))
        if coarse_path is None and self.detected_dir is not None:
            coarse_path = find_mask_path(filename, str(self.detected_dir))
        if coarse_path is None:
            self.status.showMessage(
                self.tr_("rebuild_failed", err="no coarse mask"))
            return

        origin_path = str(self.origin_dir / filename)
        mask_name = self._mask_filename.get(filename) or Path(coarse_path).name

        self.status.showMessage(self.tr_("status_rebuilding"))
        QApplication.processEvents()
        try:
            import cv2 as _cv2
            raw = _cv2.imread(coarse_path, _cv2.IMREAD_UNCHANGED)
            if raw is None:
                raise RuntimeError(f"failed to read coarse mask: {coarse_path}")
            if raw.ndim == 3:
                coarse_gray = raw[..., 2]
            else:
                coarse_gray = raw
            origin_bgr = _cv2.imread(origin_path)
            if origin_bgr is None:
                raise RuntimeError(f"failed to read origin: {origin_path}")
            guided, _, _ = process_one(origin_bgr, coarse_gray,
                                       compute_length=False)
            rgb = np.zeros((*guided.shape, 3), dtype=np.uint8)
            rgb[..., 2] = guided

            # Cache to Rebuilt/<mask_name>
            if self.rebuilt_dir is not None:
                self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.rebuilt_dir / mask_name), rgb)
            # Overwrite Labeling/<mask_name> so the rebuild result becomes
            # the new editing baseline.
            if self.output_dir is not None:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                _cv2.imwrite(str(self.output_dir / mask_name), rgb)
        except Exception as e:
            self.status.showMessage(self.tr_("rebuild_failed", err=str(e)))
            return

        self._edited.pop(filename, None)
        self._bbox_edited.pop(filename, None)
        self.status.showMessage(self.tr_("rebuild_done", name=mask_name))
        self._show_image(self.current_idx, force_reload=True)

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
        self._mask_filename.clear()
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
        mask_source = "none"

        # Step 0: the user's saved edits in Labeling/ are authoritative and must
        # win over the (Detected-derived) Rebuilt/ cache — otherwise a prebuilt
        # Rebuilt entry keeps showing the unedited mask after the user saves.
        if self.output_dir is not None and self.output_dir.exists():
            mask_path = find_mask_path(filename, str(self.output_dir))
            if mask_path is not None:
                mask_source = "labeling"

        # Step 1: else use the cached Rebuilt/<mask> (refined Detected).
        if (mask_path is None and self.rebuilt_dir is not None
                and self.rebuilt_dir.exists()):
            mask_path = find_mask_path(filename, str(self.rebuilt_dir))
            if mask_path is not None:
                mask_source = "rebuilt"

        # Step 2: Rebuilt/ missing -> run rebuild to populate it.
        # Coarse source priority: Labeling/ (preserves existing edits) > Detected/.
        if mask_path is None:
            coarse_path = None
            coarse_from = None
            if self.output_dir is not None and self.output_dir.exists():
                coarse_path = find_mask_path(filename, str(self.output_dir))
                if coarse_path is not None:
                    coarse_from = "labeling"
            if coarse_path is None and self.detected_dir is not None:
                coarse_path = find_mask_path(filename, str(self.detected_dir))
                if coarse_path is not None:
                    coarse_from = "detected"

            if coarse_path is None:
                print(f"[load] {filename}: no mask in Rebuilt/, Labeling/, or "
                      f"Detected/", file=_sys.stderr)
                self.status.showMessage(
                    f"No mask found for {filename} in any folder")
            else:
                print(f"[rebuild] {filename}: coarse source = "
                      f"{coarse_from}/{Path(coarse_path).name}", file=_sys.stderr)
                self.status.showMessage(self.tr_("status_rebuilding"))
                QApplication.processEvents()
                try:
                    import cv2 as _cv2
                    raw = _cv2.imread(coarse_path, _cv2.IMREAD_UNCHANGED)
                    if raw is None:
                        raise RuntimeError(
                            f"cv2.imread returned None for {coarse_path}")
                    coarse_gray = raw[..., 2] if raw.ndim == 3 else raw
                    origin_bgr_rb = _cv2.imread(origin_path)
                    if origin_bgr_rb is None:
                        raise RuntimeError(
                            f"cv2.imread returned None for {origin_path}")
                    guided, _, _ = process_one(origin_bgr_rb, coarse_gray,
                                               compute_length=False)
                    if self.rebuilt_dir is not None:
                        self.rebuilt_dir.mkdir(parents=True, exist_ok=True)
                        out_name = Path(coarse_path).name
                        rebuilt_path = self.rebuilt_dir / out_name
                        rgb = np.zeros((*guided.shape, 3), dtype=np.uint8)
                        rgb[..., 2] = guided
                        _cv2.imwrite(str(rebuilt_path), rgb)
                        mask_path = str(rebuilt_path)
                        mask_source = f"rebuilt(from {coarse_from})"
                        self.status.showMessage(
                            self.tr_("rebuild_done", name=out_name))
                except Exception as e:
                    import traceback as _tb
                    print(f"[rebuild] {filename}: FAILED {e}", file=_sys.stderr)
                    _tb.print_exc()
                    self.status.showMessage(
                        self.tr_("rebuild_failed", err=str(e)))
                    # Fallback: load coarse source as-is so user can still work
                    mask_path = coarse_path
                    mask_source = f"{coarse_from}(rebuild_failed)"

        print(f"[load] {filename} -> {mask_source}: {mask_path}",
              file=_sys.stderr)

        try:
            origin, crack_mask, spalling_mask = load_origin_and_masks(
                origin_path, mask_path)
        except FileNotFoundError as e:
            self.status.showMessage(f"[ERROR] {e}")
            return

        self.current_idx = idx
        self.canvas.set_image(origin, crack_mask, spalling_mask)
        self._mask_filename[filename] = (
            Path(mask_path).name if mask_path else None
        )

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
            bbox_path = self.output_dir / f"{Path(filename).stem}.bbox.json"
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
        return find_mask_path(filename, str(self.output_dir)) is not None

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
        self._save_all_artifacts(silent=True, only_if_edited=True)
        super().closeEvent(event)
