"""Update prompt: three buttons, progress, and handing over to the installer."""
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.update import checker, state, ui

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _drain_qt_events():
    """Flush any queued cross-thread signal left by a background QThread.

    UpdateCheckThread.found is a queued connection, so a test that starts a
    thread and only calls thread.wait() (without pumping the event loop) can
    leave its _on_found callback pending. If left alone it would fire later,
    inside some unrelated test's QApplication.processEvents() call, and pop a
    real (blocking) QMessageBox under the offscreen platform. Neutralize the
    message boxes and drain the queue after every test in this module so
    nothing leaks into the rest of the suite.
    """
    yield
    orig_info, orig_crit = QMessageBox.information, QMessageBox.critical
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    try:
        _app.processEvents()
    finally:
        QMessageBox.information = orig_info
        QMessageBox.critical = orig_crit


INFO = checker.UpdateInfo(version="1.0.1", variant="lite",
                          asset_name="LabelingTool-lite-Setup-v1.0.1.exe",
                          asset_url="https://x/s.exe", size=170 * 1024 * 1024,
                          sha256="a" * 64, notes="fixes")


def test_prompt_later_does_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.LATER)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda *a, **k: pytest.fail("downloaded"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert state.load(tmp_path).skipped_version is None


def test_prompt_skip_records_version(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.SKIP)
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_prompt_update_downloads_verifies_and_launches(monkeypatch, tmp_path):
    seen = {}

    def fake_download(url, dest, sha256, progress=None, **kw):
        seen["download"] = (url, sha256)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"setup")
        if progress:
            progress(10, 100)

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda path, log, **kw: seen.setdefault("launched", path))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is True
    assert seen["download"] == (INFO.asset_url, INFO.sha256)
    assert seen["launched"].name == INFO.asset_name


def test_download_failure_is_reported_and_app_keeps_running(monkeypatch, tmp_path):
    shown = []

    def boom(*a, **k):
        raise ValueError("checksum mismatch")

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", boom)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda *a, **k: pytest.fail("launched after failure"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False
    assert "checksum" in shown[0]


def test_cancelled_download_is_silent(monkeypatch, tmp_path):
    def cancelled(*a, **k):
        raise ui.net_download.DownloadCancelled()

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", cancelled)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail("error shown"))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is False


def test_check_skips_dev_builds(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: pytest.fail("network hit from a dev build"))
    ui.check_for_updates(None, home=tmp_path)          # dev build: version 0.0.0-dev


def test_check_is_throttled(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    state.mark_checked(tmp_path)
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: pytest.fail("checked despite throttle"))
    ui.check_for_updates(None, home=tmp_path)


def test_forced_check_ignores_throttle_and_skip(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    calls = []
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: calls.append(a) or None)
    state.mark_checked(tmp_path)
    state.skip_version("1.0.1", tmp_path)
    thread = ui.check_for_updates(None, force=True, home=tmp_path)
    thread.wait(5000)
    assert calls
