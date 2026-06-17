"""Data fetch screen (shown after login): pick a session from the dropdown
(populated via list_sessions), set the optional num zone, then V1 + download
+ prebuild. Mirrors the old ConnectDialog online path."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox, QComboBox, QApplication,
)

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.api.downloader import download_photos
from labeling_tool.ui.dialog_helpers import save_config, run_prebuild
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming
from labeling_tool.logging_setup import attach_session_log, vlog


class FetchDialog(QDialog):
    def __init__(self, base: str, key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("데이터 가져오기 (V1)")
        self.resize(520, 300)
        self.base = base
        self.key = key
        self.client = ViewerApiClient(base_url=base, api_key=key)
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None
        self._sessions_loaded = False

        self.cb_session = QComboBox()
        self.sp_from = QSpinBox(); self.sp_from.setRange(0, 10_000_000)
        self.sp_to = QSpinBox(); self.sp_to.setRange(0, 10_000_000)
        form = QFormLayout()
        form.addRow("sessionId", self.cb_session)
        form.addRow("fromNum (0=미사용)", self.sp_from)
        form.addRow("toNum (0=미사용)", self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        # Set True when the user chooses to go back to the login screen; the
        # app.py orchestration loop reopens LoginDialog instead of exiting.
        self.go_back = False
        self.btn_back = QPushButton("← 로그인")
        self.btn_back.clicked.connect(self._on_back)
        self.btn_fetch = QPushButton("가져오기 (V1 + 다운로드)")
        self.btn_fetch.setDefault(True)
        self.btn_fetch.clicked.connect(self._on_fetch)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_back)
        btns.addStretch(1)
        btns.addWidget(self.btn_fetch)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)

    # ---- session dropdown ----
    def showEvent(self, event):
        super().showEvent(event)
        if not self._sessions_loaded:
            self._sessions_loaded = True
            self._load_sessions()

    def _load_sessions(self):
        try:
            sessions = self.client.list_sessions()
        except Exception as e:  # endpoint pending / network error -> manual
            QMessageBox.warning(
                self, "세션 목록 실패",
                f"세션 목록을 불러오지 못했습니다. 수동 입력하세요.\n{e}")
            self.cb_session.setEditable(True)
            return
        if not sessions:
            self.cb_session.setEditable(True)
            return
        for s in sessions:
            sid = s["sessionId"]
            name = s.get("inspectionName")
            label = f"session {sid}" if not name else f"session {sid} · {name}"
            if s.get("photoCount") is not None:
                label += f"  ({s['photoCount']}장)"
            self.cb_session.addItem(label, sid)

    def _selected_sid(self) -> int | None:
        data = self.cb_session.currentData()
        if data is not None:
            return int(data)
        txt = self.cb_session.currentText().strip()
        return int(txt) if txt.isdigit() else None

    def _zone(self):
        f, t = self.sp_from.value(), self.sp_to.value()
        if f > 0 and t > 0:
            return f, t
        return None, None

    def _on_back(self):
        """Return to the login screen (app.py reopens LoginDialog)."""
        self.go_back = True
        self.reject()

    # ---- fetch ----
    def _on_fetch(self):
        sid = self._selected_sid()
        if sid is None:
            QMessageBox.warning(self, "입력 필요", "sessionId를 선택/입력하세요.")
            return
        from_num, to_num = self._zone()

        ws = Workspace.default(session_id=sid)
        ws.ensure()
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s fetch start (base=%s) ===", sid, self.base)
        manifest = Manifest(session_id=sid, base=self.base)

        try:
            photos = self._fetch_all_photos(self.client, sid, from_num, to_num)
        except ViewerApiError as e:
            QMessageBox.critical(self, "V1 실패", str(e))
            return
        if not photos:
            QMessageBox.warning(self, "비어있음", "조회된 사진이 없습니다.")
            return

        for p in photos:
            ts = int(p["timestamp"])
            manifest.add(PhotoEntry(
                filename=naming.stitched_filename(ts),
                timestamp=ts,
                photo_id=int(p.get("photoId", 0)),
                report_photo_num=int(p.get("reportPhotoNum", 0)),
                px_per_cm=float(p.get("pxPerCm") or 0.0),
                scale_source="aruco",
            ))

        self.progress.setVisible(True)
        self.progress.setRange(0, len(photos))

        def _prog(done, total):
            self.progress.setValue(done)
            self.lbl_status.setText(f"다운로드 {done}/{total}")
            QApplication.processEvents()

        failures = download_photos(
            photos, ws.origin_dir, ws.detected_dir, progress=_prog)

        run_prebuild(ws, [int(p["timestamp"]) for p in photos],
                     self.progress, self.lbl_status)

        manifest.save(ws.manifest_path)
        save_config(self.base, self.key)

        if failures:
            QMessageBox.warning(
                self, "일부 실패",
                f"{len(failures)}건 다운로드 실패. 나머지는 사용 가능합니다.")
        self.workspace = ws
        self.manifest = manifest
        self.accept()

    @staticmethod
    def _fetch_all_photos(client: ViewerApiClient, session_id: int,
                          from_num, to_num) -> list[dict]:
        if from_num is not None and to_num is not None:
            return client.list_photos(
                session_id, from_num=from_num, to_num=to_num)["photos"]
        out: list[dict] = []
        offset, limit = 0, 100
        while True:
            page = client.list_photos(session_id, offset=offset, limit=limit)
            out.extend(page["photos"])
            total = page.get("total", len(out))
            offset += limit
            if offset >= total or not page["photos"]:
                break
        return out
