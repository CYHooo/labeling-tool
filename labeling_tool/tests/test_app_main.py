"""labeling_tool.app.main(): argv handling (--selftest short-circuit,
QApplication built from the passed-in argv, not the process's sys.argv)."""

import sys

import pytest

from labeling_tool import app as app_module
from labeling_tool.update import ui as update_ui


@pytest.fixture(autouse=True)
def _no_periodic_timer(monkeypatch):
    """main() starts a 4-hour QTimer; a test has no use for a real one."""
    monkeypatch.setattr(update_ui, "start_periodic_checks", lambda *a, **k: None)


class _FakeApp:
    """Stands in for QApplication: records the argv it was built with and
    returns immediately from exec_() (never actually shows a window)."""
    captured_argv = None

    def __init__(self, argv):
        _FakeApp.captured_argv = argv

    def setApplicationName(self, *_a):
        pass

    def setDesktopFileName(self, *_a):
        pass

    def setStyleSheet(self, *_a, **_k):
        pass

    def setWindowIcon(self, *_a, **_k):
        pass


class _FakeSignal:
    """Just connectable -- main() wires the few-shot signal before exec_()."""
    def connect(self, _slot):
        pass


class _RejectingLoginDialog:
    """A login dialog whose exec_() reports "cancelled" so main() returns
    right after building QApplication, without opening any real window."""
    def __init__(self, *a, **k):
        self.fewshotRequested = _FakeSignal()

    def exec_(self):
        return 0


def test_main_builds_qapplication_from_passed_argv(monkeypatch):
    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _RejectingLoginDialog)
    monkeypatch.setattr(sys, "argv", ["LabelingTool.exe", "--ignored-process-arg"])

    rc = app_module.main(["--some-flag"])

    assert rc == 0
    assert _FakeApp.captured_argv == ["LabelingTool.exe", "--some-flag"]


# ------------------------------------------- app-layer update: apply + recover

def test_main_applies_an_update_and_reports_failure(monkeypatch, tmp_path, capsys):
    from labeling_tool.update import patch
    seen = {}
    monkeypatch.setattr(patch, "apply_patch",
                        lambda z, root, sha: seen.update(z=z, sha=sha))
    assert app_module.main(["--apply-update", str(tmp_path / "u.zip"), "--sha256", "a" * 64]) == 0
    assert seen["sha"] == "a" * 64
    assert str(seen["z"]) == str(tmp_path / "u.zip")

    def boom(*a, **k):
        raise patch.PatchError("runtime mismatch")
    monkeypatch.setattr(patch, "apply_patch", boom)
    assert app_module.main(["--apply-update", str(tmp_path / "u.zip"), "--sha256", "a" * 64]) == 1
    assert "runtime mismatch" in capsys.readouterr().err


def test_main_recovers_an_interrupted_update_before_anything_else(monkeypatch):
    from labeling_tool import selftest
    from labeling_tool.update import patch
    order = []
    monkeypatch.setattr("labeling_tool.core.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(patch, "recover", lambda root: order.append("recover") or False)
    monkeypatch.setattr(patch, "cleanup", lambda root: order.append("cleanup"))
    monkeypatch.setattr(selftest, "run_selftest", lambda v: order.append("selftest") or 0)
    app_module.main(["--selftest=full"])
    assert order == ["recover", "cleanup", "selftest"]


def test_a_recovery_without_write_access_does_not_stop_startup(monkeypatch):
    # Linux: the app runs unprivileged and /opt is root-owned, so touching
    # the install dir can fail. Starting the app matters more.
    from labeling_tool import selftest
    from labeling_tool.update import patch

    def denied(root):
        raise PermissionError(13, "Permission denied", str(root))

    monkeypatch.setattr("labeling_tool.core.app_paths.is_frozen", lambda: True)
    monkeypatch.setattr(patch, "recover", denied)
    monkeypatch.setattr(patch, "cleanup", denied)
    monkeypatch.setattr(selftest, "run_selftest", lambda v: 7)
    assert app_module.main(["--selftest=full"]) == 7


def test_main_starts_the_periodic_check(monkeypatch):
    started = []
    monkeypatch.setattr(app_module, "QApplication", _FakeApp)
    monkeypatch.setattr(app_module, "LoginDialog", _RejectingLoginDialog)
    monkeypatch.setattr(update_ui, "start_periodic_checks", lambda *a, **k: started.append(a))
    app_module.main([])
    assert started == [()]
