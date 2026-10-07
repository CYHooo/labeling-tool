"""Labeling tool entry point (single launcher for every tool).

The login screen's tabs pick the tool:
  * online:  login + data-fetch dialogs (fetch + download) -> main labeling
             window wired to the per-session workspace -> manual batch upload
  * session: an already-fetched job opened from the Labeling tab -> main
             window (uploads when URL + key were given)
  * fewshot: annotation_tool (SAM3/SAM2, needs torch; imported only on demand)
Run on a LOCAL PC (not the AI server).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Prevent cv2's bundled Qt plugins from clashing with PyQt5 (same guard the
# original labeling GUI uses).
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtCore import QSize, Qt
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


# The deb's .desktop file name (packaging/deb.py PACKAGE). Linux docks map a
# window to its .desktop entry -- and so to its icon -- by WM_CLASS (X11) or
# app_id (Wayland); Qt's default, the executable name "LM_LabelingTool",
# matched no entry and the dock showed a blank generic icon.
DESKTOP_ID = "lm-labeling-tool"


def apply_desktop_identity(app, platform: str = sys.platform) -> None:
    """Give Linux windows the .desktop entry's id: the application name is
    WM_CLASS's class part on X11, the desktop file name is the Wayland app_id."""
    if platform.startswith("linux"):
        app.setApplicationName(DESKTOP_ID)
        app.setDesktopFileName(DESKTOP_ID)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from labeling_tool.core import app_paths
    from labeling_tool.update import patch
    if app_paths.is_frozen():
        # A swap interrupted by a crash or power cut is undone before the
        # app does anything else. On Linux the app runs unprivileged and
        # /opt is root-owned, so this can be refused; the next root-run
        # --apply-update recovers instead, and starting matters more.
        try:
            patch.recover(app_paths.app_home())
            patch.cleanup(app_paths.app_home())
        except OSError as exc:
            vlog().warning("update recovery skipped: %s: %s", type(exc).__name__, exc)
    if "--apply-update" in argv:
        # Run as root by `pkexec <exe> --apply-update <zip> --sha256 <hex>`
        # (installer.build_apply_command): no window, exit code = result,
        # the reason on stderr for the unprivileged app to show.
        zip_path = argv[argv.index("--apply-update") + 1]
        sha = argv[argv.index("--sha256") + 1]
        try:
            patch.apply_patch(Path(zip_path), app_paths.app_home(), sha)
        except (patch.PatchError, OSError) as exc:
            print(f"update failed: {exc}", file=sys.stderr)
            return 1
        return 0
    for arg in argv:
        if arg.startswith("--selftest"):
            # build smoke test (CI): no window, exit code = result
            from labeling_tool import selftest
            return selftest.run_selftest(arg.partition("=")[2] or "full")

    app = QApplication([sys.argv[0], *argv])
    apply_desktop_identity(app)
    # The exe's own icon is a PE resource written by PyInstaller; Windows
    # uses it for the file. The title bar and the taskbar button come from
    # Qt, so without this the running app shows Qt's default icon. Set on
    # the QApplication so every window inherits it.
    from labeling_tool.core.app_paths import resource_path
    # PNG rather than ICO: Qt's ICO plugin is not guaranteed to be collected
    # into the Linux build, and the .desktop entry needs a bitmap anyway.
    # One addFile() per size -- NOT a single file -- because
    # packaging/make_icon.py hand-tunes the <=32px renders (heavier stroke,
    # bigger glyph, no underline) so the taskbar/title bar stay legible;
    # QIcon(<one file>) would instead generically rescale that one bitmap,
    # losing that tuning exactly the way a single 256px source would. Sizes
    # here must match packaging/make_icon.py's PNG_SIZES.
    icon = QIcon()
    for px in (16, 32, 48, 256):
        icon.addFile(str(resource_path(f"icon-{px}.png")), QSize(px, px))
    app.setWindowIcon(icon)
    # Apply the dark theme app-wide so the login/fetch dialogs and every
    # QMessageBox match the main window (set before the first dialog shows).
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    # Update check on every launch and every 4 hours after (silent when
    # offline or a dev build). A result that lands after a session window
    # opened is offered when that window closes -- see
    # prompt_pending_update() below.
    from labeling_tool.update.ui import (
        check_for_updates, prompt_pending_update, start_periodic_checks,
        wait_for_checks,
    )
    check_for_updates(None)
    start_periodic_checks()

    base = key = ""
    workspace = manifest = None
    # Signed in once per run: a reopened dialog (back from the fetch screen,
    # a failed few-shot load) starts on its jobs page until the user logs out.
    user = None
    while True:
        login = LoginDialog(user=user)
        # The few-shot model loads while this dialog is still up, so the
        # notice lives inside it. `holder` carries the built window out of
        # the callback; the dialog only accepts once it exists.
        holder = {}

        def _on_fewshot(dlg=login, holder=holder):
            win = open_fewshot_from_login(dlg)
            if win is not None:
                holder["win"] = win

        login.fewshotRequested.connect(_on_fewshot)

        accepted = login.exec_()
        user = login.user
        if not accepted:
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
