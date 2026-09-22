"""labeling_tool.app.main(): argv handling (--selftest short-circuit,
QApplication built from the passed-in argv, not the process's sys.argv)."""

import sys

from labeling_tool import app as app_module


class _FakeApp:
    """Stands in for QApplication: records the argv it was built with and
    returns immediately from exec_() (never actually shows a window)."""
    captured_argv = None

    def __init__(self, argv):
        _FakeApp.captured_argv = argv

    def setStyleSheet(self, *_a, **_k):
        pass


class _RejectingLoginDialog:
    """A login dialog whose exec_() reports "cancelled" so main() returns
    right after building QApplication, without opening any real window."""
    def __init__(self, *a, **k):
        pass

    def exec_(self):
        return 0


def test_main_builds_qapplication_from_passed_argv(monkeypatch):
    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _RejectingLoginDialog)
    monkeypatch.setattr(sys, "argv", ["LabelingTool.exe", "--ignored-process-arg"])

    rc = app_module.main(["--some-flag"])

    assert rc == 0
    assert _FakeApp.captured_argv == ["LabelingTool.exe", "--some-flag"]
