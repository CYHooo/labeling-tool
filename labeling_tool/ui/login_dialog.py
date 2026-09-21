"""Startup login screen and tool selector.

Tabs pick which labeling tool to open:
  * 온라인 라벨링 (default): BASE URL + API key (no network verify), or open an
    already-downloaded session offline — the original login screen, unchanged.
  * 로컬 폴더: the folder-based LocalMainWindow (no login / upload).
  * Few-shot 라벨링: the torch-based annotation_tool (only when torch is installed).

Outputs for app.py (`self.mode`):
  * MODE_ONLINE:  self.base / self.key set, self.workspace is None -> FetchDialog
  * MODE_SESSION: self.workspace / self.manifest set -> go straight to main window
  * MODE_LOCAL / MODE_FEWSHOT: no session; app.open_tool_window(mode)
"""

from __future__ import annotations

import importlib.util

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QComboBox, QTabWidget, QWidget,
)

from labeling_tool.ui.dialog_helpers import load_config, save_config
from labeling_tool.session.workspace import Workspace, list_local_session_ids
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog

MODE_ONLINE = "online"
MODE_SESSION = "session"
MODE_LOCAL = "local"
MODE_FEWSHOT = "fewshot"

TAB_ONLINE, TAB_LOCAL, TAB_FEWSHOT = 0, 1, 2


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
        self.resize(520, 280)

        # which tool / flow the user picked (see module docstring)
        self.mode: str | None = None
        # online outputs
        self.base: str = ""
        self.key: str = ""
        # offline outputs
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None

        cfg = load_config()
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        form = QFormLayout()
        form.addRow("BASE URL", self.ed_base)
        form.addRow("X-Viewer-Api-Key", self.ed_key)

        # offline section
        self.cb_local = QComboBox()
        local_ids = list_local_session_ids()
        for sid in local_ids:
            self.cb_local.addItem(f"session_{sid}", sid)
        self.btn_open_local = QPushButton("이미 받은 세션 열기")
        self.btn_open_local.clicked.connect(self._on_open_local)
        if not local_ids:
            self.cb_local.addItem("(받은 세션 없음)")
            self.cb_local.setEnabled(False)
            self.btn_open_local.setEnabled(False)
        offline = QHBoxLayout()
        offline.addWidget(self.cb_local, 1)
        offline.addWidget(self.btn_open_local)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_next = QPushButton("다음")
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._on_next)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.btn_next)

        # --- tab 1: online labeling (the original login screen) ---
        online_page = QWidget()
        online = QVBoxLayout(online_page)
        online.addLayout(form)
        online.addWidget(QLabel("오프라인으로 열기:"))
        online.addLayout(offline)
        online.addWidget(self.progress)
        online.addWidget(self.lbl_status)
        online.addLayout(nav)

        # --- tab 2: local folder labeling (LocalMainWindow) ---
        self.btn_local_folder = QPushButton("열기")
        self.btn_local_folder.clicked.connect(lambda: self._accept_mode(MODE_LOCAL))
        local_page = _tool_page(
            "로컬의 이미지 폴더와 마스크 폴더를 직접 선택해 라벨링합니다.\n"
            "로그인·업로드 없이 동작하며, 결과는 이미지 폴더 옆 Labeling/ 폴더에 저장됩니다.",
            self.btn_local_folder)

        # --- tab 3: few-shot annotation tool (annotation_tool, needs torch) ---
        self.btn_fewshot = QPushButton("열기")
        self.btn_fewshot.clicked.connect(lambda: self._accept_mode(MODE_FEWSHOT))
        self.lbl_fewshot_hint = QLabel("")
        if not fewshot_available():
            self.btn_fewshot.setEnabled(False)
            self.lbl_fewshot_hint.setStyleSheet("color: #e0a040;")
            self.lbl_fewshot_hint.setText(
                "⚠ torch 가 설치되어 있지 않아 사용할 수 없습니다.\n"
                "설치: pip install -r annotation_tool/requirements-gpu.txt")
        fewshot_page = _tool_page(
            "SAM3 / SAM2.1 기반 다중 클래스 반자동 라벨링 도구 (few-shot 학습 데이터용).\n"
            "GPU(torch)와 SAM 가중치가 필요하며, 처음 열 때 모델 로딩에 시간이 걸립니다.",
            self.btn_fewshot, self.lbl_fewshot_hint)

        self.tabs = QTabWidget()
        self.tabs.addTab(online_page, "온라인 라벨링")
        self.tabs.addTab(local_page, "로컬 폴더")
        self.tabs.addTab(fewshot_page, "Few-shot 라벨링")
        self.tabs.setCurrentIndex(TAB_ONLINE)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

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

    def _on_open_local(self):
        sid = self.cb_local.currentData()
        if sid is None:
            return
        ws = Workspace.default(session_id=int(sid))
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, "없음",
                                f"로컬 매니페스트 없음: {ws.manifest_path}")
            return
        # Carry any entered/prefilled credentials so a locally-opened session can
        # still upload to EC2. Both empty -> stays fully offline (upload disabled).
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        if base and key:
            save_config(base, key)
            self.base, self.key = base, key
        self.workspace = ws
        self.manifest = Manifest.load(ws.manifest_path)
        self.mode = MODE_SESSION
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local, upload=%s) ===",
                    sid, "on" if (base and key) else "off")
        self.accept()
