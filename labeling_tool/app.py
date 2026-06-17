"""Local labeling tool entry point.

Flow: connection wizard (V1 fetch + download) -> main labeling window
wired to the per-session workspace -> manual batch upload (V2->V3->V4).
Run on a LOCAL PC (not the AI server).
"""

from __future__ import annotations

import os
import sys

# Prevent cv2's bundled Qt plugins from clashing with PyQt5 (same guard the
# original labeling GUI uses).
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.login_dialog import LoginDialog
from labeling_tool.ui.fetch_dialog import FetchDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def main() -> int:
    app = QApplication(sys.argv)

    login = LoginDialog()
    if not login.exec_():
        return 0  # user cancelled

    base, key = login.base, login.key
    workspace = manifest = None  # assigned in both branches below
    if login.workspace is not None:
        # offline: a downloaded session was opened directly
        workspace, manifest = login.workspace, login.manifest
    else:
        # online: creds entered -> fetch screen
        fetch = FetchDialog(base=base, key=key)
        if not fetch.exec_():
            return 0
        if fetch.workspace is None or fetch.manifest is None:
            return 0
        workspace, manifest = fetch.workspace, fetch.manifest

    client = None
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(workspace, manifest, client)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
