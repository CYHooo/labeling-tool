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

from labeling_tool.ui.connect_dialog import ConnectDialog
from labeling_tool.ui.main_window import ViewerMainWindow
from labeling_tool.api.client import ViewerApiClient


def main() -> int:
    app = QApplication(sys.argv)

    dialog = ConnectDialog()
    if not dialog.exec_():
        return 0  # user cancelled
    if dialog.workspace is None or dialog.manifest is None:
        return 0

    client = None
    base = dialog.ed_base.text().strip()
    key = dialog.ed_key.text().strip()
    if base and key:
        client = ViewerApiClient(base_url=base, api_key=key)

    win = ViewerMainWindow(dialog.workspace, dialog.manifest, client)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
