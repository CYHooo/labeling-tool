"""Data fetch screen (shown after login): pick a session from the dropdown
(populated via list_sessions), set the optional num zone, then fetch + download
+ prebuild. Mirrors the old ConnectDialog online path."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QSpinBox, QComboBox, QApplication,
)

from labeling_tool.core.i18n import tr
from labeling_tool.ui import icons
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
        self.setWindowTitle(tr("fetch_title"))
        self.resize(520, 300)
        self.base = base
        self.key = key
        self.client = ViewerApiClient(base_url=base, api_key=key)
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None
        self._sessions_loaded = False
        # sessionId -> inspectionName from the server list, saved into the
        # manifest so the local job list can show it later
        self._session_names: dict[int, str] = {}

        self.cb_session = QComboBox()
        self.sp_from = QSpinBox(); self.sp_from.setRange(0, 10_000_000)
        self.sp_to = QSpinBox(); self.sp_to.setRange(0, 10_000_000)
        form = QFormLayout()
        form.addRow("sessionId", self.cb_session)
        form.addRow(tr("fetch_from_label"), self.sp_from)
        form.addRow(tr("fetch_to_label"), self.sp_to)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        # Set True when the user chooses to go back to the login screen; the
        # app.py orchestration loop reopens LoginDialog instead of exiting.
        self.go_back = False
        self.btn_back = QPushButton(tr("fetch_back"))
        self.btn_back.setIcon(icons.icon("arrow-left"))
        self.btn_back.clicked.connect(self._on_back)
        self.btn_fetch = QPushButton(tr("fetch_btn"))
        self.btn_fetch.setObjectName("primaryAction")
        self.btn_fetch.setIcon(icons.icon("download", primary=True))
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
                self, tr("fetch_sessions_failed_title"),
                tr("fetch_sessions_failed_msg", error=e))
            self.cb_session.setEditable(True)
            return
        if not sessions:
            self.cb_session.setEditable(True)
            return
        for s in sessions:
            sid = s["sessionId"]
            name = s.get("inspectionName")
            if name:
                self._session_names[int(sid)] = name
            label = (tr("fetch_session_item", sid=sid) if not name
                     else tr("fetch_session_item_named", sid=sid, name=name))
            if s.get("photoCount") is not None:
                label += "  " + tr("fetch_photo_count", count=s["photoCount"])
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
            QMessageBox.warning(self, tr("fetch_input_required_title"),
                                tr("fetch_input_required_msg"))
            return
        from_num = self.sp_from.value()
        to_num = self.sp_to.value()

        ws = Workspace.default(session_id=sid)
        previous = None
        if ws.manifest_path.exists():
            # Already on this PC. The folder is named by job number only, and
            # numbers are per server: a job fetched from another server is a
            # different job in the same folder -- opening or refetching it
            # here would send its labels to this server's job. Refuse.
            load_error = None
            try:
                previous = Manifest.load(ws.manifest_path)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                load_error = exc
                vlog().warning("session %s: unreadable manifest (%s)", sid, exc)
            if previous is not None and previous.base and \
                    previous.base.rstrip("/") != self.base.rstrip("/"):
                vlog().warning("session %s on this PC is from %s, not %s: refused",
                               sid, previous.base, self.base)
                QMessageBox.warning(self, tr("fetch_other_server_title"),
                                    tr("fetch_other_server_msg", sid=sid, base=previous.base))
                return
            # Fetching would replace its manifest, so ask.
            choice = self._ask_existing(sid)
            if choice is None:
                return
            if choice == "open" and previous is None:
                QMessageBox.warning(self, tr("login_warn_manifest_error_title"),
                                    tr("login_warn_manifest_error_msg",
                                       path=ws.manifest_path, exc=load_error))
                return
            if choice == "open":
                attach_session_log(ws.session_dir)
                vlog().info("=== session %s opened from fetch (already on this PC) ===", sid)
                save_config(self.base, self.key)
                self.workspace, self.manifest = ws, previous
                self.accept()
                return
        ws.ensure()
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s fetch start (base=%s fromNum=%s toNum=%s) ===",
                    sid, self.base, from_num, to_num)
        manifest = Manifest(session_id=sid, base=self.base,
                            inspection_name=self._session_names.get(sid))

        try:
            all_photos = self._fetch_all_photos(self.client, sid)
        except ViewerApiError as e:
            QMessageBox.critical(self, tr("fetch_failed_title"), str(e))
            return
        photos = filter_photos_by_range(all_photos, from_num, to_num)
        vlog().info("fetch: %d photos in session, %d selected (fromNum=%s toNum=%s)",
                    len(all_photos), len(photos), from_num, to_num)
        if not photos:
            QMessageBox.warning(self, tr("fetch_empty_title"), tr("fetch_empty_msg"))
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
            self.lbl_status.setText(tr("fetch_progress", done=done, total=total))
            QApplication.processEvents()

        failures = download_photos(
            photos, ws.origin_dir, ws.detected_dir, progress=_prog)

        if previous is not None:
            manifest.keep_from(previous)
        manifest.save(ws.manifest_path)
        save_config(self.base, self.key)

        if failures:
            QMessageBox.warning(
                self, tr("fetch_partial_failed_title"),
                tr("fetch_partial_failed_msg", count=len(failures)))
        self.workspace = ws
        self.manifest = manifest
        self.accept()

    def _ask_existing(self, sid: int) -> str | None:
        """"open", "refetch", or None (cancel) for a job already on this PC."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(tr("fetch_existing_title"))
        box.setText(tr("fetch_existing_msg", sid=sid))
        btn_open = box.addButton(tr("login_open"), QMessageBox.AcceptRole)
        btn_refetch = box.addButton(tr("fetch_existing_refetch"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(btn_open)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is btn_open:
            return "open"
        if clicked is btn_refetch:
            return "refetch"
        return None

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
