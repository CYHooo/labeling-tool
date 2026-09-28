"""Startup login screen and tool selector.

Tabs pick which labeling tool to open:
  * Online labeling (default): BASE URL + API key (no network verify) -> fetch.
  * Local jobs: pick an already-downloaded job (labeling_tool/data/session_<id>/)
    and open it in the same main window; uploads work when URL + key are set.
  * Few-shot labeling: the torch-based annotation_tool (only when torch is installed).

Outputs for app.py (`self.mode`):
  * MODE_ONLINE:  self.base / self.key set, self.workspace is None -> FetchDialog
  * MODE_SESSION: self.workspace / self.manifest set -> go straight to main window
                  (self.base / self.key set only when uploading is possible)
  * MODE_FEWSHOT: no session; app.open_tool_window(mode)
"""

from __future__ import annotations

import importlib.util
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QComboBox, QFrame,
    QApplication,
)

from labeling_tool.core import i18n
from labeling_tool.core.i18n import LANGUAGES, LANG_DISPLAY_NAMES
from labeling_tool.ui.dialog_helpers import load_config, save_config
from labeling_tool.session.workspace import Workspace, DEFAULT_DATA_ROOT
from labeling_tool.session.local_jobs import LocalJob, list_local_jobs
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog
from labeling_tool.update.ui import check_for_updates
from labeling_tool.update.version import read_build_info

MODE_ONLINE = "online"
MODE_SESSION = "session"
MODE_FEWSHOT = "fewshot"

TAB_ONLINE, TAB_LOCAL, TAB_FEWSHOT = 0, 1, 2

# Translation keys for the job table's column headers, in display order.
JOB_COLUMN_KEYS = (
    "login_col_job", "login_col_inspection", "login_col_photos",
    "login_col_server", "login_col_modified",
)


def fewshot_available() -> bool:
    """True when the few-shot tool can run (torch installed).

    Uses find_spec only, so torch is never imported just to draw the login
    screen on production PCs that don't have it."""
    return importlib.util.find_spec("torch") is not None


def _tool_page(description: QLabel, button: QPushButton, hint: QLabel | None = None) -> QWidget:
    """A simple tab page: description text, optional hint, one action button."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lbl = description
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
    # Emitted when the user picks the few-shot tool. app.py connects this and
    # drives the loading state; the dialog cannot import app.py itself
    # (circular import), so the ordering lives on the app side.
    fewshotRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(680, 460)

        # which tool / flow the user picked (see module docstring)
        self.mode: str | None = None
        # online outputs
        self.base: str = ""
        self.key: str = ""
        # downloaded-job outputs
        self.workspace: Workspace | None = None
        self.manifest: Manifest | None = None
        # keeps the manual update-check thread alive; see ui.py's own
        # module-level registry for the startup check's equivalent.
        self._update_thread = None
        # remembered build info, so retranslate() can rebuild the version
        # label without calling read_build_info() again.
        self._build_info = read_build_info()
        # True between enter_loading_state() and exit_loading_state(); a
        # close during that window is ignored (see closeEvent).
        self._loading = False

        cfg = load_config()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_online_page(cfg), "")
        self.tabs.addTab(self._build_local_page(cfg), "")
        self.tabs.addTab(self._build_fewshot_page(), "")
        self.tabs.setCurrentIndex(TAB_ONLINE)

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

        # Inline loading area, shown while the few-shot model loads. Hidden
        # until enter_loading_state() is called. This replaces the old
        # free-floating QLabel splash, which rendered as grey-on-white
        # because a parentless QLabel picks up the theme's color rule but
        # not its background.
        self._loading_box = QFrame()
        self._loading_box.setObjectName("loadingBox")
        loading_lay = QVBoxLayout(self._loading_box)
        loading_lay.setContentsMargins(16, 14, 16, 14)
        loading_lay.setSpacing(10)
        self._lbl_loading = QLabel("")
        self._lbl_loading.setWordWrap(True)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)   # indeterminate
        self._loading_bar.setTextVisible(False)
        self._lbl_loading_detail = QLabel("")
        self._lbl_loading_detail.setWordWrap(True)
        self._lbl_loading_detail.setObjectName("loadingDetail")
        loading_lay.addWidget(self._lbl_loading)
        loading_lay.addWidget(self._loading_bar)
        loading_lay.addWidget(self._lbl_loading_detail)
        self._loading_box.setVisible(False)
        root.addWidget(self._loading_box)

        # bottom row: language selector, build identity, manual update check
        self.lbl_language = QLabel("")
        self.cmb_language = QComboBox()
        for code in LANGUAGES:
            self.cmb_language.addItem(LANG_DISPLAY_NAMES[code], code)
        self.cmb_language.setCurrentIndex(LANGUAGES.index(i18n.current_language()))
        self.cmb_language.currentIndexChanged.connect(self._on_language_changed)

        self.lbl_version = QLabel("")
        self.lbl_version.setStyleSheet("color: #9ea3aa;")
        self.btn_check_update = QPushButton("")
        self.btn_check_update.clicked.connect(self._on_check_update_clicked)
        bottom = QHBoxLayout()
        bottom.addWidget(self.lbl_language)
        bottom.addWidget(self.cmb_language)
        bottom.addWidget(self.lbl_version, 1)
        bottom.addWidget(self.btn_check_update)
        root.addLayout(bottom)

        self.retranslate()
        # app.py's login loop recreates LoginDialog() on every retry (failed
        # fetch, failed few-shot open); disconnect from the process-wide
        # LanguageManager singleton once this dialog is done so dead dialogs
        # don't keep piling up as listeners.
        self._lang_conn = i18n.language_manager().languageChanged.connect(
            self._on_language_changed_elsewhere)
        self.finished.connect(self._disconnect_language_manager)

    # ------------------------------------------------------------ i18n
    def _on_language_changed(self, idx: int) -> None:
        code = self.cmb_language.itemData(idx)
        if code:
            i18n.set_language(code)

    def _on_language_changed_elsewhere(self, _code: str) -> None:
        self.retranslate()

    def _disconnect_language_manager(self, *_args) -> None:
        conn = getattr(self, "_lang_conn", None)
        if conn is not None:
            try:
                i18n.language_manager().languageChanged.disconnect(conn)
            except TypeError:
                pass  # already disconnected
            self._lang_conn = None

    def closeEvent(self, event) -> None:
        # The model load blocks the UI thread, so a close during loading
        # cannot be honoured anyway -- ignore it rather than let the window
        # look frozen. Checked before the disconnect below: a dialog that
        # stays open must keep listening for language changes.
        if getattr(self, "_loading", False):
            event.ignore()
            return
        # accept()/reject() (the exec_() path used by app.py) already emit
        # `finished`, but a plain close() (e.g. the window's [x] button, or
        # a test) does not -- cover that path here too.
        self._disconnect_language_manager()
        super().closeEvent(event)

    def retranslate(self) -> None:
        """Re-apply every translated string. Called on init and whenever
        the language changes (either from this dialog's own combo, or from
        elsewhere, e.g. the main window)."""
        self.setWindowTitle(i18n.tr("login_title"))
        self.lbl_language.setText(i18n.tr("language"))
        self.tabs.setTabText(TAB_ONLINE, i18n.tr("login_tab_online"))
        self.tabs.setTabText(TAB_LOCAL, i18n.tr("login_tab_local"))
        self.tabs.setTabText(TAB_FEWSHOT, i18n.tr("login_tab_fewshot"))

        self.lbl_field_base.setText(i18n.tr("login_field_base"))
        self.lbl_field_key.setText(i18n.tr("login_field_key"))
        self.btn_next.setText(i18n.tr("login_next"))
        # lbl_status is only ever set to "" today (no code path writes a
        # message into it), but clear it explicitly so a future status
        # message can never survive a language change untranslated.
        self.lbl_status.setText("")

        self.lbl_field_local_base.setText(i18n.tr("login_field_base"))
        self.lbl_field_local_key.setText(i18n.tr("login_field_key"))
        self.tbl_jobs.setHorizontalHeaderLabels(
            [i18n.tr(k) for k in JOB_COLUMN_KEYS])
        if not self._jobs:
            self.lbl_jobs_empty.setText(
                i18n.tr("login_jobs_empty", tab=i18n.tr("login_tab_online")))
        self.btn_open_job.setText(i18n.tr("login_open"))
        self._update_upload_state()

        self._update_fewshot_texts()
        self.btn_fewshot.setText(i18n.tr("login_open"))

        info = self._build_info
        self.lbl_version.setText(
            i18n.tr("login_version", version=info.version)
            + (f" ({info.variant})" if info.variant else ""))
        self.btn_check_update.setText(i18n.tr("login_check_update"))

    def _on_check_update_clicked(self):
        """Disable the button for the duration of the check.

        A forced check that starts while another is already running (from
        the startup check or a double click) returns None immediately, so
        the button must be re-enabled right away in that case too.
        """
        self.btn_check_update.setEnabled(False)
        thread = check_for_updates(self, force=True)
        self._update_thread = thread
        if thread is None:
            self.btn_check_update.setEnabled(True)
        else:
            thread.finished.connect(lambda: self.btn_check_update.setEnabled(True))

    # ---------------------------------------------------------------- tabs
    def _build_online_page(self, cfg: dict) -> QWidget:
        """Tab 1: BASE URL + API key -> FetchDialog (downloaded jobs moved to tab 2)."""
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.lbl_field_base = QLabel("")
        self.lbl_field_key = QLabel("")
        self.form_online = QFormLayout()
        self.form_online.addRow(self.lbl_field_base, self.ed_base)
        self.form_online.addRow(self.lbl_field_key, self.ed_key)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        self.lbl_status = QLabel("")

        self.btn_next = QPushButton("")
        self.btn_next.setDefault(True)
        self.btn_next.clicked.connect(self._on_next)
        nav = QHBoxLayout()
        nav.addStretch(1)
        nav.addWidget(self.btn_next)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addLayout(self.form_online)
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
        self.lbl_field_local_base = QLabel("")
        self.lbl_field_local_key = QLabel("")
        self.form_local = QFormLayout()
        self.form_local.addRow(self.lbl_field_local_base, self.ed_local_base)
        self.form_local.addRow(self.lbl_field_local_key, self.ed_local_key)

        self._jobs: list[LocalJob] = list_local_jobs(DEFAULT_DATA_ROOT)
        self.tbl_jobs = QTableWidget(len(self._jobs), len(JOB_COLUMN_KEYS))
        self.tbl_jobs.setHorizontalHeaderLabels(
            [i18n.tr(k) for k in JOB_COLUMN_KEYS])
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
                i18n.tr("login_jobs_empty", tab=i18n.tr("login_tab_online")))

        self.lbl_upload = QLabel("")
        self.btn_open_job = QPushButton("")
        self.btn_open_job.clicked.connect(self._on_open_job)
        self.btn_open_job.setEnabled(False)
        nav = QHBoxLayout()
        nav.addWidget(self.lbl_upload, 1)
        nav.addWidget(self.btn_open_job)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addLayout(self.form_local)
        lay.addWidget(self.tbl_jobs, 1)
        lay.addWidget(self.lbl_jobs_empty)
        lay.addLayout(nav)
        if self._jobs:
            self.tbl_jobs.selectRow(0)  # most recent job
        self._update_upload_state()
        return page

    def _build_fewshot_page(self) -> QWidget:
        """Tab 3: few-shot annotation tool (annotation_tool, needs torch)."""
        self.btn_fewshot = QPushButton("")
        self.btn_fewshot.clicked.connect(self.fewshotRequested.emit)
        self.lbl_fewshot_hint = QLabel("")
        self.lbl_fewshot_desc = QLabel("")
        self.lbl_fewshot_desc.setWordWrap(True)
        self._update_fewshot_texts()
        return _tool_page(self.lbl_fewshot_desc, self.btn_fewshot, self.lbl_fewshot_hint)

    def _update_fewshot_texts(self) -> None:
        """(Re)build the few-shot tab's description/hint/button in the
        current language. Called from __init__ and from retranslate()."""
        from labeling_tool.core.app_paths import is_frozen

        if not fewshot_available():
            self.btn_fewshot.setEnabled(False)
            self.lbl_fewshot_hint.setStyleSheet("color: #e0a040;")
            if is_frozen():
                self.lbl_fewshot_hint.setText(i18n.tr("login_fewshot_hint_lite"))
            else:
                self.lbl_fewshot_hint.setText(i18n.tr("login_fewshot_hint_no_torch"))
        else:
            self.btn_fewshot.setEnabled(True)
            self.lbl_fewshot_hint.setText("")
        self.lbl_fewshot_desc.setText(
            i18n.tr("login_fewshot_desc_lite") if is_frozen()
            else i18n.tr("login_fewshot_desc_full"))

    # -------------------------------------------------------------- actions
    def enter_loading_state(self, message: str, detail: str = "") -> None:
        """Show the inline loading area and lock the dialog down.

        The model load blocks the UI thread, so everything that would open a
        second modal (update check) or rewrite the loading text (language
        switch) is disabled for the duration."""
        self._lbl_loading.setText(message)
        self._lbl_loading.setStyleSheet("")
        self._lbl_loading_detail.setText(detail)
        self._lbl_loading_detail.setVisible(bool(detail))
        self._loading_bar.setVisible(True)
        self._loading_box.setVisible(True)
        self.tabs.setEnabled(False)
        self.cmb_language.setEnabled(False)
        self.btn_check_update.setEnabled(False)
        self._loading = True
        QApplication.processEvents()

    def exit_loading_state(self, error: str | None = None) -> None:
        """Unlock the dialog. With `error`, keep the area visible and show
        the message there instead of in a QMessageBox -- a modal box under
        offscreen Qt hangs the test suite, and an inline error lets the user
        pick another tab without restarting."""
        self.tabs.setEnabled(True)
        self.cmb_language.setEnabled(True)
        self.btn_check_update.setEnabled(True)
        self._loading = False
        self._loading_bar.setVisible(False)
        if error:
            self._lbl_loading.setText(error)
            self._lbl_loading.setStyleSheet("color: #e06c6c;")
            self._lbl_loading_detail.setVisible(False)
            self._loading_box.setVisible(True)
        else:
            self._loading_box.setVisible(False)

    def _accept_mode(self, mode: str) -> None:
        self.mode = mode
        vlog().info("login: tool selected -> %s", mode)
        self.accept()

    def _on_next(self):
        base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        if not base or not key:
            QMessageBox.warning(self, i18n.tr("login_warn_input_required_title"),
                                 i18n.tr("login_warn_input_required_msg"))
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
            self.lbl_upload.setText(i18n.tr("login_upload_possible"))
            self.lbl_upload.setStyleSheet("color: #3aa55a;")
        else:
            self.lbl_upload.setText(i18n.tr("login_upload_impossible"))
            self.lbl_upload.setStyleSheet("color: #e0a040;")

    def _on_open_job(self):
        job = self._selected_job()
        if job is None:
            return
        ws = Workspace(root=DEFAULT_DATA_ROOT, session_id=job.session_id)
        if not ws.manifest_path.exists():
            QMessageBox.warning(self, i18n.tr("login_warn_no_manifest_title"),
                                 i18n.tr("login_warn_no_manifest_msg", path=ws.manifest_path))
            return
        # Credentials enable uploading this job to EC2; both empty -> fully
        # offline (upload disabled in the main window).
        base = self.ed_local_base.text().strip()
        key = self.ed_local_key.text().strip()
        if base and key and job.base:
            if base.rstrip("/") != job.base.rstrip("/"):
                QMessageBox.warning(
                    self, i18n.tr("login_warn_server_mismatch_title"),
                    i18n.tr("login_warn_server_mismatch_msg", base=job.base),
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
                self, i18n.tr("login_warn_manifest_error_title"),
                i18n.tr("login_warn_manifest_error_msg", path=ws.manifest_path, exc=exc),
            )
            return
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local, upload=%s) ===",
                    job.session_id, "on" if (base and key) else "off")
        self.mode = MODE_SESSION
        self.accept()
