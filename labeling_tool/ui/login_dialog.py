"""Startup login screen and tool selector.

Tabs pick which labeling tool to open:
  * 온라인 라벨링 (default): BASE URL + API key (no network verify) -> fetch.
  * 로컬 작업: pick an already-downloaded job (labeling_tool/data/session_<id>/)
    and open it in the same main window; uploads work when URL + key are set.
  * Few-shot 라벨링: the torch-based annotation_tool (only when torch is installed).

Outputs for app.py (`self.mode`):
  * MODE_ONLINE:  self.base / self.key set, self.workspace is None -> FetchDialog
  * MODE_SESSION: self.workspace / self.manifest set -> go straight to main window
                  (self.base / self.key set only when uploading is possible)
  * MODE_FEWSHOT: no session; app.open_tool_window(mode)
"""

from __future__ import annotations

import importlib.util
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView,
)

from labeling_tool.ui.dialog_helpers import load_config, save_config
from labeling_tool.session.workspace import Workspace, DEFAULT_DATA_ROOT
from labeling_tool.session.local_jobs import LocalJob, list_local_jobs
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog

MODE_ONLINE = "online"
MODE_SESSION = "session"
MODE_FEWSHOT = "fewshot"

TAB_ONLINE, TAB_LOCAL, TAB_FEWSHOT = 0, 1, 2

JOB_COLUMNS = ("세션", "점검명", "사진 / 업로드", "서버", "최근 수정")


def fewshot_available() -> bool:
    """True when the few-shot tool can run (torch installed).

    Uses find_spec only, so torch is never imported just to draw the login
    screen on production PCs that don't have it."""
    return importlib.util.find_spec("torch") is not None


def _tool_page(description: str, button: QPushButton, hint: QLabel | None = None) -> QWidget:
    """A simple tab page: description text, optional hint, one action button."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lbl = QLabel(description)
    lbl.setWordWrap(True)
    lay.addWidget(lbl)
    if hint is not None:
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(hint)
    lay.addStretch(1)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(button)
    lay.addLayout(row)
    return page


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그인")
        self.resize(680, 460)

        # which tool / flow the user picked (see module docstring)
        self.mode: str | None = None
        # online outputs
        self.base: str = ""
        self.key: str = ""
        # downloaded-job outputs
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None

        cfg = load_config()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_online_page(cfg), "온라인 라벨링")
        self.tabs.addTab(self._build_local_page(cfg), "로컬 작업")
        self.tabs.addTab(self._build_fewshot_page(), "Few-shot 라벨링")
        self.tabs.setCurrentIndex(TAB_ONLINE)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

    # ---------------------------------------------------------------- tabs
    def _build_online_page(self, cfg: dict) -> QWidget:
        """Tab 1: BASE URL + API key -> FetchDialog (downloaded jobs moved to tab 2)."""
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("BASE URL", self.ed_base)
        form.addRow("X-Viewer-Api-Key", self.ed_key)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_next = QPushButton("다음")
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._on_next)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.btn_next)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addLayout(form)
        lay.addStretch(1)
        lay.addWidget(self.progress)
        lay.addWidget(self.lbl_status)
        lay.addLayout(nav)
        return page

    def _build_local_page(self, cfg: dict) -> QWidget:
        """Tab 2: already-downloaded jobs, newest first; URL/key enable upload."""
        # URL follows the selected job's server; the key is prefilled from config
        self.ed_local_base = QLineEdit(cfg.get("base", ""))
        self.ed_local_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_local_key.setEchoMode(QLineEdit.Password)
        for ed in (self.ed_local_base, self.ed_local_key):
            ed.textChanged.connect(self._update_upload_state)
        form = QFormLayout()
        form.addRow("BASE URL", self.ed_local_base)
        form.addRow("X-Viewer-Api-Key", self.ed_local_key)

        self._jobs: list[LocalJob] = list_local_jobs(DEFAULT_DATA_ROOT)
        self.tbl_jobs = QTableWidget(len(self._jobs), len(JOB_COLUMNS))
        self.tbl_jobs.setHorizontalHeaderLabels(JOB_COLUMNS)
        self.tbl_jobs.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_jobs.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_jobs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_jobs.verticalHeader().setVisible(False)
        self.tbl_jobs.setAlternatingRowColors(True)
        header = self.tbl_jobs.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for row, job in enumerate(self._jobs):
            cells = (
                str(job.session_id),
                job.inspection_name or "—",
                f"{job.photo_count} / {job.synced_count}",
                job.host or "—",
                datetime.fromtimestamp(job.modified).strftime("%Y-%m-%d %H:%M"),
            )
            for col, text in enumerate(cells):
                self.tbl_jobs.setItem(row, col, QTableWidgetItem(text))
        self.tbl_jobs.itemSelectionChanged.connect(self._on_job_selected)
        self.tbl_jobs.cellDoubleClicked.connect(lambda *_: self._on_open_job())

        self.lbl_jobs_empty = QLabel("")
        self.lbl_jobs_empty.setWordWrap(True)
        if not self._jobs:
            self.lbl_jobs_empty.setText(
                "받은 작업이 없습니다. 「온라인 라벨링」에서 먼저 데이터를 가져오세요.")

        self.lbl_upload = QLabel("")
        self.btn_open_job = QPushButton("열기")
        self.btn_open_job.clicked.connect(self._on_open_job)
        self.btn_open_job.setEnabled(False)
        nav = QHBoxLayout()
        nav.addWidget(self.lbl_upload, 1)
        nav.addWidget(self.btn_open_job)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addLayout(form)
        lay.addWidget(self.tbl_jobs, 1)
        lay.addWidget(self.lbl_jobs_empty)
        lay.addLayout(nav)
        if self._jobs:
            self.tbl_jobs.selectRow(0)  # most recent job
        self._update_upload_state()
        return page

    def _build_fewshot_page(self) -> QWidget:
        """Tab 3: few-shot annotation tool (annotation_tool, needs torch)."""
        from labeling_tool.core.app_paths import is_frozen

        self.btn_fewshot = QPushButton("열기")
        self.btn_fewshot.clicked.connect(lambda: self._accept_mode(MODE_FEWSHOT))
        self.lbl_fewshot_hint = QLabel("")
        if not fewshot_available():
            self.btn_fewshot.setEnabled(False)
            self.lbl_fewshot_hint.setStyleSheet("color: #e0a040;")
            if is_frozen():
                self.lbl_fewshot_hint.setText(
                    "⚠ 이 빌드는 lite 버전이라 few-shot 도구를 사용할 수 없습니다.\n"
                    "few-shot 도구가 필요하면 full 빌드를 설치하세요.")
            else:
                self.lbl_fewshot_hint.setText(
                    "⚠ torch 가 설치되어 있지 않아 사용할 수 없습니다.\n"
                    "설치: pip install -r annotation_tool/requirements-gpu.txt")
        description = (
            "SAM2.1 기반 다중 클래스 반자동 라벨링 도구 (few-shot 학습 데이터용).\n"
            "GPU(torch)와 SAM 가중치가 필요하며, 처음 열 때 모델 로딩에 시간이 걸립니다."
            if is_frozen() else
            "SAM3 / SAM2.1 기반 다중 클래스 반자동 라벨링 도구 (few-shot 학습 데이터용).\n"
            "GPU(torch)와 SAM 가중치가 필요하며, 처음 열 때 모델 로딩에 시간이 걸립니다."
        )
        return _tool_page(description, self.btn_fewshot, self.lbl_fewshot_hint)

    # -------------------------------------------------------------- actions
    def _accept_mode(self, mode: str) -> None:
        self.mode = mode
        vlog().info("login: tool selected -> %s", mode)
        self.accept()

    def _on_next(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        if not base or not key:
            QMessageBox.warning(self, "입력 필요", "BASE/Key를 입력하세요.")
            return
        save_config(base, key)
        self.base, self.key = base, key
        self.mode = MODE_ONLINE
        self.accept()

    def _selected_job(self) -> LocalJob | None:
        rows = self.tbl_jobs.selectionModel().selectedRows()
        return self._jobs[rows[0].row()] if rows else None

    def _on_job_selected(self):
        job = self._selected_job()
        self.btn_open_job.setEnabled(job is not None)
        # upload must go back to the server the job was fetched from
        if job is not None:
            if job.base:
                self.ed_local_base.setText(job.base)
            else:
                self.ed_local_base.clear()

    def _update_upload_state(self):
        if self.ed_local_base.text().strip() and self.ed_local_key.text().strip():
            self.lbl_upload.setText("업로드: 가능 (URL/Key 입력됨)")
            self.lbl_upload.setStyleSheet("color: #3aa55a;")
        else:
            self.lbl_upload.setText("업로드: 불가 — 로컬 저장만 (URL/Key 를 입력하면 업로드 가능)")
            self.lbl_upload.setStyleSheet("color: #e0a040;")

    def _on_open_job(self):
        job = self._selected_job()
        if job is None:
            return
        ws = Workspace(root=DEFAULT_DATA_ROOT, session_id=job.session_id)
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, "없음",
                                f"로컬 매니페스트 없음: {ws.manifest_path}")
            return
        # Credentials enable uploading this job to EC2; both empty -> fully
        # offline (upload disabled in the main window).
        base = self.ed_local_base.text().strip()
        key = self.ed_local_key.text().strip()
        if base and key and job.base:
            if base.rstrip("/") != job.base.rstrip("/"):
                QMessageBox.warning(
                    self, "서버 불일치",
                    f"이 작업은 {job.base} 에서 받아왔습니다.\n"
                    "다른 서버로 업로드할 수 없습니다.\n"
                    "URL을 원래 서버로 되돌리거나, URL/Key를 비우고 오프라인으로 여세요.",
                )
                return
        if base and key:
            save_config(base, key)
            self.base, self.key = base, key
        self.workspace = ws
        try:
            self.manifest = Manifest.load(ws.manifest_path)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            QMessageBox.warning(
                self, "매니페스트 오류",
                f"로컬 매니페스트를 읽을 수 없습니다: {ws.manifest_path}\n{exc}",
            )
            return
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local, upload=%s) ===",
                    job.session_id, "on" if (base and key) else "off")
        self.mode = MODE_SESSION
        self.accept()
