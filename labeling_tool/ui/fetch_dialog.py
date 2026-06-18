"""Data fetch screen (shown after login): pick a session from the dropdown
(populated via list_sessions), set the optional num zone, then fetch + download
+ prebuild. Mirrors the old ConnectDialog online path."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox, QComboBox, QApplication,
)

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.api.downloader import download_photos
from labeling_tool.ui.dialog_helpers import save_config
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming
from labeling_tool.logging_setup import attach_session_log, vlog


def filter_photos_by_range(photos: list[dict], from_num: int,
                           to_num: int) -> list[dict]:
    """Keep photos whose reportPhotoNum is within [from_num, to_num].

    0 is an OPEN bound: from_num=0 -> from the first, to_num=0 -> to the last.
    So a single field still works (e.g. toNum=15 -> first 15 photos), and both
    0 means everything. Filtering happens client-side on the already-fetched
    photo list, which is robust regardless of how the server handles the
    fromNum/toNum query params.
    """
    if from_num <= 0 and to_num <= 0:
        return list(photos)
    out: list[dict] = []
    for p in photos:
        n = int(p.get("reportPhotoNum", 0))
        if from_num > 0 and n < from_num:
            continue
        if to_num > 0 and n > to_num:
            continue
        out.append(p)
    return out


class FetchDialog(QDialog):
    def __init__(self, base: str, key: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("데이터 가져오기")
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
        form.addRow("fromNum (0=처음부터)", self.sp_from)
        form.addRow("toNum (0=끝까지)", self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        # Set True when the user chooses to go back to the login screen; the
        # app.py orchestration loop reopens LoginDialog instead of exiting.
        self.go_back = False
        self.btn_back = QPushButton("← 로그인")
        self.btn_back.clicked.connect(self._on_back)
        self.btn_fetch = QPushButton("가져오기 (다운로드)")
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
        from_num = self.sp_from.value()
        to_num = self.sp_to.value()

        ws = Workspace.default(session_id=sid)
        ws.ensure()
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s fetch start (base=%s fromNum=%s toNum=%s) ===",
                    sid, self.base, from_num, to_num)
        manifest = Manifest(session_id=sid, base=self.base)

        try:
            all_photos = self._fetch_all_photos(self.client, sid)
        except ViewerApiError as e:
            QMessageBox.critical(self, "가져오기 실패", str(e))
            return
        photos = filter_photos_by_range(all_photos, from_num, to_num)
        vlog().info("fetch: %d photos in session, %d selected (fromNum=%s toNum=%s)",
                    len(all_photos), len(photos), from_num, to_num)
        if not photos:
            QMessageBox.warning(self, "비어있음",
                                "선택된 사진이 없습니다 (범위를 확인하세요).")
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
    def _fetch_all_photos(client: ViewerApiClient, session_id: int) -> list[dict]:
        """Fetch the full photo list (metadata, paginated). The download range
        is applied client-side by filter_photos_by_range."""
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
