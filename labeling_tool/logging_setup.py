"""Logging: one global app log plus the per-job Viewer API log.

app.log  -- <user data>/logs/app.log (see log_dir()), rotated at 1 MB with
            five old files kept. Everything the app logs goes here: startup,
            sign-in, updates, uncaught exceptions, Qt warnings, and every
            per-job line below, so one file covers a whole run.
vapi.log -- <session_dir>/vapi.log: timestamped request + download +
            prepare-phase entries of the open job, so its data flow and where
            time is spent (client crack metrics vs. network) can be diagnosed.

Never log a password or an API key; presigned URL query strings are
redacted by the formatters (see redact()).
"""

from __future__ import annotations

import logging
import os
import platform
import re
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_LOGGER_NAME = "labeling_tool"
LOGGER_NAME = "labeling_tool.vapi"
APP_LOG_NAME = "app.log"
APP_LOG_MAX_BYTES = 1024 * 1024
APP_LOG_BACKUPS = 5


def alog() -> logging.Logger:
    """The app-wide logger; the job logger vlog() is its child."""
    return logging.getLogger(APP_LOGGER_NAME)


def vlog() -> logging.Logger:
    """The shared Viewer API logger. Its lines go to the open job's vapi.log
    (once attach_session_log ran) and, through alog(), to app.log."""
    return logging.getLogger(LOGGER_NAME)


LOG_DIR_ENV = "LM_LABELING_LOG_DIR"


def log_dir() -> Path:
    """Where app.log lives: $LM_LABELING_LOG_DIR when set, else beside the
    user data (the install folder on Windows, ~/.local/share/lm-labeling-tool
    on Linux), or <repo>/logs in a source checkout."""
    override = os.environ.get(LOG_DIR_ENV, "").strip()
    if override:
        return Path(override)
    from labeling_tool.core import app_paths
    if not app_paths.is_frozen():
        return app_paths.REPO_ROOT / "logs"
    return app_paths.user_data_home() / "logs"


_PRESIGNED_QUERY = re.compile(r"(https?://[^\s?'\"]+)\?[^\s'\"]*(?:X-Amz-|Signature=)[^\s'\"]*")


def redact(text: str) -> str:
    """Drop the query string of a presigned URL: its signature and access
    key id are credentials, and app.log is the file users are asked to send."""
    return _PRESIGNED_QUERY.sub(r"\1?<redacted>", text)


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class _SafeRotatingFileHandler(RotatingFileHandler):
    """Rotation that survives a locked app.log. On Windows a second running
    instance (or the old one during an update restart) keeps the file open,
    the rename fails, and the stock handler retried on every record and
    lost them all. Here a failed rotation just keeps appending to the same
    file for the rest of this run."""

    def doRollover(self):
        try:
            super().doRollover()
        except OSError:
            self.maxBytes = 0                # no more rotation in this run
            if self.stream is None:
                self.stream = self._open()


def setup_app_log(directory: Path | None = None) -> Path | None:
    """Attach the rotating app.log handler (once). None when the folder
    cannot be written: the app runs on without a log rather than not at all."""
    directory = Path(directory) if directory is not None else log_dir()
    log = alog()
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        if getattr(h, "_app_handler", False):
            log.removeHandler(h)
            h.close()
    path = directory / APP_LOG_NAME
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fh = _SafeRotatingFileHandler(path, maxBytes=APP_LOG_MAX_BYTES,
                                      backupCount=APP_LOG_BACKUPS, encoding="utf-8")
    except OSError as exc:
        print(f"app log disabled: {exc}", file=sys.stderr)
        return None
    fh._app_handler = True               # tag so a second setup replaces it
    fh.setFormatter(_RedactingFormatter(
        "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)
    return path


def log_startup(build, language: str) -> None:
    """The first line of a run: which build, on what, in which language."""
    alog().info(
        "start: version=%s commit=%s runtime=%s variant=%s platform=%s (%s) "
        "python=%s lang=%s pid=%d",
        build.version, build.commit or "-", build.runtime or "-",
        build.variant or "-", sys.platform, platform.platform(),
        platform.python_version(), language, os.getpid())


def install_exception_hooks(abort_in_qt: bool = True) -> None:
    """Log uncaught exceptions (main thread and worker threads) with their
    traceback before the usual handling.

    Installing sys.excepthook stops PyQt5 from aborting on an exception that
    escapes a Qt slot; with abort_in_qt the hook keeps that behaviour (an
    unknown state is not worth continuing in), via qFatal once a
    QApplication exists."""
    previous_thread_hook = threading.excepthook

    def _excepthook(exc_type, exc, tb):
        alog().critical("uncaught exception", exc_info=(exc_type, exc, tb))
        for h in alog().handlers:
            h.flush()
        sys.__excepthook__(exc_type, exc, tb)
        if abort_in_qt and _inside_qt_code():
            try:
                # ASCII only: PyQt5 encodes qFatal's text as ASCII, and a
                # Korean message made the hook itself fail -- the app then
                # ran on instead of aborting.
                from PyQt5.QtCore import qFatal
                qFatal("uncaught %s (details in app.log)" % exc_type.__name__)
            finally:
                os.abort()

    def _thread_hook(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread is not None else "?"
            alog().error("uncaught exception in thread %s", name,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        previous_thread_hook(args)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook


def _inside_qt_code() -> bool:
    """True when an exception escaped from code Qt called: a slot while the
    event loop runs, or a worker QThread. That is where PyQt5 aborted the
    app before this hook existed; elsewhere (before the event loop starts)
    Python's own handling -- exit code 1 -- still applies."""
    from PyQt5.QtCore import QCoreApplication, QThread
    app = QCoreApplication.instance()
    if app is None:
        return False
    if QThread.currentThread() is not app.thread():
        return True
    return app.thread().loopLevel() > 0


def install_qt_message_handler() -> None:
    """Route Qt's own warnings and errors into app.log (still echoed to
    stderr, as without a handler)."""
    from PyQt5.QtCore import QtMsgType, qInstallMessageHandler
    levels = {QtMsgType.QtWarningMsg: logging.WARNING,
              QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def _handler(mode, context, message):
        level = levels.get(mode)
        if level is not None:
            logging.getLogger(APP_LOGGER_NAME + ".qt").log(level, "%s", message)
            for h in alog().handlers:
                h.flush()
        print(message, file=sys.stderr)

    qInstallMessageHandler(_handler)


def attach_session_log(session_dir) -> Path:
    """Route Viewer API logs to <session_dir>/vapi.log (one active session at a time).

    Idempotent: replaces any previously attached session file handler so
    switching sessions logs to the right file. The lines still propagate to
    app.log.
    """
    log = vlog()
    log.setLevel(logging.INFO)
    log.propagate = True
    for h in list(log.handlers):
        if getattr(h, "_session_handler", False):
            log.removeHandler(h)
            h.close()
    path = Path(session_dir) / "vapi.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh._session_handler = True          # tag so we can replace it later
    fh.setFormatter(_RedactingFormatter(
        "%(asctime)s.%(msecs)03d %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S"))
    log.addHandler(fh)
    alog().info("job log: %s", path)
    return path
