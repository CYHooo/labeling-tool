"""The window icon.

PyInstaller's EXE(icon=) writes the .ico into the exe's PE resources, which
is what Windows shows for the FILE. The title bar and the taskbar button
come from Qt instead, and need QApplication.setWindowIcon -- without it the
running app shows Qt's default icon no matter what the exe looks like.
"""

import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from labeling_tool.core import app_paths

_app = QApplication.instance() or QApplication([])


def test_icon_resource_ships_with_the_package():
    """Bundled next to the code, so the same path works from source and
    inside _internal/ after PyInstaller collects it."""
    icon = app_paths.resource_path("icon.ico")
    assert icon.is_file(), f"{icon} missing"
    assert icon.stat().st_size > 1024


def test_icon_loads_as_a_real_qicon():
    icon = QIcon(str(app_paths.resource_path("icon.ico")))
    assert not icon.isNull()
    # the sizes make_icon.py writes; a truncated .ico would lose the large ones
    have = {s.width() for s in icon.availableSizes()}
    assert {16, 32, 256} <= have, f"expected 16/32/256 among {sorted(have)}"


def test_main_sets_the_application_window_icon(monkeypatch):
    """Set on the QApplication, so every window -- login, fetch, labeling,
    few-shot -- inherits it without each one remembering to."""
    from labeling_tool import app as app_module

    captured = {}

    class _FakeApp:
        def __init__(self, argv):
            captured["argv"] = argv

        def setStyleSheet(self, *_a, **_k):
            pass

        def setWindowIcon(self, icon):
            captured["icon"] = icon

        def exec_(self):
            return 0

    class _FakeSignal:
        def connect(self, _slot):
            pass

    class _RejectingLogin:
        def __init__(self, *a, **k):
            self.fewshotRequested = _FakeSignal()

        def exec_(self):
            return 0

    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _RejectingLogin)
    monkeypatch.setattr(sys, "argv", ["LM_LabelingTool.exe"])

    app_module.main([])

    assert "icon" in captured, "main() never called setWindowIcon"
    assert not captured["icon"].isNull(), "the window icon loaded empty"
    # The icon must come from the PNG: an ICO here would be null on a Linux
    # build whose Qt has no ICO plugin, and the assertion above would still
    # pass on a developer's Windows machine.
    assert captured["icon"].availableSizes(), "the window icon carries no bitmap"
    expected = QIcon(str(app_paths.resource_path("icon.png")))
    assert (captured["icon"].availableSizes()[0].width()
            == expected.availableSizes()[0].width())


def test_png_icon_resource_ships_with_the_package():
    # Qt's ICO plugin is not guaranteed to be collected into the Linux
    # build, and the .desktop entry needs a bitmap regardless.
    png = app_paths.resource_path("icon.png")
    assert png.is_file(), f"{png} missing"
    assert png.stat().st_size > 1024


def test_png_icon_loads_as_a_real_qicon():
    icon = QIcon(str(app_paths.resource_path("icon.png")))
    assert not icon.isNull()
    have = {s.width() for s in icon.availableSizes()}
    assert 256 in have, f"expected a 256px bitmap among {sorted(have)}"
