"""Global app log: <user data>/logs/app.log, rotated, catching what the
per-job vapi.log cannot (startup, sign-in, updates, uncaught errors)."""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

import pytest

from PyQt5.QtWidgets import QApplication

from labeling_tool import logging_setup
from labeling_tool.core import app_paths

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_logging():
    """Every test leaves the loggers and hooks as it found them."""
    app_logger = logging.getLogger(logging_setup.APP_LOGGER_NAME)
    vapi = logging_setup.vlog()
    saved = (list(app_logger.handlers), app_logger.level, list(vapi.handlers),
             vapi.propagate, sys.excepthook, threading.excepthook)
    yield
    for logger, handlers in ((app_logger, saved[0]), (vapi, saved[2])):
        for h in list(logger.handlers):
            if h not in handlers:
                logger.removeHandler(h)
                h.close()
    app_logger.setLevel(saved[1])
    vapi.propagate = saved[3]
    sys.excepthook, threading.excepthook = saved[4], saved[5]


def _flush():
    for h in logging.getLogger(logging_setup.APP_LOGGER_NAME).handlers:
        h.flush()


def test_log_dir_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv(logging_setup.LOG_DIR_ENV, str(tmp_path / "elsewhere"))
    assert logging_setup.log_dir() == tmp_path / "elsewhere"


def test_log_dir_is_beside_the_user_data(monkeypatch, tmp_path):
    monkeypatch.delenv(logging_setup.LOG_DIR_ENV, raising=False)
    monkeypatch.setattr(app_paths, "user_data_home", lambda: tmp_path)
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    assert logging_setup.log_dir() == tmp_path / "logs"


def test_log_dir_in_a_source_checkout_is_the_repo_logs_folder(monkeypatch):
    monkeypatch.delenv(logging_setup.LOG_DIR_ENV, raising=False)
    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    assert logging_setup.log_dir() == app_paths.REPO_ROOT / "logs"


def test_setup_writes_a_rotating_app_log(tmp_path):
    path = logging_setup.setup_app_log(tmp_path)
    assert path == tmp_path / "app.log"
    handlers = [h for h in logging.getLogger(logging_setup.APP_LOGGER_NAME).handlers
                if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 1024 * 1024 and handlers[0].backupCount == 5
    logging_setup.alog().info("hello %s", "world")
    _flush()
    assert "hello world" in path.read_text(encoding="utf-8")


def test_setup_twice_keeps_one_handler(tmp_path):
    logging_setup.setup_app_log(tmp_path)
    logging_setup.setup_app_log(tmp_path)
    handlers = [h for h in logging.getLogger(logging_setup.APP_LOGGER_NAME).handlers
                if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1


def test_job_log_lines_also_reach_the_app_log(tmp_path):
    path = logging_setup.setup_app_log(tmp_path / "logs")
    session = tmp_path / "session_7"
    logging_setup.attach_session_log(session)
    logging_setup.vlog().info("uploaded %d photos", 3)
    _flush()
    for h in logging_setup.vlog().handlers:
        h.flush()
    assert "uploaded 3 photos" in (session / "vapi.log").read_text(encoding="utf-8")
    assert "uploaded 3 photos" in path.read_text(encoding="utf-8")


def test_an_unwritable_log_dir_is_not_fatal(tmp_path):
    blocker = tmp_path / "logs"
    blocker.write_text("a file where the folder should be")
    assert logging_setup.setup_app_log(blocker) is None
    logging_setup.alog().info("still fine")                     # no exception


def test_uncaught_exceptions_are_logged_with_their_traceback(tmp_path, monkeypatch):
    path = logging_setup.setup_app_log(tmp_path)
    logging_setup.install_exception_hooks(abort_in_qt=False)
    try:
        raise ValueError("boom in main")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "ValueError: boom in main" in text
    assert "Traceback" in text


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_uncaught_thread_exceptions_are_logged(tmp_path):
    path = logging_setup.setup_app_log(tmp_path)
    logging_setup.install_exception_hooks(abort_in_qt=False)

    def boom():
        raise RuntimeError("boom in thread")

    t = threading.Thread(target=boom, name="worker-x")
    t.start()
    t.join()
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "RuntimeError: boom in thread" in text and "worker-x" in text


def test_startup_line_names_version_platform_and_runtime(tmp_path):
    from labeling_tool.update.version import BuildInfo
    path = logging_setup.setup_app_log(tmp_path)
    logging_setup.log_startup(BuildInfo("0.2.9", "full", commit="abc1234", runtime="r2dd9cf8f"), "ko")
    _flush()
    text = path.read_text(encoding="utf-8")
    for part in ("0.2.9", "abc1234", "r2dd9cf8f", sys.platform, "lang=ko"):
        assert part in text


def test_apply_update_and_selftest_runs_write_no_app_log(tmp_path, monkeypatch, app_log_starts):
    # --apply-update runs as root (pkexec): a root-owned app.log would lock
    # the user's own app out of its log.
    from labeling_tool import app, selftest
    from labeling_tool.update import patch
    monkeypatch.setattr(patch, "apply_patch", lambda *a, **k: None)
    monkeypatch.setattr(selftest, "run_selftest", lambda mode: 0)
    assert app.main(["--apply-update", str(tmp_path / "u.zip"), "--sha256", "00"]) == 0
    assert app.main(["--selftest=quick"]) == 0
    assert app_log_starts == []


def test_start_app_logging_sets_up_the_log_and_hooks(tmp_path, monkeypatch):
    from labeling_tool import app
    import importlib
    real = importlib.reload(app)._start_app_logging      # undo the conftest stub
    monkeypatch.setattr(logging_setup, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(logging_setup, "install_qt_message_handler", lambda: None)
    real()
    _flush()
    assert "start: version=" in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert sys.excepthook is not sys.__excepthook__     # restored by the fixture


def test_sign_in_logs_the_id_but_never_the_password(tmp_path, monkeypatch):
    from labeling_tool.ui import login_dialog as ld
    monkeypatch.setattr(ld, "load_config", lambda: {})
    monkeypatch.setattr(ld, "save_config", lambda *a, **k: None)
    monkeypatch.setattr(ld, "save_user_id", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(ld, "DEFAULT_DATA_ROOT", tmp_path / "data")
    path = logging_setup.setup_app_log(tmp_path / "logs")
    dlg = ld.LoginDialog()
    try:
        for password in ("wrong-pass-123", "admin"):
            dlg.ed_user.setText("admin")
            dlg.ed_password.setText(password)
            dlg.ed_key.setText("secret-api-key-xyz")
            dlg._on_sign_in()
    finally:
        dlg.close()
    _flush()
    text = path.read_text(encoding="utf-8")
    assert "signed in as admin" in text and "sign-in refused" in text
    for secret in ("wrong-pass-123", "secret-api-key-xyz"):
        assert secret not in text
