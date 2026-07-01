"""Standalone offline labeling entry point: pick image + mask folders, edit
crack/spalling masks locally, save to an output folder. No login/API."""

from __future__ import annotations

import os
import sys

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""

from PyQt5.QtWidgets import QApplication

from labeling_tool.ui.folder_dialog import FolderDialog
from labeling_tool.ui.local_main_window import LocalMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    from labeling_tool.core.window.styles import STYLESHEET
    app.setStyleSheet(STYLESHEET)

    dlg = FolderDialog()
    if not dlg.exec_():
        return 0
    dlg.output_dir.mkdir(parents=True, exist_ok=True)
    win = LocalMainWindow(dlg.image_dir, dlg.mask_dir, dlg.output_dir)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
