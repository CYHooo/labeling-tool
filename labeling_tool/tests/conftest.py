"""Make any Qt-touching test run headless."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""
