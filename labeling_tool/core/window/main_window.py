"""MainWindow class — application orchestration and state management."""

from pathlib import Path

import numpy as np

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QStatusBar, QMessageBox, QApplication, QInputDialog, QListWidgetItem,
)
from PyQt5.QtGui import QColor, QDesktopServices

from labeling_tool.core.constants import (
    OUTPUT_DIR_NAME,
    IMAGE_EXTENSIONS, MASK_NAME_SUFFIXES,
)
from labeling_tool.core.i18n import tr, language_manager
from labeling_tool.core.mask_io import load_origin_and_layers
from labeling_tool.core.mask_codec import encode_layers
from labeling_tool.core.classes import ClassRegistry, CRACK_ID, SPALLING_ID
from labeling_tool.core.canvas import ImageCanvas
from labeling_tool.core.bbox import (
    ScaleTracker, save_bboxes, load_bboxes, load_scale_info,
    scale_from_two_points, MARKER_PHYSICAL_CM,
)
from labeling_tool.session import mask_store
from labeling_tool.core.result import export_result
from labeling_tool.core.window.styles import STYLESHEET
from labeling_tool.core.window.ui_builder import (
    MARK_ROLE, SECONDARY_TEXT_ROLE, TwoPartItemDelegate, build_help_dialog,
    build_side_panel,
)
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

        self.class_registry = ClassRegistry()
        self._class_sync_status = "offline"
        # SAM moved crack -> spalling when it was turned on; leaving SAM
        # gives crack back unless the user picked another category there.
        self._sam_took_crack = False

        self._build_ui()
        self.canvas.set_class_registry(self.class_registry)
        self._refresh_class_pickers()
        self.setWindowTitle(self.tr_("window_title"))
        self.setMinimumSize(820, 560)
        self._apply_initial_geometry()

        # Follow language changes made anywhere else (e.g. reopening the
        # login screen). Disconnect on close so a reopened window doesn't
        # stack listeners on the process-wide LanguageManager singleton.
        self._lang_conn = language_manager().languageChanged.connect(
            self._on_language_changed_elsewhere)

        from labeling_tool.ui.derived_mask_worker import DerivedMaskSignals
        self._derived_signals = DerivedMaskSignals()
        self._derived_signals.done.connect(self._on_derived_ready)
        self._chk_show_repair15.setChecked(True)   # 15cm contour on by default
        self._offer_refit_for: str | None = None   # filename awaiting silent bbox refit

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
        return tr(key, **kwargs)

    def _on_language_changed_elsewhere(self, _code: str) -> None:
        self._retranslate_ui()

    def _disconnect_language_manager(self) -> None:
        conn = getattr(self, "_lang_conn", None)
        if conn is not None:
            try:
                language_manager().languageChanged.disconnect(conn)
            except TypeError:
                pass  # already disconnected
            self._lang_conn = None

    def _retranslate_ui(self):
        self.setWindowTitle(self.tr_("window_title"))
        self._refresh_job_info()
        self._btn_help.setToolTip(self.tr_("group_hint"))
        if not self._btn_sam_toggle.isEnabled():
            self._tool_picker.setToolToolTip(2, self.tr_("sam_unavailable"))

        self._grp_list.setTitle(self.tr_("group_list"))
        self._refresh_list_header()
        self.btn_prev.setText(self.tr_("btn_prev"))
        self.btn_next.setText(self.tr_("btn_next"))
        self.btn_save.setText(self.tr_("btn_save"))
        self._refresh_nav_tooltips()

        self._grp_tools.setTitle(self.tr_("group_tools"))
        for idx, key in enumerate(("tool_view", "tool_brush", "tool_sam", "tool_bbox")):
            self._tool_picker.setToolText(idx, self.tr_(key))
        for title, title_key, hint, hint_key in self._tool_texts:
            title.setText(self.tr_(title_key))
            hint.setText(self.tr_(hint_key))
        self._refresh_class_pickers()

        self._grp_display.setTitle(self.tr_("group_display"))
        self._chk_show_highlight.setText(self.tr_("btn_show_highlight"))
        self._chk_show_repair15.setText(self.tr_("btn_show_repair15"))
        self._btn_measure.setText(
            self.tr_("btn_measure_cancel") if self.canvas.measure_mode
            else self.tr_("btn_measure"))
        self._refresh_scale_label()

        # hidden mode switches (the tool picker shows the mode)
        self._btn_brush_toggle.setText(
            self.tr_("btn_brush_off") if self.canvas.brush_mode
            else self.tr_("btn_brush_on"))
        self._btn_bbox_toggle.setText(
            self.tr_("btn_bbox_off") if self.canvas.bbox_mode
            else self.tr_("btn_bbox_on"))
        self._btn_sam_toggle.setText(self.tr_("btn_sam"))
        self._lbl_brush_size.setText(self.tr_("lbl_brush_size"))
        self._chk_fine_annotation.setText(self.tr_("btn_fine_annotation"))
        self._btn_brush_reset.setText(self.tr_("btn_brush_reset"))
        self._btn_undo.setText(self.tr_("btn_undo"))
        self._btn_redo.setText(self.tr_("btn_redo"))
        self._btn_sam_commit.setText(self.tr_("btn_sam_commit"))
        self._btn_sam_cancel.setText(self.tr_("btn_sam_cancel"))
        self._btn_sam_undo.setText(self.tr_("btn_sam_undo"))

        help_dialog = getattr(self, "_help_dialog", None)
        if help_dialog is not None:
            help_dialog.setWindowTitle(self.tr_("group_hint"))
            self._lbl_hint.setText(self.tr_("hint_text"))
            self._btn_open_logs.setText(self.tr_("btn_open_logs"))

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

    # ------------------------------------------------------------------
    # Job info + list rows (overridden by the Viewer window, which knows the job)
    # ------------------------------------------------------------------
    def _job_info(self) -> tuple[str, str]:
        """(job id, inspection name) shown above the image list."""
        return "—", "—"

    def _refresh_job_info(self):
        job_id, inspection = self._job_info()
        self._lbl_job_info.set_full_text(self.tr_(
            "job_info_line", job=job_id, name=inspection,
            count=self._photo_count_text()))

    def _photo_count_text(self) -> str:
        """Photo count in the job line. Overridable."""
        return self.tr_("photo_count", n=len(self.image_files))

    def _refresh_list_header(self):
        self._list_header.set_labels(self.tr_("list_col_number"),
                                     self.tr_("list_col_file"))
        self._list_header.setToolTip(self.tr_("list_marks_tip"))
        self._fit_list_columns()

    def _fit_list_columns(self):
        """Size the id column to the widest id or its header, whichever is
        wider, so the file names (and their header) start in one column."""
        delegate = self.file_list.itemDelegate()
        if not isinstance(delegate, TwoPartItemDelegate):
            return
        ids = [self.file_list.item(i).text() for i in range(self.file_list.count())
               if self.file_list.item(i).data(SECONDARY_TEXT_ROLE)]
        delegate.fit_primary_column(ids + [self._list_header.labels()[0]],
                                    self.file_list.font())
        self._list_header.update()
        self.file_list.viewport().update()

    def _refresh_nav_tooltips(self):
        for btn, key in ((self.btn_prev, "A"), (self.btn_next, "D"),
                         (self.btn_save, "S / Ctrl+S"), (self._btn_undo, "Ctrl+Z"),
                         (self._btn_redo, "Ctrl+Y / Ctrl+Shift+Z"),
                         (self._btn_sam_commit, "Enter"), (self._btn_sam_cancel, "Esc"),
                         (self._btn_sam_undo, "Ctrl+Z")):
            btn.setToolTip(self.tr_("tip_shortcut", shortcut=key))

    def _open_log_folder(self):
        """Open the folder holding app.log in the file manager, so a user
        can send the log when something went wrong."""
        from labeling_tool import logging_setup
        folder = logging_setup.log_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:              # never let a slot raise
            self.status.showMessage(str(exc))
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            # no file manager to hand it to: at least say where it is
            self.status.showMessage(self.tr_("log_folder_path", path=str(folder)))

    def _show_help(self):
        if getattr(self, "_help_dialog", None) is None:
            self._help_dialog = build_help_dialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    # ------------------------------------------------------------------
    # Tool picker: the selected tool is the editing mode
    # ------------------------------------------------------------------
    def _tool_mode_buttons(self):
        """Mode switch per tool index; the view tool (0) has none."""
        return (None, self._btn_brush_toggle, self._btn_sam_toggle,
                self._btn_bbox_toggle)

    def _on_tool_changed(self, idx: int):
        buttons = self._tool_mode_buttons()
        target = buttons[idx] if 0 <= idx < len(buttons) else None
        if target is None:
            for btn in buttons[1:]:
                btn.setChecked(False)
        elif target.isEnabled():
            target.setChecked(True)      # its handler leaves the other modes
        self._sync_tool()

    def _sync_tool(self, *_):
        """Select the active mode's tool (after B / X, measuring, or a
        refused switch); the view tool when no editing mode is on."""
        buttons = self._tool_mode_buttons()
        idx = next((i for i, btn in enumerate(buttons)
                    if btn is not None and btn.isChecked()), 0)
        self._tool_picker.blockSignals(True)
        self._tool_picker.setCurrentIndex(idx)
        self._tool_picker.blockSignals(False)

    def _refresh_tools(self):
        """A tool whose switch is disabled (SAM without its model, the repair
        area without a scale) is disabled in the picker too, and its mode
        ends. Signals stay blocked meanwhile, so no tool change on the way
        can switch the user into another mode."""
        for btn in self._tool_mode_buttons():
            if btn is not None and not btn.isEnabled() and btn.isChecked():
                btn.setChecked(False)
        self._tool_picker.blockSignals(True)
        for idx, btn in enumerate(self._tool_mode_buttons()):
            if btn is not None:
                self._tool_picker.setToolEnabled(idx, btn.isEnabled())
        self._tool_picker.blockSignals(False)
        self._sync_tool()

    def _toggle_mode_shortcut(self, btn):
        """B / X: toggle a tool's mode, unless the tool is unavailable."""
        if btn.isEnabled():
            btn.toggle()

    def _on_photo_saved(self, filename: str) -> None:
        """A changed photo was written to disk. Overridable."""

    def _list_item_mark(self, filename: str) -> str | None:
        """Upload mark of a row ("uploaded" / "pending" / None). Overridable."""
        return None

    def _list_item_parts(self, filename: str) -> tuple[str, str]:
        """(main text, dim second part) of the image-list row for filename."""
        return filename, ""

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
        if not checked:
            # The release may never reach the brush: close the open stroke
            # so it is undoable and class switching is not locked.
            self.canvas.finish_brush_stroke()
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
        measure_pts = self.canvas.measure_points()   # the 2 clicked points
        self.current_scale = scale
        self.current_scale_source = "manual"
        # Feed the session tracker so later images without ArUco fall back to it.
        self.scale_tracker.last_known_scale = scale
        self.canvas.set_bbox_padding_px(scale * 15.0)
        self._btn_bbox_toggle.setEnabled(True)
        self._refresh_tools()
        self._refresh_scale_label()
        mm_per_px = 10.0 / scale
        self.status.showMessage(
            self.tr_("measure_done", scale=f"{mm_per_px:.4f}"))
        # Persist immediately so the manual scale survives an image switch /
        # is used at upload even if the user doesn't redraw the mask.
        if self.current_idx >= 0:
            if self._save_all_artifacts(silent=True):
                # the upload sends px_per_cm: a new scale needs uploading again
                self._on_photo_saved(self.image_files[self.current_idx])
                self._refresh_list_colors()
        self._btn_measure.setChecked(False)         # leaves measure mode (clears line)
        self.canvas.set_measure_points(measure_pts)  # keep the line visible after measuring

    def _on_brush_size_changed(self, value: int):
        self.canvas.brush_size = int(value)
        self.canvas.update()

    def _nudge_brush_size(self, delta: int):
        """Bump brush size from the [/ ] shortcuts; spinbox clamps the range."""
        self._spn_brush_size.setValue(self._spn_brush_size.value() + delta)

    def _on_brush_reset(self):
        """Reload the detected mask for the current image, discarding edits."""
        if self.current_idx < 0:
            self.status.showMessage(self.tr_("brush_no_image"))
            return
        filename = self.image_files[self.current_idx]
        before = self.canvas.snapshot()
        # Reloading starts a fresh history (earlier strokes cannot be undone
        # past a reset); the reset itself is recorded, so Ctrl+Z brings the
        # discarded edits back.
        self._show_image(self.current_idx, force_reload=True)
        self.canvas.record_external_change(before)
        self._edited.pop(filename, None)
        self._refresh_list_colors()
        self.status.showMessage(self.tr_("brush_reset"))

    # ------------------------------------------------------------------
    # Undo / redo (mask edits on the current image)
    # ------------------------------------------------------------------
    # Ctrl+Z / Ctrl+Y mean the same in every tool: unconfirmed SAM or
    # repair-area points are taken back first, then mask edits.
    def _on_undo(self):
        c = self.canvas
        if c.sam_mode:
            if c.can_undo_sam_point():
                self._on_sam_undo()
                return
            # no points left: once a mask edit is undone, point redo steps
            # would redo out of order (keep them when nothing is undone)
            if c.can_undo():
                c.cancel_sam()
        if c.bbox_mode and c.bbox_interaction.undo_click():
            c.update()
            return
        c.undo()

    def _on_redo(self):
        c = self.canvas
        if c.sam_mode and c.redo_sam_point():
            self.status.showMessage(self.tr_("sam_redone"))
            return
        c.redo()

    def _refresh_undo_buttons(self):
        self._btn_undo.setEnabled(self.canvas.can_undo())
        self._btn_redo.setEnabled(self.canvas.can_redo())

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

        layers = self.canvas.layers

        # ----- 1. Mask (single-channel integer label: 0=bg, class ids above) -----
        if layers:
            label = encode_layers(layers)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            mask_out = self._save_mask_path(filename)
            _cv2.imwrite(str(mask_out), label)

            # ----- 1b. Derived masks: highlight + (scale-dependent) repair15 --
            snap = {c: m.copy() for c, m in layers.items()}
            scale = self.current_scale or 0.0
            if async_derived:
                # Offer to re-fit bboxes from the new 15cm contour only when the
                # mask actually changed and bboxes already exist.
                if mask_dirty and self.canvas.bbox_interaction.boxes:
                    self._offer_refit_for = filename
                self._dispatch_derived(filename, snap, scale)
            else:
                from labeling_tool.core.derived_masks import generate_derived_layers
                hi_path = (str(self.highlight_dir / mask_store.mask_name(filename))
                           if self.highlight_dir is not None else None)
                r15_path = (str(self.repair15_dir / mask_store.mask_name(filename))
                            if self.repair15_dir is not None else None)
                if self.highlight_dir is not None:
                    self.highlight_dir.mkdir(parents=True, exist_ok=True)
                if self.repair15_dir is not None:
                    self.repair15_dir.mkdir(parents=True, exist_ok=True)
                hi, r15 = generate_derived_layers(snap, scale, hi_path, r15_path)
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
            scale_points=(self.canvas.measure_points()
                          if self.current_scale_source == "manual" else None),
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
                    layers.get(CRACK_ID), layers.get(SPALLING_ID),
                    list(self.canvas.bbox_interaction.boxes),
                    self.current_scale,
                    extra_layers={c: m for c, m in layers.items()
                                  if c not in (CRACK_ID, SPALLING_ID)},
                    registry=self.class_registry,
                )

        # ----- 4. Bookkeeping -----
        if mask_dirty or bbox_dirty:
            self._on_photo_saved(filename)
        self._edited.pop(filename, None)
        self._bbox_edited.pop(filename, None)
        self._refresh_list_colors()
        if not silent:
            self.status.showMessage(self.tr_("brush_saved", p=str(self.output_dir)))
        return True

    # ------------------------------------------------------------------
    # Damage classes
    # ------------------------------------------------------------------
    def _class_base_url(self) -> str:
        return ""

    def _apply_class_registry(self, registry: ClassRegistry, status: str) -> None:
        self.class_registry = registry
        self._class_sync_status = status
        self.canvas.set_class_registry(registry)
        self._refresh_class_pickers()

    def _refresh_class_pickers(self) -> None:
        """Rebuild both class pickers from class_registry (names follow the
        language, so this also runs on retranslate)."""
        if not hasattr(self, "_class_picker_brush"):
            return                      # called while the panel is being built
        reg = self.class_registry
        cur = self.canvas.current_class_id
        if cur not in reg:
            cur = SPALLING_ID if self.canvas.sam_mode else CRACK_ID
            self.canvas.current_class_id = cur
        entries = [(c.class_id, reg.display_name(c.class_id, self.tr_), c.rgb)
                   for c in reg.classes()]
        # Ids found in a photo but unknown to the registry are not listed:
        # they cannot be chosen and only show grey on the canvas.
        ok, tip = self._can_add_class()
        for picker, disabled in ((self._class_picker_brush, frozenset()),
                                 (self._class_picker_sam, frozenset({CRACK_ID}))):
            shown = cur if cur not in disabled else SPALLING_ID
            picker.set_classes(entries, shown, disabled)
            picker.set_add_enabled(ok, tip)
            picker.retranslate(self.tr_("lbl_class"))

    def _set_current_class(self, cid: int) -> None:
        """Make `cid` the class the brush and SAM write (pickers, keys 1-9)."""
        reg = self.class_registry
        if cid not in reg:
            return
        if self.canvas._brushing:
            # A layer created mid-stroke would come after the stroke's undo
            # snapshot, leaving part of the stroke un-undoable: keep the
            # class and put the pickers back on it.
            self._show_current_class()
            return
        if self.canvas.sam_mode and not reg.is_area(cid):
            cid = SPALLING_ID                      # SAM selects areas only
        self.canvas.current_class_id = cid
        self._show_current_class()
        self.canvas.update()
        self.status.showMessage(self.tr_(
            "status_category_changed", cat=reg.display_name(cid, self.tr_)))

    def _show_current_class(self) -> None:
        """Point both pickers at the current class; the SAM picker cannot
        show the crack line, so it shows spalling while crack is current."""
        cid = self.canvas.current_class_id
        self._class_picker_brush.set_current(cid)
        self._class_picker_sam.set_current(
            cid if self.class_registry.is_area(cid) else SPALLING_ID)

    def _select_class_by_index(self, i: int) -> None:
        """Number key i+1: the i-th class in list order; nothing if absent."""
        classes = self.class_registry.classes()
        if 0 <= i < len(classes):
            self._set_current_class(classes[i].class_id)

    def _can_add_class(self) -> tuple[bool, str]:
        """Whether "+" works, and its tooltip. Adding needs the server."""
        return False, self.tr_("class_add_unavailable")

    def _on_add_class(self) -> None:
        """Adding needs the server (the Viewer window implements it)."""

    def _dispatch_derived(self, filename: str, layers: dict, scale: float) -> None:
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
            layers=layers, px_per_cm=scale,
            highlight_path=hi_path, repair15_path=r15_path,
            token=filename, signals=self._derived_signals))

    def _maybe_auto_bbox(self, token: str) -> None:
        """Auto-fit bboxes from the current 15cm contour: silently when there are
        none, and (on a mask-edit regeneration) silently re-fit all from the new
        15cm. Plain loads/switches keep the saved bboxes untouched."""
        if self.current_idx < 0 or token != self.image_files[self.current_idx]:
            return
        contours = self.canvas.repair15_contours
        if not contours:
            return
        from labeling_tool.core.bbox import bboxes_from_contours
        new_boxes = bboxes_from_contours(contours)
        if not new_boxes:
            return
        # No bboxes yet -> fit. Mask was just edited (flag set) -> refit all.
        # Otherwise (plain load) leave the existing bboxes as they are.
        if self.canvas.bbox_interaction.boxes and self._offer_refit_for != token:
            return
        self._offer_refit_for = None
        self.canvas.bbox_interaction.boxes = new_boxes
        self._mark_bbox_edited()
        self.canvas.update()

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

    def _on_brush_save(self):
        """S / Ctrl+S / the save button: what is still unconfirmed (a SAM
        selection, repair-area points) is confirmed first, then saved."""
        notice = (self._confirm_pending_edits()
                  if 0 <= self.current_idx < len(self.image_files) else None)
        ok = self._save_all_artifacts(silent=False)
        # A failed save already said why; do not cover it with "recorded".
        if notice and ok:
            self.status.showMessage(notice)

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
        if checked and not self.class_registry.is_area(self.canvas.current_class_id):
            self._set_current_class(SPALLING_ID)       # SAM selects areas only
            self._sam_took_crack = self.canvas.current_class_id == SPALLING_ID
        elif not checked:
            took, self._sam_took_crack = self._sam_took_crack, False
            if took and self.canvas.current_class_id == SPALLING_ID:
                self._set_current_class(CRACK_ID)
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
        """Undo button (btn_sam_undo): drop the last SAM point (no-op outside SAM mode)."""
        if self.canvas.sam_mode and self.canvas.undo_sam_point():
            self.status.showMessage(self.tr_("sam_undone"))

    def _on_escape(self):
        """Esc drops everything not yet confirmed: all SAM points, or the
        repair-area points / selection.

        Esc and Enter are single global shortcuts (shortcuts.py); routing them
        by mode here avoids conflicting bindings (which fire ambiguously / not
        at all)."""
        if self.canvas.sam_mode:
            self._on_sam_cancel()
        else:
            self._on_bbox_cancel()

    def _on_confirm(self):
        """Enter confirms: the SAM selection, or the repair-area points."""
        if self.canvas.sam_mode:
            self._on_sam_commit()
        else:
            self._on_bbox_commit()

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

        side_panel = build_side_panel(self)
        self.canvas.history_changed.connect(self._refresh_undo_buttons)
        self._refresh_nav_tooltips()
        self._refresh_tools()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.canvas)
        splitter.addWidget(side_panel)
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
        self._refresh_job_info()
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

        files = self._build_image_list()
        if not files:
            QMessageBox.warning(self,
                self.tr_("warn_title"),
                self.tr_("warn_no_images", dir=str(self.origin_dir)))
            return

        self.image_files = files
        self.file_list.clear()
        for name in files:
            text, secondary = self._list_item_parts(name)
            item = QListWidgetItem(text)
            if secondary:
                item.setData(SECONDARY_TEXT_ROLE, secondary)
            item.setToolTip(name)
            self.file_list.addItem(item)
        self._fit_list_columns()
        self._refresh_job_info()

        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.file_list.setCurrentRow(0)
        self._refresh_list_colors()
        self.status.showMessage(self.tr_("loaded_n_images", n=len(files)))

    def _build_image_list(self) -> list[str]:
        """Filenames to list. Default: images in origin_dir. Overridable."""
        return sorted([
            f.name for f in self.origin_dir.iterdir()
            if f.suffix.lower() in IMAGE_EXTENSIONS
        ])

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

        notice = None
        if (not force_reload) and self.current_idx >= 0 and self.current_idx != idx:
            notice = self._confirm_pending_edits()
            self._save_all_artifacts(silent=True, only_if_edited=True)

        filename = self.image_files[idx]
        origin_path = str(self.origin_dir / filename)
        import sys as _sys

        mask_path, source = self._display_mask_path(filename)

        print(f"[load] {filename} -> {source}: {mask_path}", file=_sys.stderr)

        try:
            origin, layers = load_origin_and_layers(origin_path, mask_path)
        except FileNotFoundError as e:
            self.status.showMessage(self.tr_("status_error", error=str(e)))
            return

        self.current_idx = idx
        # A pending refit offer is only meaningful for an in-place save; drop it
        # on navigation so a deferred async result can't pop the dialog on return.
        self._offer_refit_for = None
        self.canvas.set_image_layers(origin, layers)

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

        # ----- scale: resolved per image (Viewer subclass uses the server PPM;
        #       base = ArUco auto-detect), but a saved MANUAL scale always wins -----
        scale, source, aruco_corners = self._resolve_scale(filename, origin)
        # Display-only outline; None when no fresh detection on this image,
        # so we never show stale ArUco from a previous load.
        self.canvas.set_aruco_corners(aruco_corners)

        bbox_path = (self.output_dir / mask_store.bbox_name(filename)
                     if self.output_dir is not None else None)
        saved = load_scale_info(bbox_path)
        if saved["source"] == "manual" and saved["scale"]:
            # Honor the manual scale (ArUco would otherwise overwrite it) and
            # redraw its measurement line on revisit.
            scale, source = saved["scale"], "manual"
            self.scale_tracker.last_known_scale = scale
            self.canvas.set_measure_points(saved["points"])
        else:
            self.canvas.set_measure_points(None)

        self.current_scale = scale
        self.current_scale_source = source
        self.canvas.set_bbox_padding_px(scale * 15.0 if scale else 0.0)
        self._refresh_scale_label()
        self._btn_bbox_toggle.setEnabled(scale is not None)
        self._refresh_tools()

        # ----- BBox JSON -----
        if bbox_path is not None:
            self.canvas.bbox_interaction.boxes = load_bboxes(bbox_path)
        else:
            self.canvas.bbox_interaction.boxes = []

        # ----- auto-bbox from the 15cm contour (default-shown) -----
        if self.canvas.repair15_contours:
            self._maybe_auto_bbox(filename)            # fit-if-empty (no dialog on load)
        elif self.current_scale and self.current_scale > 0:
            if self.canvas.layers:
                # No Repair15 on disk yet -> generate it (and the contour) async;
                # the callback fits bboxes when ready.
                self._dispatch_derived(
                    filename, {c: m.copy() for c, m in self.canvas.layers.items()},
                    float(self.current_scale))

        # File list selection
        self.file_list.blockSignals(True)
        self.file_list.setCurrentRow(idx)
        self.file_list.blockSignals(False)

        if force_reload:
            self._edited.pop(filename, None)
            self._bbox_edited.pop(filename, None)

        self._refresh_list_colors()
        self._update_status_for_current()
        if notice:
            self.status.showMessage(notice)

    def _confirm_pending_edits(self) -> str | None:
        """Moving to another photo (or closing) confirms what was left
        unconfirmed -- a SAM selection, repair-area points -- so it is saved
        instead of silently dropped. A lone repair-area point cannot make a
        box and is dropped. Returns a status line saying what was confirmed."""
        c = self.canvas
        notices = []
        if c.has_sam_preview() and c.commit_sam():
            notices.append(self.tr_("sam_auto_committed"))
        clicks = c.bbox_interaction.in_progress_clicks
        if clicks:
            if len(clicks) >= 2 and c.bbox_padding_px <= 0:
                notices.append(self.tr_("bbox_auto_dropped"))
            elif (len(clicks) >= 2
                    and c.bbox_interaction.commit(c.bbox_padding_px)):
                self._mark_bbox_edited()
                notices.append(self.tr_("bbox_auto_committed"))
            c.bbox_interaction.in_progress_clicks = []
        return " · ".join(notices) or None

    def _display_mask_path(self, filename: str) -> tuple[str | None, str]:
        """(mask_path|None, source) to display. Default: Labeling then Detected
        via <stem>_mask.png. Overridable."""
        resolved, source = mask_store.resolve_display_mask(
            labeling_dir=self.output_dir,
            detected_dir=self.detected_dir, origin_filename=filename)
        return (str(resolved) if resolved is not None else None), source

    def _save_mask_path(self, filename: str) -> Path:
        """Output path for the edited mask. Default: <stem>_mask.png in
        output_dir. Overridable."""
        return self.output_dir / mask_store.mask_name(filename)

    def _resolve_scale(self, filename: str, origin):
        """Return (scale_px_per_cm, source, aruco_corners) for this image.

        Base implementation auto-detects via ArUco. The Viewer subclass
        overrides this to use the server-provided pxPerCm (captured data no
        longer embeds ArUco markers)."""
        return self.scale_tracker.update_for_image(origin)

    def _refresh_scale_label(self):
        # Internal canonical scale is px/cm. The label shows mm/px = 10 / (px/cm).
        # Where an automatic value came from is not shown; a hand-measured one
        # (it overrides the server's) is amber with a tooltip -- a text marker
        # did not fit the narrowest panel.
        manual = (self.current_scale_source == "manual"
                  and self.current_scale is not None and self.current_scale > 0)
        if self.current_scale is None or self.current_scale <= 0:
            txt = self.tr_("lbl_scale", scale="--")
        else:
            txt = self.tr_("lbl_scale", scale=f"{10.0 / self.current_scale:.4f}")
        self._lbl_scale.setText(txt)
        if bool(self._lbl_scale.property("manual")) != manual:
            self._lbl_scale.setProperty("manual", manual)
            self._lbl_scale.style().unpolish(self._lbl_scale)   # re-read the QSS
            self._lbl_scale.style().polish(self._lbl_scale)
        self._lbl_scale.setToolTip(self.tr_("scale_manual_tip") if manual else "")

    def _update_status_for_current(self):
        if self.current_idx < 0:
            return
        filename = self.image_files[self.current_idx]
        edited = (self.tr_("status_edited_yes") if self._edited.get(filename)
                  else self.tr_("status_edited_no"))
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
            item.setData(MARK_ROLE, self._list_item_mark(fname))
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
        if self.current_idx >= 0:
            self._confirm_pending_edits()
        self._save_all_artifacts(silent=True, only_if_edited=True,
                                 async_derived=False)
        self._disconnect_language_manager()
        super().closeEvent(event)
