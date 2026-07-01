"""MainWindow subclass wired to a Viewer API Workspace + Manifest.

Reuses all core labeling behavior; adds session directory injection and a
single "Upload to EC2" action that uploads edited photos.
"""

from __future__ import annotations

import uuid

from PyQt5.QtWidgets import (
    QPushButton, QMessageBox, QProgressBar,
)

from labeling_tool.core.window.main_window import MainWindow as CoreMainWindow
from labeling_tool.core.bbox import load_scale_info
from labeling_tool.annotation_payload import upload_scale_source
from labeling_tool.session import mask_store
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest
from labeling_tool.api.client import ViewerApiClient
from labeling_tool.ui.upload_worker import UploadWorker


class ViewerMainWindow(CoreMainWindow):
    def __init__(self, workspace: Workspace, manifest: Manifest,
                 client: ViewerApiClient | None):
        self._ws = workspace
        self._manifest = manifest
        self._client = client
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
        self._refresh_path_labels()
        self._reload_data()

        self._add_upload_button()
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

    # ------------------------------------------------------------------
    def _add_upload_button(self):
        self.btn_upload = QPushButton("EC2에 업로드")
        self.btn_upload.setObjectName("primaryAction")
        self.btn_upload.clicked.connect(self._on_upload)
        # Inline progress bar, shown right under the button during upload so the
        # progress is always visible in a fixed place (no easy-to-miss popup).
        self._upload_bar = QProgressBar()
        self._upload_bar.setObjectName("uploadProgress")
        self._upload_bar.setTextVisible(True)
        self._upload_bar.setVisible(False)
        # _panel_layout is the side panel's QVBoxLayout (exposed by the
        # ui_builder patch). Insert above the consolidated help group so the
        # button + bar sit at the bottom of the content, not floating.
        layout = getattr(self, "_panel_layout", None)
        if layout is not None:
            grp_hint = getattr(self, "_grp_hint", None)
            idx = layout.indexOf(grp_hint) if grp_hint is not None else -1
            if idx < 0:
                idx = layout.count() - 1
            layout.insertWidget(idx, self.btn_upload)
            layout.insertWidget(idx + 1, self._upload_bar)

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
        """Photos with a saved edited mask in Labeling/ this session."""
        out = []
        for fn in self._manifest.filenames_in_order():
            if (self.output_dir / mask_store.mask_name(fn)).exists():
                out.append(fn)
        return out

    def _on_upload(self):
        if self._client is None:
            QMessageBox.warning(self, "오프라인",
                                "API 클라이언트가 없어 업로드할 수 없습니다.")
            return
        self._save_all_artifacts(silent=True, only_if_edited=True)
        filenames = self._edited_filenames()
        if not filenames:
            self.status.showMessage("업로드할 편집본이 없습니다 (저장된 마스크 없음)")
            QMessageBox.information(self, "없음", "업로드할 편집본이 없습니다.")
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
            self.status.showMessage(
                "pxPerCm가 있는 편집본이 없습니다 — ArUco 자동검출 또는 수동 측정 필요")
            QMessageBox.warning(self, "스케일 없음",
                                "pxPerCm가 있는 편집본이 없습니다 (ArUco 필요).")
            return

        total = len(specs)
        self._upload_bar.setRange(0, total)
        self._upload_bar.setValue(0)
        self._upload_bar.setFormat("준비 %v/%m")
        self._upload_bar.setVisible(True)
        self.btn_upload.setEnabled(False)
        self.status.showMessage(f"EC2 업로드 준비… (0/{total})")

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
        label = "준비" if phase == "prepare" else "업로드"
        self._upload_bar.setMaximum(total)
        self._upload_bar.setValue(done)
        self._upload_bar.setFormat(f"{label} %v/%m")
        self.status.showMessage(f"EC2 {label} 중… ({done}/{total})")

    def _on_upload_done(self, result):
        self._upload_bar.setVisible(False)
        self.btn_upload.setEnabled(True)
        self._upload_worker = None
        self._finish_upload(result)

    def _on_upload_error(self, msg):
        self._upload_bar.setVisible(False)
        self.btn_upload.setEnabled(True)
        self._upload_worker = None
        self.status.showMessage("업로드 실패")
        QMessageBox.critical(self, "업로드 실패", msg)

    def _finish_upload(self, result):
        # timestamps now carries only SERVER-CONFIRMED photos (uploader excludes
        # batches whose updatedPhotoCount < sent), so we never mark unpersisted
        # photos as synced.
        synced_ts = set(result.get("timestamps") or [])
        anomalies = result.get("anomalies") or []
        if synced_ts:
            files = [fn for fn in self._manifest.filenames_in_order()
                     if self._manifest.get(fn).timestamp in synced_ts]
            self._manifest.mark_synced(files, batch_id=result.get("batch_id", ""))
            self._manifest.save(self._ws.manifest_path)

        verify_failures = result.get("verify_failures") or []
        report = result.get("verify_report")
        log_path = self._ws.session_dir / "vapi.log"
        report_line = f"\n검증 보고서(CSV): {report}" if report else ""
        if result["failed"] or anomalies or verify_failures:
            parts = []
            if result["failed"]:
                first_err = (str(result["failed"][0].get("error", ""))
                             or "(원인 미기록)")
                parts.append(f"{len(result['failed'])}개 배치 업로드 실패 — 원인: {first_err}")
            if verify_failures:
                # read-back is authoritative: name the photos missing on the server
                nums = ", ".join(str(v.get("reportPhotoNum") or v["timestamp"])
                                 for v in verify_failures[:12])
                more = " …" if len(verify_failures) > 12 else ""
                parts.append(
                    f"서버 확인 결과 {len(verify_failures)}장 미반영 "
                    f"(번호/타임스탬프: {nums}{more})")
            elif anomalies:
                missing = sum(a["sent"] - a["updated"] for a in anomalies)
                parts.append(
                    f"서버가 일부만 저장 (요청보다 {missing}장 미반영)")
            self.status.showMessage(
                f"서버 확인 {len(synced_ts)}장 정상, 일부 미반영 — 다시 시도하세요")
            QMessageBox.warning(
                self, "일부 실패 / 미반영",
                f"서버에 확인된 사진: {len(synced_ts)}장\n\n"
                + "\n".join(parts)
                + f"{report_line}\n자세한 로그: {log_path}\n\n다시 업로드하세요.")
        elif not synced_ts:
            self.status.showMessage("업로드할 항목이 없습니다")
            QMessageBox.information(self, "없음", "업로드할 편집본이 없습니다.")
        else:
            self.status.showMessage(
                f"업로드 완료: {result['uploaded']}건 (서버 확인 OK)")
            QMessageBox.information(
                self, "완료",
                f"{result['uploaded']}건 업로드 + 서버 확인 완료.{report_line}")
