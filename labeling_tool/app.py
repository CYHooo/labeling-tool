"""Labeling tool entry point (single launcher for every tool).

The login screen's tabs pick the tool:
  * online:  login + data-fetch dialogs (fetch + download) -> main labeling
             window wired to the per-session workspace -> manual batch upload
  * session: an already-downloaded job picked on the Local jobs tab -> main
             window (uploads when URL + key were given)
  * fewshot: annotation_tool (SAM3/SAM2, needs torch; imported only on demand)
Run on a LOCAL PC (not the AI server).
"""

from __future__ import annotations

import os
import sys

# Prevent cv2's bundled Qt plugins from clashing with PyQt5 (same guard the
# original labeling GUI uses).
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.i18n import tr
from labeling_tool.logging_setup import vlog
from labeling_tool.ui.login_dialog import LoginDialog, MODE_FEWSHOT
from labeling_tool.ui.fetch_dialog import FetchDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def _ensure_weights() -> bool:
    """True when the SAM2.1 weights are present (or not needed).

    Split out so tests can stub it without reaching into the weights
    dialog."""
    from annotation_tool import configs as fewshot_configs
    if fewshot_configs.BACKEND != "sam2":
        return True
    from labeling_tool.ui.sam2_weights_dialog import ensure_sam2_weights
    return ensure_sam2_weights()


def _build_fewshot_main_window():
    """Import the few-shot tool and build its window.

    Imported lazily: pulls in torch, which production PCs may not have."""
    from annotation_tool.ui import main_window as fewshot_main_window
    return fewshot_main_window.MainWindow()


def load_fewshot_window() -> tuple[object | None, str | None]:
    """Build the few-shot window: (window, None) or (None, message).

    Weights are the caller's business -- see open_fewshot_from_login, which
    settles them before any loading notice goes up.

    Building the window loads the SAM model synchronously and blocks the UI
    thread; the caller shows the login dialog's inline loading area first."""
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return _build_fewshot_main_window(), None
    except Exception as exc:  # noqa: BLE001 - any load failure is reported
        vlog().exception("few-shot tool failed to open")
        return None, tr("login_loading_failed",
                        type=type(exc).__name__, exc=exc)
    finally:
        QApplication.restoreOverrideCursor()


def open_fewshot_from_login(dlg):
    """Drive the few-shot open from the login dialog. Returns the window
    (the dialog has been accepted) or None (the dialog stays open).

    Ordering matters: ensure_sam2_weights() puts up its own modal question
    and download dialog, so it has to finish BEFORE the loading area claims
    the model is being loaded -- otherwise that modal stacks on top of a
    notice describing the wrong thing for the whole download."""
    if not _ensure_weights():
        return None  # declined -- nothing was shown, nothing to report
    dlg.enter_loading_state(tr("app_fewshot_loading"),
                            tr("login_loading_detail"))
    win, err = load_fewshot_window()
    if win is None:
        dlg.exit_loading_state(err)
        return None
    dlg.mode = MODE_FEWSHOT
    dlg.accept()
    return win


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for arg in argv:
        if arg.startswith("--selftest"):
            # build smoke test (CI): no window, exit code = result
            from labeling_tool import selftest
            return selftest.run_selftest(arg.partition("=")[2] or "full")

    app = QApplication([sys.argv[0], *argv])
    # The exe's own icon is a PE resource written by PyInstaller; Windows
    # uses it for the file. The title bar and the taskbar button come from
    # Qt, so without this the running app shows Qt's default icon. Set on
    # the QApplication so every window inherits it.
    from labeling_tool.core.app_paths import resource_path
    app.setWindowIcon(QIcon(str(resource_path("icon.ico"))))
    # Apply the dark theme app-wide so the login/fetch dialogs and every
    # QMessageBox match the main window (set before the first dialog shows).
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    # Update check on every launch (silent when offline or a dev build). A
    # result that lands after a session window opened is offered when that
    # window closes -- see prompt_pending_update() below.
    from labeling_tool.update.ui import (
        check_for_updates, prompt_pending_update, wait_for_checks,
    )
    check_for_updates(None)

    base = key = ""
    workspace = manifest = None
    while True:
        login = LoginDialog()
        # The few-shot model loads while this dialog is still up, so the
        # notice lives inside it. `holder` carries the built window out of
        # the callback; the dialog only accepts once it exists.
        holder = {}

        def _on_fewshot(dlg=login, holder=holder):
            win = open_fewshot_from_login(dlg)
            if win is not None:
                holder["win"] = win

        login.fewshotRequested.connect(_on_fewshot)

        if not login.exec_():
            wait_for_checks()
            return 0  # user cancelled

        if login.mode == MODE_FEWSHOT:
            tool_win = holder["win"]
            tool_win.show()
            code = app.exec_()
            prompt_pending_update()
            return code

        base, key = login.base, login.key
        if login.workspace is not None:
            # offline: a downloaded session was opened directly
            workspace, manifest = login.workspace, login.manifest
            break

        # online: creds entered -> fetch screen
        fetch = FetchDialog(base=base, key=key)
        if not fetch.exec_():
            if fetch.go_back:
                continue  # back to login screen, reopen LoginDialog
            wait_for_checks()
            return 0
        if fetch.workspace is None or fetch.manifest is None:
            wait_for_checks()
            return 0
        workspace, manifest = fetch.workspace, fetch.manifest
        break

    client = None
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(workspace, manifest, client)
    win.show()
    code = app.exec_()
    prompt_pending_update()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
