"""Startup login screen: collect BASE URL + API key (no network verify),
or open an already-downloaded session offline.

Outputs for app.py:
  * offline: self.workspace / self.manifest set -> go straight to main window
  * online:  self.base / self.key set, self.workspace is None -> open FetchDialog
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QComboBox,
)

from labeling_tool.ui.dialog_helpers import load_config, save_config
from labeling_tool.session.workspace import Workspace, list_local_session_ids
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그인")
        self.resize(480, 240)

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

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(QLabel("오프라인으로 열기:"))
        root.addLayout(offline)
        root.addWidget(self.progress)
        root.addWidget(self.lbl_status)
        root.addLayout(nav)

    def _on_next(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        if not base or not key:
            QMessageBox.warning(self, "입력 필요", "BASE/Key를 입력하세요.")
            return
        save_config(base, key)
        self.base, self.key = base, key
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
        self.workspace = ws
        self.manifest = Manifest.load(ws.manifest_path)
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local) ===", sid)
        self.accept()
