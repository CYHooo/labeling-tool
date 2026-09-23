"""Update prompt: three buttons, progress, and handing over to the installer."""
import tempfile
import threading

import pytest
from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget

from labeling_tool.update import checker, state, ui
from labeling_tool.update.version import BuildInfo

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _drain_qt_events():
    """Test-isolation only: drain queued cross-thread signals between tests.

    UpdateCheckThread.found is a queued connection, so a test that starts a
    thread and only calls thread.wait() (without pumping the event loop)
    leaves its _on_found callback queued rather than run. Thread ownership
    and parent-widget lifetime are handled in production code (see
    _RUNNING_CHECKS and the sip.isdeleted() guard in ui.py); this fixture
    just makes sure a pending callback runs (against a neutralized
    QMessageBox) before the next test, instead of firing at an arbitrary
    later point in the suite.
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


def test_running_check_is_retained_then_released(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: None)
    # force=False: an empty tmp_path has no last_check, so should_check() is
    # already True - this avoids the "up to date" QMessageBox that force=True
    # would pop for a found=None result.
    thread = ui.check_for_updates(None, home=tmp_path)
    assert thread in ui._RUNNING_CHECKS
    thread.wait(5000)
    _app.processEvents()  # let the queued `finished` signal run _on_finished
    assert thread not in ui._RUNNING_CHECKS


def test_on_found_with_deleted_parent_does_not_raise(monkeypatch, tmp_path):
    parent = QWidget()
    sip.delete(parent)  # force immediate C++ destruction (not deferred)
    assert sip.isdeleted(parent)

    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.LATER)
    thread = ui.check_for_updates(parent, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()  # runs _on_found (and _on_finished) against the dead parent


# --------------------------------------------------------------- C2: a failed
# check must never be reported as "up to date", and must only surface at all
# when the user explicitly asked (force=True).

def test_forced_failed_check_warns_instead_of_lying(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("no network")))
    warned, informed = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: informed.append(a[2]))
    thread = ui.check_for_updates(None, force=True, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()
    assert warned and "TimeoutError" in warned[0]
    assert not informed  # never the "최신 버전" lie


def test_unforced_failed_check_stays_silent(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("no network")))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: pytest.fail("warned on an unforced failure"))
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: pytest.fail("reported anything on an unforced failure"))
    thread = ui.check_for_updates(None, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()


# ----------------------------------------------------- I3: shutdown must wait
# for an in-flight check instead of destroying a running QThread.

def test_wait_for_checks_blocks_until_thread_finishes(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    release = threading.Event()

    def slow_find(*a, **k):
        release.wait(5)
        return None

    monkeypatch.setattr(ui.checker, "find_update", slow_find)
    thread = ui.check_for_updates(None, home=tmp_path)
    assert thread in ui._RUNNING_CHECKS
    release.set()
    ui.wait_for_checks(5000)
    assert thread.isFinished()
    _app.processEvents()  # drain the queued found/finished callbacks


# --------------------------------------------- I4: a live session (main
# window open) must never be torn down by QApplication.quit() from a late
# update prompt.

def test_found_update_stays_silent_once_a_session_window_is_open(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui, "_ask",
                        lambda *a, **k: pytest.fail("prompted while a session was open"))
    win = QMainWindow()
    win.show()
    try:
        thread = ui.check_for_updates(None, home=tmp_path)
        thread.wait(5000)
        _app.processEvents()
    finally:
        win.close()


# ------------------------------------------------- I7: never run two checks
# at once.

def test_second_check_while_one_runs_does_not_start_another_thread(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    release = threading.Event()

    def blocking_find(*a, **k):
        release.wait(5)
        return None

    monkeypatch.setattr(ui.checker, "find_update", blocking_find)
    thread1 = ui.check_for_updates(None, home=tmp_path)
    assert thread1 is not None
    thread2 = ui.check_for_updates(None, home=tmp_path)
    assert thread2 is None
    release.set()
    thread1.wait(5000)
    _app.processEvents()


def test_second_forced_check_while_one_runs_tells_user_and_does_not_start(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    release = threading.Event()

    def blocking_find(*a, **k):
        release.wait(5)
        return None

    monkeypatch.setattr(ui.checker, "find_update", blocking_find)
    informed = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: informed.append(a[2]))
    thread1 = ui.check_for_updates(None, home=tmp_path)
    thread2 = ui.check_for_updates(None, force=True, home=tmp_path)
    assert thread2 is None
    assert informed and "확인 중" in informed[0]
    release.set()
    thread1.wait(5000)
    _app.processEvents()


# ------------------------------------------------------- M4: a dev build
# (force=True) must say so instead of the button silently doing nothing.

def test_forced_check_on_dev_build_tells_the_user(monkeypatch, tmp_path):
    informed = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: informed.append(a[2]))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: pytest.fail("network hit from a dev build"))
    assert ui.check_for_updates(None, force=True, home=tmp_path) is None
    assert informed


# --------------------------------------------------------- M3: each download
# gets its own fresh temp directory (no fixed, predictable path).

def test_prompt_update_uses_a_fresh_temp_dir_each_time(monkeypatch, tmp_path):
    seen_dirs = []

    def fake_download(url, dest, sha256, progress=None, **kw):
        seen_dirs.append(dest.parent)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")

    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer", lambda *a, **k: None)
    ui.prompt_and_install(None, INFO, home=tmp_path)
    ui.prompt_and_install(None, INFO, home=tmp_path)
    assert seen_dirs[0] != seen_dirs[1]
    assert str(seen_dirs[0]).startswith(tempfile.gettempdir())


# ----------------------------------------------------------------- M12: a
# successful update hand-off must quit the app (the installer restarts it).

def test_prompt_and_install_true_quits_the_app(monkeypatch, tmp_path):
    def fake_download(url, dest, sha256, progress=None, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")

    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "lite", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer", lambda *a, **k: None)
    quit_calls = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(True))
    thread = ui.check_for_updates(None, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()
    assert quit_calls == [True]


# ------------------------------------------------------------- M2 / M10: the
# prompt text must be plain (untrusted release body) and must call out the
# full variant's download size.

def test_ask_uses_plain_text_format(monkeypatch):
    captured = {}

    def fake_exec(self):
        captured["format"] = self.textFormat()
        return None

    monkeypatch.setattr(QMessageBox, "exec_", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    ui._ask(None, INFO)
    assert captured["format"] == Qt.PlainText


def test_ask_warns_about_full_variant_download_size(monkeypatch):
    full_info = checker.UpdateInfo(
        version="1.0.1", variant="full",
        asset_name="LabelingTool-full-Setup-v1.0.1.exe",
        asset_url="https://x/s.exe", size=1500 * 1024 * 1024,
        sha256="a" * 64, notes="")
    captured = {}

    def fake_exec(self):
        captured["text"] = self.text()
        return None

    monkeypatch.setattr(QMessageBox, "exec_", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    ui._ask(None, full_info)
    assert "1.5 GB" in captured["text"]
