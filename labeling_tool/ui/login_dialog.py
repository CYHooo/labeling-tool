"""Startup login screen and tool selector.

A signed-in user comes first: page 1 asks for ID / PW (labeling_tool.auth)
and the server (BASE URL + API key); page 2 is the jobs page, whose tabs pick
which labeling tool to open:
  * Labeling (default): the jobs already fetched to this PC
    (labeling_tool/data/session_<id>/). "Fetch a new job" goes on to the
    fetch screen with page 1's server; "Open" reopens a fetched job,
    uploading to the server it came from when a key is entered.
  * Few-shot labeling: the torch-based annotation_tool (only when torch is installed).

Outputs for app.py (`self.mode`):
  * MODE_ONLINE:  self.base / self.key set, self.workspace is None -> FetchDialog
  * MODE_SESSION: self.workspace / self.manifest set -> go straight to main window
                  (self.base / self.key set only when uploading is possible)
  * MODE_FEWSHOT: no session; app.open_fewshot_from_login(dialog)
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from urllib.parse import urlparse

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QLabel, QMessageBox, QTabWidget, QWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QComboBox, QFrame,
    QApplication,
)

from labeling_tool import auth
from labeling_tool.core import i18n
from labeling_tool.core.i18n import LANGUAGES, LANG_DISPLAY_NAMES
from labeling_tool.ui.dialog_helpers import load_config, save_config, save_user_id
from labeling_tool.session.workspace import Workspace, DEFAULT_DATA_ROOT
from labeling_tool.session.local_jobs import LocalJob, list_local_jobs
from labeling_tool.session.manifest import Manifest
from labeling_tool.logging_setup import attach_session_log, vlog
from labeling_tool.update.ui import check_for_updates
from labeling_tool.update.version import read_build_info

MODE_ONLINE = "online"
MODE_SESSION = "session"
MODE_FEWSHOT = "fewshot"

TAB_LABELING, TAB_FEWSHOT = 0, 1
PAGE_SIGN_IN, PAGE_WORK = 0, 1

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

    def __init__(self, parent=None, user: auth.User | None = None,
                 authenticator: auth.Authenticator | None = None):
        super().__init__(parent)
        self.resize(680, 460)

        # which tool / flow the user picked (see module docstring)
        self.mode: str | None = None
        # The signed-in user. app.py passes the previous dialog's user back in
        # when it reopens this dialog, so one sign-in lasts until log-out.
        self.user: auth.User | None = user
        self._auth = authenticator or auth.default_authenticator()
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

        sign_in_page = self._build_sign_in_page(cfg)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_labeling_page(cfg), "")
        self.tabs.addTab(self._build_fewshot_page(), "")
        self.tabs.setCurrentIndex(TAB_LABELING)

        root = QVBoxLayout(self)
        self.pages = QStackedWidget()
        self.pages.addWidget(sign_in_page)
        self.pages.addWidget(self.tabs)
        self.pages.setCurrentIndex(PAGE_WORK if user is not None else PAGE_SIGN_IN)
        root.addWidget(self.pages)
        # The ID is usually remembered: start typing the password.
        (self.ed_password if self.ed_user.text() else self.ed_user).setFocus()

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
        # Deliberately no progress bar: the model load blocks the UI thread,
        # so an animated bar would freeze mid-sweep and read as a hung
        # program (Windows adds "(Not Responding)" to the title bar). Text
        # that admits the wait beats motion the event loop cannot deliver.
        self._lbl_loading_detail = QLabel("")
        self._lbl_loading_detail.setWordWrap(True)
        self._lbl_loading_detail.setObjectName("loadingDetail")
        loading_lay.addWidget(self._lbl_loading)
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
        self.setWindowTitle(i18n.tr(
            "login_title" if self.pages.currentIndex() == PAGE_SIGN_IN else "work_title"))
        self.lbl_app_name.setText("LM Labeling Tool")
        self.lbl_field_user.setText(i18n.tr("signin_field_id"))
        self.lbl_field_password.setText(i18n.tr("signin_field_password"))
        self.lbl_server.setText(i18n.tr("signin_server_section"))
        self.btn_sign_in.setText(i18n.tr("signin_button"))
        if self.lbl_sign_in_error.text():
            self.lbl_sign_in_error.setText(i18n.tr("signin_error"))
        self.btn_log_out.setText(i18n.tr("login_logout"))
        self.lbl_user.setText(i18n.tr("login_signed_in_as", user=self.user.user_id) if self.user else "")
        self.lbl_language.setText(i18n.tr("language"))
        self.tabs.setTabText(TAB_LABELING, i18n.tr("login_tab_labeling"))
        self.tabs.setTabText(TAB_FEWSHOT, i18n.tr("login_tab_fewshot"))

        self.lbl_field_base.setText(i18n.tr("login_field_base"))
        self.lbl_field_key.setText(i18n.tr("login_field_key"))
        self.lbl_jobs_title.setText(i18n.tr("login_jobs_title"))
        self.tbl_jobs.setHorizontalHeaderLabels(
            [i18n.tr(k) for k in JOB_COLUMN_KEYS])
        self.btn_new_job.setText(i18n.tr("login_new_job"))
        if not self._jobs:
            self.lbl_jobs_empty.setText(
                i18n.tr("login_jobs_empty", button=i18n.tr("login_new_job")))
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
    def _build_sign_in_page(self, cfg: dict) -> QWidget:
        """Page 1: ID / PW, then the server every later step uses."""
        self.lbl_app_name = QLabel("")
        self.lbl_app_name.setAlignment(Qt.AlignCenter)
        self.lbl_app_name.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px;")
        self.ed_user = QLineEdit(cfg.get("userId", ""))
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.Password)
        self.lbl_field_user = QLabel("")
        self.lbl_field_password = QLabel("")
        # One form for both groups so every field lines up in one column.
        form = QFormLayout()
        form.addRow(self.lbl_field_user, self.ed_user)
        form.addRow(self.lbl_field_password, self.ed_password)

        self.lbl_server = QLabel("")
        self.lbl_server.setStyleSheet("font-weight: bold; padding-top: 8px;")
        self.ed_base = QLineEdit(cfg.get("base", ""))
        self.ed_key = QLineEdit(cfg.get("apiKey", ""))
        self.ed_key.setEchoMode(QLineEdit.Password)
        for ed in (self.ed_base, self.ed_key):
            ed.textChanged.connect(self._update_upload_state)
        self.lbl_field_base = QLabel("")
        self.lbl_field_key = QLabel("")
        form.addRow(self.lbl_server)
        form.addRow(self.lbl_field_base, self.ed_base)
        form.addRow(self.lbl_field_key, self.ed_key)

        self.lbl_sign_in_error = QLabel("")
        self.lbl_sign_in_error.setStyleSheet("color: #e06c6c;")
        self.btn_sign_in = QPushButton("")
        # Enter in any field signs in -- wired per field, not as the dialog's
        # default button, which would also fire from the jobs page.
        self.btn_sign_in.setAutoDefault(False)
        self.btn_sign_in.clicked.connect(self._on_sign_in)
        for ed in (self.ed_user, self.ed_password, self.ed_base, self.ed_key):
            ed.returnPressed.connect(self._on_sign_in)
        row = QHBoxLayout()
        row.addWidget(self.lbl_sign_in_error, 1)
        row.addWidget(self.btn_sign_in)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(self.lbl_app_name)
        lay.addLayout(form)
        lay.addStretch(1)
        lay.addLayout(row)
        return page

    def _on_sign_in(self):
        try:
            user = self._auth.login(self.ed_user.text(), self.ed_password.text())
        except auth.AuthError:
            vlog().info("sign-in refused for %r", self.ed_user.text().strip())
            self.lbl_sign_in_error.setText(i18n.tr("signin_error"))
            self.ed_password.selectAll()
            self.ed_password.setFocus()
            return
        self.user = user
        save_user_id(user.user_id)
        vlog().info("signed in as %s", user.user_id)
        self.lbl_sign_in_error.setText("")
        self.pages.setCurrentIndex(PAGE_WORK)
        self.retranslate()

    def _on_log_out(self):
        vlog().info("signed out (%s)", self.user.user_id if self.user else "-")
        self.user = None
        self.ed_password.clear()
        self.pages.setCurrentIndex(PAGE_SIGN_IN)
        self.retranslate()
        self.ed_password.setFocus()

    def _build_labeling_page(self, cfg: dict) -> QWidget:
        """The jobs already on this PC and two ways on: fetch a new job with
        the sign-in page's server, or open a fetched one."""
        self.lbl_user = QLabel("")
        self.lbl_user.setStyleSheet("color: #9ea3aa;")
        self.lbl_jobs_title = QLabel("")
        self.lbl_jobs_title.setStyleSheet("font-weight: bold;")
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

        self.lbl_upload = QLabel("")
        self.btn_new_job = QPushButton("")
        self.btn_new_job.clicked.connect(self._on_new_job)
        self.btn_open_job = QPushButton("")
        self.btn_open_job.clicked.connect(self._on_open_job)
        self.btn_open_job.setEnabled(False)
        # No default button: Enter after typing a new server must not open the
        # newest old job, nor start a fetch. Both take an explicit click.
        for btn in (self.btn_new_job, self.btn_open_job):
            btn.setAutoDefault(False)
            btn.setDefault(False)
        self.btn_log_out = QPushButton("")
        self.btn_log_out.setAutoDefault(False)
        self.btn_log_out.clicked.connect(self._on_log_out)
        nav = QHBoxLayout()
        nav.addWidget(self.btn_log_out)
        nav.addWidget(self.lbl_upload, 1)
        nav.addWidget(self.btn_new_job)
        nav.addWidget(self.btn_open_job)

        title = QHBoxLayout()
        title.addWidget(self.lbl_jobs_title, 1)
        title.addWidget(self.lbl_user)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addLayout(title)
        lay.addWidget(self.tbl_jobs, 1)
        lay.addWidget(self.lbl_jobs_empty)
        lay.addLayout(nav)
        if self._jobs:
            self.tbl_jobs.selectRow(0)  # most recent job
        self._update_upload_state()
        return page

    def _build_fewshot_page(self) -> QWidget:
        """Tab 2: few-shot annotation tool (annotation_tool, needs torch)."""
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

    def _on_new_job(self):
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

    def _upload_target(self, job: LocalJob | None) -> str:
        """Where a job's edits go: the server it was fetched from, so it can
        never land on another one; the entered server only for a job whose
        manifest predates recording it."""
        if job is not None and job.base:
            return job.base
        return self.ed_base.text().strip()

    def _on_job_selected(self):
        self.btn_open_job.setEnabled(self._selected_job() is not None)
        self._update_upload_state()

    def _update_upload_state(self):
        if not hasattr(self, "lbl_upload"):
            return  # a field fired textChanged before the page was built
        target = self._upload_target(self._selected_job())
        if target and self.ed_key.text().strip():
            host = urlparse(target).netloc or target
            self.lbl_upload.setText(i18n.tr("login_upload_possible", host=host))
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
        try:
            manifest = Manifest.load(ws.manifest_path)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            QMessageBox.warning(
                self, i18n.tr("login_warn_manifest_error_title"),
                i18n.tr("login_warn_manifest_error_msg", path=ws.manifest_path, exc=exc),
            )
            return
        # A key enables uploading this job, always to its own server; no key
        # -> fully offline (upload disabled in the main window).
        typed_base = self.ed_base.text().strip()
        key = self.ed_key.text().strip()
        target = self._upload_target(job)
        if typed_base and key:
            save_config(typed_base, key)
        if target and key:
            self.base, self.key = target, key
        self.workspace = ws
        self.manifest = manifest
        attach_session_log(ws.session_dir)
        vlog().info("=== session %s opened (local, upload=%s) ===",
                    job.session_id, self.base or "off")
        self.mode = MODE_SESSION
        self.accept()
