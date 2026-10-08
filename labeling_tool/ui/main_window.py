"""MainWindow subclass wired to a Viewer API Workspace + Manifest.

Reuses all core labeling behavior; adds session directory injection and a
single "Upload to EC2" action that uploads edited photos.
"""

from __future__ import annotations

import uuid

from PyQt5.QtWidgets import (
    QPushButton, QMessageBox, QProgressBar, QWidget, QHBoxLayout, QLabel,
)

from labeling_tool.ui import icons
from labeling_tool.core.window.main_window import MainWindow as CoreMainWindow
from labeling_tool.core.bbox import load_scale_info
from labeling_tool.annotation_payload import upload_scale_source
from labeling_tool.session import mask_store
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.focus import PhotoFocus
from labeling_tool.session.manifest import Manifest
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.ui.upload_worker import UploadWorker


class ViewerMainWindow(CoreMainWindow):
    def __init__(self, workspace: Workspace, manifest: Manifest,
                 client: ViewerApiClient | None, focus: PhotoFocus | None = None):
        self._ws = workspace
        self._manifest = manifest
        self._client = client
        # After a range fetch: list just those photos until "show all".
        self._focus = focus
        self._show_all = focus is None
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
        # upload marks (✓ / ●) in their own column before the id
        self.file_list.itemDelegate().mark_width = 20
        self._fit_list_columns()
        self._refresh_list_colors()

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
        """"Photos 5 ~ 10 (6)  [Show all]" above the list after a range fetch."""
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
        if self._focus is not None:
            # the bar's row comes out of the list: about three rows minimum
            # keeps a 900 px window from scrolling (a range is usually short)
            self.file_list.setMinimumHeight(92)

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
        if entry is None:
            return None
        if self._edited.get(filename) or (
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

    def _on_upload(self):
        if self._client is None:
            QMessageBox.warning(self, self.tr_("vmw_offline_title"),
                                self.tr_("vmw_offline_msg"))
            return
        self._save_all_artifacts(silent=True, only_if_edited=True)
        filenames = self._edited_filenames()
        if not filenames:
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

        if not specs:
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
        worker = UploadWorker(
            self._client, session_id=self._ws.session_id, specs=specs,
            labeling_dir=str(self.output_dir),
            edit_batch_id=str(uuid.uuid4()), parent=self)
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
        self._finish_upload(result)

    def _on_upload_error(self, msg):
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
            self._manifest.save(self._ws.manifest_path)
            self._refresh_list_colors()

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
            self.status.showMessage(
                self.tr_("vmw_status_partial", count=len(synced_ts)))
            QMessageBox.warning(
                self, self.tr_("vmw_partial_title"),
                self.tr_("vmw_partial_msg_header", count=len(synced_ts))
                + "\n".join(parts)
                + report_line
                + self.tr_("vmw_partial_msg_footer", log_path=log_path))
        elif not synced_ts:
            self.status.showMessage(self.tr_("vmw_status_no_items"))
            QMessageBox.information(self, self.tr_("vmw_none_title"),
                                     self.tr_("vmw_msg_no_edits"))
        else:
            self.status.showMessage(
                self.tr_("vmw_status_done", count=result["uploaded"]))
            QMessageBox.information(
                self, self.tr_("vmw_done_title"),
                self.tr_("vmw_done_msg", count=result["uploaded"],
                         report_line=report_line))
