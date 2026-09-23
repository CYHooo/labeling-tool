"""Labeling tool entry point (single launcher for every tool).

The login screen's tabs pick the tool:
  * online:  login + data-fetch dialogs (fetch + download) -> main labeling
             window wired to the per-session workspace -> manual batch upload
  * session: an already-downloaded job picked on the 로컬 작업 tab -> main
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
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox

from labeling_tool.logging_setup import vlog
from labeling_tool.ui.login_dialog import LoginDialog, MODE_FEWSHOT
from labeling_tool.ui.fetch_dialog import FetchDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def _open_fewshot_window():
    """Import and build the few-shot tool; None (after telling the user) on failure.

    Building it loads the SAM model synchronously, so show a busy notice. Any
    failure (no weights, HF auth, CUDA, ...) must return to the login screen
    instead of killing the app."""
    from annotation_tool import configs as fewshot_configs
    if fewshot_configs.BACKEND == "sam2":
        from labeling_tool.ui.sam2_weights_dialog import ensure_sam2_weights
        if not ensure_sam2_weights():
            return None  # declined / failed -> back to the login screen

    notice = QLabel("Few-shot 모델 로딩 중… 잠시 기다려 주세요.")
    notice.setWindowFlags(Qt.SplashScreen | Qt.WindowStaysOnTopHint)
    notice.setMargin(24)
    notice.show()
    QApplication.setOverrideCursor(Qt.WaitCursor)
    QApplication.processEvents()
    try:
        # imported lazily: pulls in torch, which production PCs may not have
        from annotation_tool.ui import main_window as fewshot_main_window
        return fewshot_main_window.MainWindow()
    except Exception as exc:  # noqa: BLE001 - show any load failure to the user
        vlog().exception("few-shot tool failed to open")
        QMessageBox.critical(
            None, "Few-shot 도구를 열 수 없습니다",
            f"{type(exc).__name__}: {exc}\n\n"
            "SAM 가중치(./checkpoint)와 torch 설치를 확인하세요 "
            "(annotation_tool/USAGE.md 참고).")
        return None
    finally:
        QApplication.restoreOverrideCursor()
        notice.close()


def open_tool_window(mode: str):
    """Build the window for a tool that needs no server session.

    Returns None when it could not be opened (caller goes back to login)."""
    if mode == MODE_FEWSHOT:
        return _open_fewshot_window()
    raise ValueError(f"not a standalone tool mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for arg in argv:
        if arg.startswith("--selftest"):
            # build smoke test (CI): no window, exit code = result
            from labeling_tool import selftest
            return selftest.run_selftest(arg.partition("=")[2] or "lite")

    app = QApplication([sys.argv[0], *argv])
    # Apply the dark theme app-wide so the login/fetch dialogs and every
    # QMessageBox match the main window (set before the first dialog shows).
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    # startup update check (silent when offline / throttled / a dev build)
    from labeling_tool.update.ui import check_for_updates
    check_for_updates(None)

    base = key = ""
    workspace = manifest = None
    while True:
        login = LoginDialog()
        if not login.exec_():
            return 0  # user cancelled

        if login.mode == MODE_FEWSHOT:
            tool_win = open_tool_window(login.mode)
            if tool_win is None:
                continue  # failed to open -> back to the login screen
            tool_win.show()
            return app.exec_()

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
            return 0
        if fetch.workspace is None or fetch.manifest is None:
            return 0
        workspace, manifest = fetch.workspace, fetch.manifest
        break

    client = None
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(workspace, manifest, client)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
