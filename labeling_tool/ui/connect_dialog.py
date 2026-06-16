"""Startup connection wizard: collect creds, call V1, download, build manifest.

Returns a populated Workspace + Manifest on success. The caller (app.py)
then opens the main labeling window against that workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox,
)

from labeling_tool.api.client import ViewerApiClient
from labeling_tool.api.errors import ViewerApiError
from labeling_tool.api.downloader import download_photos
from labeling_tool.rebuild_cache import prebuild_rebuilt
from labeling_tool.session.workspace import Workspace
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session import naming
from labeling_tool.logging_setup import attach_session_log, vlog

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(base: str, api_key: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"base": base, "apiKey": api_key}, indent=2),
        encoding="utf-8")


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("연결 / 데이터 가져오기 (V1)")
        self.resize(520, 320)
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None

        cfg = _load_config()
        form = QFormLayout()
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.sp_session = QSpinBox(); self.sp_session.setRange(1, 10_000_000)
        self.sp_from = QSpinBox(); self.sp_from.setRange(0, 10_000_000)
        self.sp_to = QSpinBox(); self.sp_to.setRange(0, 10_000_000)
        form.addRow("BASE URL", self.ed_base)
        form.addRow("X-Viewer-Api-Key", self.ed_key)
        form.addRow("sessionId", self.sp_session)
        form.addRow("fromNum (0=미사용)", self.sp_from)
        form.addRow("toNum (0=미사용)", self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_fetch = QPushButton("가져오기 (V1 + 다운로드)")
        self.btn_open_local = QPushButton("이미 받은 세션 열기")
        self.btn_fetch.clicked.connect(self._on_fetch)
        self.btn_open_local.clicked.connect(self._on_open_local)
        btns = QHBoxLayout()
        btns.addWidget(self.btn_open_local)
        btns.addStretch(1)
        btns.addWidget(self.btn_fetch)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)

    def _zone(self) -> tuple[int | None, int | None]:
        f, t = self.sp_from.value(), self.sp_to.value()
        if f > 0 and t > 0:
            return f, t
        return None, None

    def _on_open_local(self):
        sid = self.sp_session.value()
        ws = Workspace.default(session_id=sid)
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, "없음",
                                f"로컬 매니페스트 없음: {ws.manifest_path}")
            return
        self.workspace = ws
        self.manifest = Manifest.load(ws.manifest_path)
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local) ===", sid)
        # Build any missing Rebuilt/ entries (idempotent — instant if cached).
        self._run_prebuild(ws, [
            self.manifest.get(fn).timestamp
            for fn in self.manifest.filenames_in_order()])
        self.accept()

    def _run_prebuild(self, ws, timestamps):
        """Pre-compute the Rebuilt/ cache for every photo with a visible
        progress bar, so the labeling window opens instantly instead of
        freezing while it rebuilds the first image on the UI thread."""
        if not timestamps:
            return
        from PyQt5.QtWidgets import QApplication
        self.progress.setVisible(True)
        self.progress.setRange(0, len(timestamps))
        self.progress.setValue(0)

        def _prog(done, total):
            self.progress.setValue(done)
            self.lbl_status.setText(f"재구성(rebuild) {done}/{total}")
            QApplication.processEvents()

        prebuild_rebuilt(ws.origin_dir, ws.detected_dir, ws.rebuilt_dir,
                         timestamps, progress=_prog)

    def _on_fetch(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        sid = self.sp_session.value()
        if not base or not key:
            QMessageBox.warning(self, "입력 필요", "BASE/Key를 입력하세요.")
            return
        from_num, to_num = self._zone()
        client = ViewerApiClient(base_url=base, api_key=key)

        ws = Workspace.default(session_id=sid)
        ws.ensure()
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s fetch start (base=%s) ===", sid, base)
        manifest = Manifest(session_id=sid, base=base)

        # ---- V1 with pagination ----
        try:
            photos = self._fetch_all_photos(client, sid, from_num, to_num)
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

        # ---- download ----
        self.progress.setVisible(True)
        self.progress.setRange(0, len(photos))
        from PyQt5.QtWidgets import QApplication

        def _prog(done, total):
            self.progress.setValue(done)
            self.lbl_status.setText(f"다운로드 {done}/{total}")
            QApplication.processEvents()

        failures = download_photos(
            photos, ws.origin_dir, ws.detected_dir, progress=_prog)

        # ---- prebuild Rebuilt/ so the labeling window opens instantly ----
        self._run_prebuild(ws, [int(p["timestamp"]) for p in photos])

        manifest.save(ws.manifest_path)
        _save_config(base, key)

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
