"""MainWindow subclass wired to a Viewer API Workspace + Manifest.

Reuses all core labeling behavior; adds session directory injection and a
single "Upload to EC2" action that uploads edited photos.
"""

from __future__ import annotations

import uuid

from PyQt5 import sip
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QPushButton, QMessageBox, QProgressBar, QWidget, QHBoxLayout, QLabel,
)

from labeling_tool.ui import icons
from labeling_tool.core.i18n import TRANSLATIONS
from labeling_tool.core.window.ui_builder import (
    MARK_ROLE, SERVER_MISSING_ROLE, SURFACE_EDITED_ROLE, SURFACE_ROLE,
)
from labeling_tool.core.window.main_window import MainWindow as CoreMainWindow
from labeling_tool.core.bbox import load_scale_info
from labeling_tool.annotation_payload import upload_scale_source
from labeling_tool.session import mask_store
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.focus import PhotoFocus
from labeling_tool.session.manifest import Manifest
from labeling_tool.session.photo_edits import (
    apply_photo_refresh, has_pending_edit, set_surface, shown_surface,
    surface_updates,
)
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.edit_fields import normalize_surface
from labeling_tool.ui.upload_worker import UploadWorker
from labeling_tool.logging_setup import vlog

# Text keys of the list's surface column: a known surface
# by name, anything else as the short "unknown" mark.
_SURFACE_TEXT_KEYS = {"floor": "surface_floor", "wall": "surface_wall",
                      "ceiling": "surface_ceiling"}


class ViewerMainWindow(CoreMainWindow):
    def __init__(self, workspace: Workspace, manifest: Manifest,
                 client: ViewerApiClient | None, focus: PhotoFocus | None = None):
        self._ws = workspace
        self._manifest = manifest
        self._client = client
        # After a range fetch: list just those photos until "show all".
        self._focus = focus
        self._show_all = focus is None
        # Class ids added from this window (V6): a late sync result must not
        # drop them, but cached classes the server no longer lists go away.
        self._added_class_ids: set[int] = set()
        # The surface column and surface row are turned on
        # below, once the core window is built; hooks the core calls while
        # building (header, retranslate) check this first.
        self._surface_ui_on = False
        super().__init__()

        # Saving should be fast: only the editable mask + bbox JSON are needed.
        # The heavy Result/ export (full crack metric + full-res PNG, ~2s on a
        # panorama) is redundant here — metrics are computed at upload time.
        self.export_result_on_save = False

        # Point the core tool at the workspace folders.
        self.origin_dir = workspace.origin_dir.resolve()
        self.detected_dir = workspace.detected_dir.resolve()
        self._sync_output_dir()                 # derives Labeling/ etc.
        # Override derived dirs to the workspace's explicit layout.
        self.output_dir = workspace.labeling_dir.resolve()
        self.result_dir = workspace.result_dir.resolve()
        self.highlight_dir = workspace.highlight_dir.resolve()
        self.repair15_dir = workspace.repair15_dir.resolve()
        if self._focus is not None:
            # A range with none of its photos on disk, or with every local
            # photo, has nothing to narrow: open the job as usual.
            in_range = self._range_files()
            if not in_range or len(in_range) == len(self._all_local_files()):
                self._focus = None
                self._show_all = True
        self._add_range_bar()
        self._reload_data()
        self._refresh_range_bar()

        self._add_upload_button()
        self._init_sam()
        self._start_class_sync()
        # upload marks (✓ / ●) in their own column before the id
        self.file_list.itemDelegate().mark_width = 20
        self._enable_surface()
        self._fit_list_columns()
        self._refresh_list_colors()

    # ------------------------------------------------------------ surface
    def _enable_surface(self) -> None:
        """Turn on what only this window has: the list's surface column and
        the surface row in the display group. Deleting photos was taken out
        (2026-10-15): the delegate's trash column stays off (delete_width 0)."""
        self._surface_row.surfaceChosen.connect(self._on_surface_chosen)
        self._surface_row.setVisible(True)
        self._surface_ui_on = True
        self._refresh_list_header()          # surface title + column width
        self._refresh_surface_row()

    def _fit_surface_column(self) -> None:
        """Size the surface column to its widest text in any language, so
        switching the language never clips the longest surface name."""
        keys = ("surface_floor", "surface_wall", "surface_ceiling",
                "surface_unknown_short", "list_col_surface")
        texts = [table[k] for table in TRANSLATIONS.values() for k in keys
                 if k in table]
        self.file_list.itemDelegate().fit_surface_column(texts, self.file_list.font())

    def _refresh_list_header(self):
        super()._refresh_list_header()
        if not getattr(self, "_surface_ui_on", False):
            return
        number, file = self._list_header.labels()
        self._list_header.set_labels(number, file, self.tr_("list_col_surface"))
        self._fit_surface_column()
        self._fit_list_columns()

    def _surface_text(self, entry) -> str:
        key = _SURFACE_TEXT_KEYS.get(shown_surface(entry), "surface_unknown_short")
        return self.tr_(key)

    def _refresh_list_row(self, row: int) -> None:
        """A row's mark, surface text and server-missing state from its
        manifest entry. A delete mark left in an old manifest is not shown."""
        item = self.file_list.item(row)
        if item is None or not 0 <= row < len(self.image_files):
            return
        filename = self.image_files[row]
        item.setData(MARK_ROLE, self._list_item_mark(filename))
        entry = (self._manifest.photos.get(filename)
                 if self._manifest is not None else None)
        if entry is None:
            return
        item.setData(SURFACE_ROLE, self._surface_text(entry))
        item.setData(SURFACE_EDITED_ROLE, entry.surface_edit is not None)
        # a photo gone from the server sends nothing: "서버에 없음"
        missing = bool(entry.server_missing)
        item.setData(SERVER_MISSING_ROLE, missing)
        item.setToolTip(f"{filename}\n{self.tr_('server_missing_tip')}"
                        if missing else filename)

    def _refresh_list_colors(self):
        super()._refresh_list_colors()
        for row in range(len(self.image_files)):
            self._refresh_list_row(row)

    def _current_entry(self):
        if self._manifest is None or not 0 <= self.current_idx < len(self.image_files):
            return None
        return self._manifest.photos.get(self.image_files[self.current_idx])

    def _refresh_surface_row(self) -> None:
        """Show the current photo's surface and tilt; nothing to edit
        without a photo."""
        entry = self._current_entry()
        if entry is None:
            self._surface_row.set_value(None, False, None, None)
            self._surface_row.setEnabled(False)
            return
        self._surface_row.setEnabled(True)
        self._surface_row.set_value(shown_surface(entry), entry.surface_edit is not None,
                                    entry.tilt_deg, entry.tilt_source)

    def _show_image(self, idx: int, force_reload: bool = False):
        super()._show_image(idx, force_reload)
        self._refresh_surface_row()

    def _reload_data(self):
        super()._reload_data()
        self._refresh_surface_row()

    def _save_manifest(self) -> bool:
        """Write the manifest now; a write error is shown, never raised (the
        callers are Qt slots)."""
        try:
            self._manifest.save(self._ws.manifest_path)
        except OSError as exc:
            self.status.showMessage(str(exc))
            return False
        return True

    def _on_surface_chosen(self, value: str) -> None:
        """A surface button: change the current photo's surface; choosing the
        server's value takes the change back."""
        entry = self._current_entry()
        if entry is not None and set_surface(entry, value):
            self._save_manifest()
        self._refresh_surface_row()
        if entry is not None:
            self._refresh_list_row(self.current_idx)
            self.file_list.viewport().update()

    def _class_base_url(self) -> str:
        if self._client is not None:
            return self._client.base_url
        return getattr(self._manifest, "base", "") or ""

    def _start_class_sync(self) -> None:
        """Cached classes at once; the server's list when it answers."""
        from labeling_tool.core.classes import load_cached
        from labeling_tool.api.class_sync import SYNC_OFFLINE
        base = self._class_base_url()
        self._apply_class_registry(load_cached(base), SYNC_OFFLINE)
        if self._client is None:
            return
        from PyQt5.QtCore import QThreadPool
        from labeling_tool.ui.class_sync_worker import ClassSyncRunnable, ClassSyncSignals
        self._class_sync_signals = ClassSyncSignals()
        self._class_sync_signals.done.connect(self._on_class_sync_done)
        QThreadPool.globalInstance().start(
            ClassSyncRunnable(self._client, base, self._class_sync_signals))

    def _can_add_class(self) -> tuple[bool, str]:
        from labeling_tool.api.class_sync import SYNC_OK, SYNC_UNSUPPORTED
        if self._client is None:
            return False, self.tr_("class_add_unavailable")
        if self._class_sync_status == SYNC_UNSUPPORTED:
            return False, self.tr_("class_add_unsupported")
        if self._class_sync_status != SYNC_OK:
            return False, self.tr_("class_add_unavailable")
        return True, self.tr_("class_add_tip")

    def _ask_new_class(self) -> tuple[str, str] | None:
        from labeling_tool.core.classes import pick_color
        from labeling_tool.ui.add_class_dialog import AddClassDialog
        dlg = AddClassDialog(pick_color(self.class_registry), self.tr_, self)
        if dlg.exec_() != dlg.Accepted:
            return None
        return dlg.name(), dlg.color()

    def _on_add_class(self) -> None:
        import requests
        from labeling_tool.api.class_sync import add_class_and_cache
        from labeling_tool.api.errors import ViewerApiError
        ok, _tip = self._can_add_class()
        if not ok:
            return
        answer = self._ask_new_class()
        if answer is None:
            return
        name, color = answer
        # The V6 call blocks the UI briefly: show that something is happening,
        # and give the normal cursor back before any message box.
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                registry, cls = add_class_and_cache(
                    self._client, self._class_base_url(), self.class_registry,
                    name, color)
            finally:
                QApplication.restoreOverrideCursor()
        except (ViewerApiError, requests.RequestException, ValueError) as e:
            key = ("class_add_full" if getattr(e, "code", "") == "CLASS_LIMIT_EXCEEDED"
                   else "class_add_failed")
            QMessageBox.warning(self, self.tr_("class_add_title"),
                                self.tr_(key, error=str(e)))
            return
        self._added_class_ids.add(cls.class_id)
        self._apply_class_registry(registry, self._class_sync_status)
        self._set_current_class(cls.class_id)

    def _on_class_sync_done(self, registry, status: str) -> None:
        """Apply the sync result.

        ok: the server's list, plus classes added in this window since the
        sync started (the result may arrive after a local add).
        unsupported: the server has no V5, so built-in classes only.
        offline: what sync_classes returned (the cache), plus this session's
        additions.
        """
        from labeling_tool.api.class_sync import SYNC_UNSUPPORTED
        merged = registry
        if status != SYNC_UNSUPPORTED:
            for cls in self.class_registry.user_classes():
                if cls.class_id in self._added_class_ids and cls.class_id not in merged:
                    merged = merged.with_class(cls)
        self._apply_class_registry(merged, status)

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
            self._tool_picker.setToolToolTip(2, self.tr_("sam_unavailable"))
        self._refresh_tools()

    # ------------------------------------------------------------ range view
    def _add_range_bar(self):
        """"Photos 5 ~ 10 (6)  [Show all]" above the list (in the list
        column's list group) after a range fetch."""
        self._range_bar = QWidget()
        row = QHBoxLayout(self._range_bar)
        row.setContentsMargins(0, 0, 0, 2)        # compact: the list keeps its rows
        self._lbl_range = QLabel()
        self._lbl_range.setObjectName("rangeLabel")
        self._btn_range_toggle = QPushButton()
        self._btn_range_toggle.setObjectName("compactButton")
        self._btn_range_toggle.setAutoDefault(False)
        self._btn_range_toggle.clicked.connect(self._toggle_range_view)
        row.addWidget(self._lbl_range, 1)
        row.addWidget(self._btn_range_toggle)
        self._grp_list.layout().insertWidget(0, self._range_bar)
        self._range_bar.setVisible(self._focus is not None)

    def _refresh_range_bar(self):
        if self._focus is None:
            return
        f = self._focus
        end = str(f.to_num) if f.to_num else self.tr_("fetch_range_end")
        self._lbl_range.setText(self.tr_("list_range_label", a=f.from_num, b=end,
                                         n=len(self._range_files())))
        self._btn_range_toggle.setText(
            self.tr_("btn_show_range" if self._show_all else "btn_show_all"))

    def _all_local_files(self) -> list[str]:
        """Every photo of the job on this PC (the folders may not be set yet)."""
        if self.origin_dir is None or not self.origin_dir.exists():
            return []
        return super()._build_image_list()

    def _range_files(self) -> list[str]:
        on_disk = set(self._all_local_files())
        return [fn for fn in self._focus.filenames if fn in on_disk]

    def _build_image_list(self) -> list[str]:
        files = self._all_local_files()
        if self._focus is None or self._show_all:
            return files
        wanted = set(self._focus.filenames)
        return [fn for fn in files if fn in wanted]

    def _toggle_range_view(self):
        """Switch between the fetched range and every photo of the job,
        saving the current photo first and staying on it if listed."""
        notice = (self._confirm_pending_edits()
                  if 0 <= self.current_idx < len(self.image_files) else None)
        self._save_all_artifacts(silent=True, only_if_edited=True)
        current = (self.image_files[self.current_idx]
                   if 0 <= self.current_idx < len(self.image_files) else None)
        self._show_all = not self._show_all
        # Rebuild the list without letting it open photo 1 on the way.
        self.file_list.blockSignals(True)
        try:
            self._reload_data()
        finally:
            self.file_list.blockSignals(False)
        if self.image_files:
            target = (self.image_files.index(current)
                      if current in self.image_files else 0)
            self.current_idx = -1                 # force a real load
            self._show_image(target)
        self._refresh_range_bar()
        self._refresh_job_info()
        if notice:
            self.status.showMessage(notice)

    def _photo_count_text(self) -> str:
        if self._focus is None or self._show_all:
            return super()._photo_count_text()
        return self.tr_("photo_count_part", shown=len(self.image_files),
                        total=len(self._all_local_files()))

    # ------------------------------------------------------------ job info
    def _job_info(self) -> tuple[str, str]:
        return (str(self._ws.session_id),
                (self._manifest.inspection_name if self._manifest else None) or "—")

    def _list_item_mark(self, filename: str) -> str | None:
        """✓ uploaded and unchanged since; ● changed and not (re)uploaded."""
        entry = (self._manifest.photos.get(filename)
                 if self._manifest is not None else None)
        if entry is None or entry.server_missing:
            return None          # gone from the server: nothing will be sent
        if self._edited.get(filename) or has_pending_edit(entry) or (
                not entry.synced and self._has_labeling_file(filename)):
            return "pending"
        return "uploaded" if entry.synced else None

    def _begin_upload_tracking(self) -> None:
        """From now until the upload finishes, remember photos saved again:
        the upload carries their older version."""
        self._saved_during_upload: set[str] | None = set()

    def _on_photo_saved(self, filename: str) -> None:
        """A re-edited photo needs uploading again: drop its synced flag (it
        used to stay set, so the photo looked uploaded)."""
        during = getattr(self, "_saved_during_upload", None)
        if during is not None:
            during.add(filename)
        entry = (self._manifest.photos.get(filename)
                 if self._manifest is not None else None)
        if entry is not None and entry.synced:
            entry.synced = False
            try:
                self._manifest.save(self._ws.manifest_path)
            except OSError as exc:                       # never raise in a slot
                self.status.showMessage(str(exc))

    def _list_item_parts(self, filename: str) -> tuple[str, str]:
        """"<job id>-<photo number>" then the file name; a file the manifest
        does not know (should not happen) is listed by name alone."""
        entry = (self._manifest.photos.get(filename)
                 if self._manifest is not None else None)
        if entry is None:
            return filename, ""
        return f"{self._ws.session_id}-{entry.report_photo_num}", filename

    # ------------------------------------------------------------ i18n
    def retranslate(self) -> None:
        """Re-apply this subclass's own translated text (the core window's
        _retranslate_ui handles everything it owns; this covers the upload
        button and the range bar added on top of it)."""
        self.btn_upload.setText(self.tr_("vmw_btn_upload"))
        if hasattr(self, "_range_bar"):
            self._refresh_range_bar()
        if getattr(self, "_surface_ui_on", False):
            self._surface_row.retranslate(self.tr_)
            for row in range(len(self.image_files)):
                self._refresh_list_row(row)
            self.file_list.viewport().update()

    def _retranslate_ui(self):
        # CoreMainWindow already owns the languageChanged connection and
        # disconnects it on close (see closeEvent in core/window/main_window.py);
        # extend its single retranslate hook instead of adding a second listener.
        super()._retranslate_ui()
        self.retranslate()

    # ------------------------------------------------------------------
    def _add_upload_button(self):
        self.btn_upload = QPushButton(self.tr_("vmw_btn_upload"))
        self.btn_upload.setObjectName("primaryAction")
        self.btn_upload.setIcon(icons.icon("cloud-upload", primary=True))
        self.btn_upload.clicked.connect(self._on_upload)
        # Inline progress bar, shown right under the button during upload so the
        # progress is always visible in a fixed place (no easy-to-miss popup).
        self._upload_bar = QProgressBar()
        self._upload_bar.setObjectName("uploadProgress")
        self._upload_bar.setTextVisible(True)
        self._upload_bar.setVisible(False)
        # Pinned under the scrolling panel (build_side_panel), so upload is
        # always in reach whatever the panel's scroll position.
        layout = self._panel_bottom_layout
        layout.addWidget(self.btn_upload)
        layout.addWidget(self._upload_bar)

    def _resolve_scale(self, filename: str, origin):
        """Use the server-provided pxPerCm fetched into the manifest (captured
        data no longer embeds ArUco markers). Falls back to ArUco only if the
        server gave no scale for this photo."""
        entry = (self._manifest.photos.get(filename)
                 if self._manifest is not None else None)
        px = float(entry.px_per_cm) if entry and entry.px_per_cm else 0.0
        if px > 0:
            return px, "server", None        # server PPM; no ArUco overlay/detection
        return super()._resolve_scale(filename, origin)

    def _edited_filenames(self) -> list[str]:
        """Photos with a saved edited mask in Labeling/ -- of those listed
        (a range view uploads only its photos; "show all" uploads all)."""
        listed = set(self.image_files)
        out = []
        for fn in self._manifest.filenames_in_order():
            if fn in listed and (self.output_dir / mask_store.mask_name(fn)).exists():
                out.append(fn)
        return out

    # ------------------------------------------------------------ closing
    def closeEvent(self, event):
        """Closing with photos still ● asks first: upload and close / close /
        cancel. An upload still running keeps the window open: its thread
        belongs to the window and the result has to be recorded."""
        if getattr(self, "_upload_worker", None) is not None:
            event.ignore()
            self._tell_upload_running()
            return
        # Save the photo on screen before asking: a repair-area change counts
        # only once saved (that re-opens an uploaded photo), and nothing
        # waits unsaved behind the question. Unconfirmed SAM / repair-area
        # points are left alone, so cancel changes nothing; closing (the
        # base class) or uploading confirms them.
        self._save_all_artifacts(silent=True, only_if_edited=True,
                                 async_derived=False)
        count = self._pending_upload_count()
        choice = self._ask_close_unuploaded(count) if count else "close"
        if choice == "upload":
            event.ignore()
            self._close_after_upload = True
            self._on_upload()               # confirms what is on screen first
            if getattr(self, "_upload_worker", None) is None:
                self._close_after_upload = False   # it did not start: stay open
            return
        if choice != "close":
            event.ignore()
            return
        super().closeEvent(event)

    def _pending_upload_count(self) -> int:
        """Listed photos marked ● -- what an upload from here would send (a
        range view counts only its photos, as it uploads only those) -- plus
        the photo on screen when unconfirmed edits would make it ●."""
        count = sum(1 for fn in self.image_files
                    if self._list_item_mark(fn) == "pending")
        if 0 <= self.current_idx < len(self.image_files) and self._has_unconfirmed_edits():
            fn = self.image_files[self.current_idx]
            entry = self._manifest.photos.get(fn)
            if (entry is not None and not entry.server_missing
                    and self._list_item_mark(fn) != "pending"):
                count += 1
        return count

    def _ask_close_unuploaded(self, count: int) -> str:
        """"upload", "close" or "cancel" (also Esc / the title-bar close)."""
        box = QMessageBox(QMessageBox.Question, self.tr_("close_unuploaded_title"),
                          self.tr_("close_unuploaded_msg", n=count), parent=self)
        upload = box.addButton(self.tr_("close_unuploaded_btn_upload"),
                               QMessageBox.AcceptRole)
        close = box.addButton(self.tr_("close_unuploaded_btn_close"),
                              QMessageBox.DestructiveRole)
        cancel = box.addButton(self.tr_("close_unuploaded_btn_cancel"),
                               QMessageBox.RejectRole)
        box.setDefaultButton(upload)
        box.setEscapeButton(cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is upload:
            return "upload"
        return "close" if clicked is close else "cancel"

    def _tell_upload_running(self) -> None:
        """Not modal: a modal box would run a nested event loop inside the
        refused close, and an upload finishing in it could not close the
        window ("upload and close"). One box at a time; it goes when the
        upload ends."""
        self._close_busy_notice()
        box = QMessageBox(QMessageBox.Information,
                          self.tr_("close_upload_running_title"),
                          self.tr_("close_upload_running_msg"), parent=self)
        box.setAttribute(Qt.WA_DeleteOnClose)
        self._busy_notice = box
        box.open()

    def _close_busy_notice(self) -> None:
        box = getattr(self, "_busy_notice", None)
        self._busy_notice = None
        if box is not None and not sip.isdeleted(box):
            box.close()

    def _on_upload(self):
        if self._client is None:
            QMessageBox.warning(self, self.tr_("vmw_offline_title"),
                                self.tr_("vmw_offline_msg"))
            return
        if 0 <= self.current_idx < len(self.image_files):
            notice = self._confirm_pending_edits()   # upload what is on screen
            if notice:
                self.status.showMessage(notice)
        self._save_all_artifacts(silent=True, only_if_edited=True)
        # Surface changes of the listed photos ride along (a range view
        # sends only its photos'); a photo the server no longer has sends
        # nothing. Deletes are never sent: deleting photos was taken out of
        # the tool, and a delete mark left in an old manifest is ignored.
        listed = set(self.image_files)
        edit_entries = [self._manifest.get(fn)
                        for fn in self._manifest.filenames_in_order() if fn in listed]
        surface = surface_updates(edit_entries)
        filenames = [fn for fn in self._edited_filenames()
                     if not self._manifest.get(fn).server_missing]
        if not (filenames or surface):
            self.status.showMessage(self.tr_("vmw_status_no_edits"))
            QMessageBox.information(self, self.tr_("vmw_none_title"),
                                     self.tr_("vmw_msg_no_edits"))
            return

        # Build only lightweight specs on the UI thread (instant). The heavy
        # work — decoding each mask, computing crack metrics, and the network
        # upload — all runs in UploadWorker so the UI never freezes.
        specs = []
        for fn in filenames:
            entry = self._manifest.get(fn)
            info = load_scale_info(self.output_dir / mask_store.bbox_name(fn))
            px_per_cm = info["scale"] if info["scale"] else (entry.px_per_cm or 0.0)
            if px_per_cm <= 0:
                continue                  # upload requires pxPerCm
            # Default scale is the server metrics PPM; manual measurement wins.
            specs.append({"filename": fn, "timestamp": entry.timestamp,
                          "px_per_cm": px_per_cm,
                          "scale_source": upload_scale_source(info["source"])})

        if not specs and not surface:
            self.status.showMessage(self.tr_("vmw_status_no_scale"))
            QMessageBox.warning(self, self.tr_("vmw_no_scale_title"),
                                self.tr_("vmw_msg_no_scale"))
            return

        total = len(specs)
        self._upload_bar.setRange(0, total)
        self._upload_bar.setValue(0)
        self._upload_bar.setFormat(
            self.tr_("vmw_progress_format", phase=self.tr_("vmw_phase_prepare")))
        self._upload_bar.setVisible(True)
        self.btn_upload.setEnabled(False)
        self.status.showMessage(self.tr_("vmw_status_upload_starting", total=total))

        self._begin_upload_tracking()
        # What each surface change sent: one changed again while uploading
        # must stay pending afterwards (see _apply_sent_surfaces).
        self._upload_surface_snapshot = {
            int(u["timestamp"]): u["surface"] for u in surface}
        worker = UploadWorker(
            self._client, session_id=self._ws.session_id, specs=specs,
            labeling_dir=str(self.output_dir),
            edit_batch_id=str(uuid.uuid4()),
            class_registry=self.class_registry,
            surface_updates=surface, deletes=(), parent=self)
        self._upload_worker = worker      # keep a reference (avoid GC)
        worker.progress.connect(self._on_upload_progress)
        worker.done.connect(self._on_upload_done)
        worker.error.connect(self._on_upload_error)
        worker.start()

    def _on_upload_progress(self, done, total, phase):
        label = (self.tr_("vmw_phase_prepare") if phase == "prepare"
                 else self.tr_("vmw_phase_upload"))
        self._upload_bar.setMaximum(total)
        self._upload_bar.setValue(done)
        self._upload_bar.setFormat(self.tr_("vmw_progress_format", phase=label))
        self.status.showMessage(
            self.tr_("vmw_status_progress", phase=label, done=done, total=total))

    def _on_upload_done(self, result):
        self._upload_bar.setVisible(False)
        self.btn_upload.setEnabled(True)
        self._upload_worker = None
        self._close_busy_notice()
        close_after = getattr(self, "_close_after_upload", False)
        self._close_after_upload = False      # cleared even if the next line raises
        self._finish_upload(result)
        if close_after:
            # "upload and close": try again once the result was shown (and
            # outside this slot); photos the server did not take are still ●
            # and are asked about anew
            QTimer.singleShot(0, self.close)

    def _on_upload_error(self, msg):
        self._close_after_upload = False      # a failed upload never closes
        self._close_busy_notice()
        self._saved_during_upload = None
        self._upload_bar.setVisible(False)
        self.btn_upload.setEnabled(True)
        self._upload_worker = None
        self.status.showMessage(self.tr_("vmw_upload_failed"))
        QMessageBox.critical(self, self.tr_("vmw_upload_failed"), msg)

    def _finish_upload(self, result):
        # timestamps now carries only SERVER-CONFIRMED photos (uploader excludes
        # batches whose updatedPhotoCount < sent), so we never mark unpersisted
        # photos as synced.
        synced_ts = set(result.get("timestamps") or [])
        anomalies = result.get("anomalies") or []
        # saved again while uploading: the server has the older version
        resaved = getattr(self, "_saved_during_upload", None) or set()
        self._saved_during_upload = None
        if synced_ts:
            files = [fn for fn in self._manifest.filenames_in_order()
                     if self._manifest.get(fn).timestamp in synced_ts
                     and fn not in resaved]
            self._manifest.mark_synced(files, batch_id=result.get("batch_id", ""))
            self._save_manifest()
            self._refresh_list_colors()

        n_surface = self._apply_upload_edits(result)
        n_skipped = self._mark_server_missing(result.get("skipped_timestamps") or ())
        summary = " · ".join(
            ([self.tr_("upload_surface_summary", n=n_surface)] if n_surface else [])
            + ([self.tr_("upload_skipped_summary", n=n_skipped)] if n_skipped else []))
        if n_surface:
            self._start_photo_refresh()

        verify_failures = result.get("verify_failures") or []
        report = result.get("verify_report")
        log_path = self._ws.session_dir / "vapi.log"
        report_line = (self.tr_("vmw_report_line", report=report)
                        if report else "")
        if result["failed"] or anomalies or verify_failures:
            parts = []
            if result["failed"]:
                first_err = (str(result["failed"][0].get("error", ""))
                             or self.tr_("vmw_err_unrecorded"))
                parts.append(self.tr_(
                    "vmw_part_failed_batches",
                    count=len(result["failed"]), err=first_err))
            if verify_failures:
                # read-back is authoritative: name the photos missing on the server
                nums = ", ".join(str(v.get("reportPhotoNum") or v["timestamp"])
                                 for v in verify_failures[:12])
                more = " …" if len(verify_failures) > 12 else ""
                parts.append(self.tr_(
                    "vmw_part_verify_failures",
                    count=len(verify_failures), nums=nums, more=more))
            elif anomalies:
                missing = sum(a["sent"] - a["updated"] for a in anomalies)
                parts.append(self.tr_("vmw_part_anomalies", missing=missing))
            self.status.showMessage(_joined(
                self.tr_("vmw_status_partial", count=len(synced_ts)), summary))
            QMessageBox.warning(
                self, self.tr_("vmw_partial_title"),
                self.tr_("vmw_partial_msg_header", count=len(synced_ts))
                + "\n".join(parts)
                + report_line
                + self.tr_("vmw_partial_msg_footer", log_path=log_path))
        elif not (synced_ts or summary):
            self.status.showMessage(self.tr_("vmw_status_no_items"))
            QMessageBox.information(self, self.tr_("vmw_none_title"),
                                     self.tr_("vmw_msg_no_edits"))
        elif summary and not result["uploaded"]:
            # only surface changes went up: "0 photos" would mislead
            done = self.tr_("vmw_status_done_edits", summary=summary)
            self.status.showMessage(done)
            QMessageBox.information(self, self.tr_("vmw_done_title"),
                                     done + report_line)
        else:
            self.status.showMessage(_joined(
                self.tr_("vmw_status_done", count=result["uploaded"]), summary))
            QMessageBox.information(
                self, self.tr_("vmw_done_title"),
                self.tr_("vmw_done_msg", count=result["uploaded"],
                         report_line=report_line)
                + (f"\n{summary}" if summary else ""))
        unknown = result.get("unknown_classes") or []
        if unknown:
            self.status.showMessage(self.tr_(
                "class_unknown_on_upload", ids=", ".join(f"#{i}" for i in unknown)))

    # ------------------------------------------------------------ after an upload
    def _apply_upload_edits(self, result) -> int:
        """Take the sent surfaces the server confirmed. Returns how many
        were applied. Deletes are never sent, so a result's
        deleted_timestamps (none expected) change nothing here."""
        snapshot = getattr(self, "_upload_surface_snapshot", None) or {}
        self._upload_surface_snapshot = None
        by_ts = {int(e.timestamp): fn for fn, e in self._manifest.photos.items()}
        n_surface = self._apply_sent_surfaces(
            [int(t) for t in result.get("surface_timestamps") or []],
            by_ts, snapshot)
        if n_surface:
            self._save_manifest()
            self._refresh_list_colors()
            self.file_list.viewport().update()
            self._refresh_surface_row()
        return n_surface

    def _mark_server_missing(self, timestamps) -> int:
        """Photos the server skipped are gone there (deleted by someone
        else): flag them so later uploads leave them out. Their local files
        stay. Returns how many photos were skipped."""
        timestamps = [int(t) for t in timestamps]
        if timestamps and self._manifest.mark_server_missing(timestamps):
            self._save_manifest()
            self._refresh_list_colors()
            self.file_list.viewport().update()
        return len(timestamps)

    def _apply_sent_surfaces(self, timestamps, by_ts, snapshot) -> int:
        """A surface change the server took becomes the photo's surface. A
        change made while the upload ran is newer than what was sent, so it
        stays pending (including one taken back to the old value)."""
        count = 0
        for ts in timestamps:
            fn = by_ts.get(ts)
            if fn is None:
                continue
            entry = self._manifest.get(fn)
            sent = snapshot.get(ts, entry.surface_edit)
            if normalize_surface(sent) is None:
                continue
            before = normalize_surface(entry.surface)
            entry.surface = sent
            entry.tilt_source = "manual"
            if entry.surface_edit == sent:
                entry.surface_edit = None
            elif entry.surface_edit is None and before not in (None, sent):
                entry.surface_edit = before      # taken back: still to be sent
            count += 1
        return count

    def _start_photo_refresh(self) -> None:
        """Fetch the job's photo list again in the background: the server
        may adjust surfaces and photo numbers."""
        if self._client is None:
            return
        from PyQt5.QtCore import QThreadPool
        from labeling_tool.ui.photo_refresh_worker import (
            PhotoRefreshRunnable, PhotoRefreshSignals)
        # Each refresh gets a generation: only the newest one's result is
        # applied (an older one may arrive later with older numbers). One
        # signals object for the window's life, slot = a bound method (as
        # with the class sync), so a closed window is never called back.
        self._photo_refresh_gen = getattr(self, "_photo_refresh_gen", 0) + 1
        if getattr(self, "_photo_refresh_signals", None) is None:
            self._photo_refresh_signals = PhotoRefreshSignals()
            self._photo_refresh_signals.finished.connect(self._on_photo_refresh_finished)
        QThreadPool.globalInstance().start(PhotoRefreshRunnable(
            self._client, self._ws.session_id, self._photo_refresh_signals,
            self._photo_refresh_gen))

    def _on_photo_refresh_finished(self, generation: int, photos) -> None:
        self._on_photo_refresh_done(photos, generation)

    def _on_photo_refresh_done(self, photos, generation: int | None = None) -> None:
        """New numbers and surfaces for the photos still here; the list
        order and the current photo stay as they are. A result from an
        older refresh than the latest started is dropped."""
        if generation is not None and generation != getattr(
                self, "_photo_refresh_gen", 0):
            return
        if photos is None:
            self.status.showMessage(self.tr_("photo_refresh_failed"))
            return
        if not apply_photo_refresh(self._manifest, photos):
            return
        self._save_manifest()
        for row, fn in enumerate(self.image_files):
            item = self.file_list.item(row)
            if item is not None:
                item.setText(self._list_item_parts(fn)[0])
        self._fit_list_columns()
        self._refresh_list_colors()
        self._refresh_surface_row()
        self.file_list.viewport().update()


def _joined(text: str, summary: str) -> str:
    """A status line with the surface / skipped summary after it."""
    return f"{text} · {summary}" if summary else text
