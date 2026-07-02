"""Standalone offline labeling entry point: opens the main window directly.
Pick the image folder + mask folder inside the GUI ("이미지 폴더" / "마스크 폴더"),
edit crack/spalling masks locally, save to a Labeling/ output folder. No login/API."""

from __future__ import annotations

import os
import sys

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.local_main_window import LocalMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    win = LocalMainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
