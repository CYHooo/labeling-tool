"""Update prompt: three buttons, progress, and handing over to the installer."""
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
    ui._PENDING.clear()
    yield
    ui._PENDING.clear()
    orig_info, orig_crit = QMessageBox.information, QMessageBox.critical
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)
    try:
        _app.processEvents()
    finally:
        QMessageBox.information = orig_info
        QMessageBox.critical = orig_crit


INFO = checker.UpdateInfo(
    version="1.0.1", variant="lite",
    assets=(checker.Asset(name="LabelingTool-lite-Setup-v1.0.1.exe",
                          url="https://x/s.exe",
                          size=170 * 1024 * 1024,
                          sha256="a" * 64),),
    notes="fixes", kind="app")


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

    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda path, log, **kw: seen.setdefault("launched", path))
    assert ui.prompt_and_install(None, INFO, home=tmp_path) is True
    assert seen["download"] == (INFO.assets[0].url, INFO.assets[0].sha256)
    assert seen["launched"].name == INFO.assets[0].name


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


def test_every_launch_checks_even_right_after_a_check(monkeypatch, tmp_path):
    """No throttle: a release published an hour after the day's first launch
    must be offered on the next launch, not the next day."""
    from labeling_tool.update.version import BuildInfo
    calls = []
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: calls.append(a) or None)
    state.mark_checked(tmp_path)
    thread = ui.check_for_updates(None, home=tmp_path)
    assert thread is not None
    thread.wait(5000)
    assert calls


def test_an_unforced_check_still_honours_a_skipped_version(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: pytest.fail("offered a skipped version"))
    state.skip_version(INFO.version, tmp_path)
    ui.check_for_updates(None, home=tmp_path).wait(5000)
    _app.processEvents()
    assert not ui._PENDING


def test_forced_check_ignores_throttle_and_skip(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    calls = []
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: calls.append(a) or None)
    state.mark_checked(tmp_path)
    state.skip_version("1.0.1", tmp_path)
    thread = ui.check_for_updates(None, force=True, home=tmp_path)
    thread.wait(5000)
    assert calls


def test_running_check_is_retained_then_released(monkeypatch, tmp_path):
    from labeling_tool.update.version import BuildInfo
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.LATER)
    thread = ui.check_for_updates(parent, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()  # runs _on_found (and _on_finished) against the dead parent


# --------------------------------------------------------------- C2: a failed
# check must never be reported as "up to date", and must only surface at all
# when the user explicitly asked (force=True).

def test_forced_failed_check_warns_instead_of_lying(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    # ... but it is not dropped: it waits for the session to end.
    assert ui._PENDING and ui._PENDING[0][0] is INFO


def test_update_found_mid_session_is_offered_when_the_session_ends(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    offered = []
    win = QMainWindow()
    win.show()
    try:
        monkeypatch.setattr(ui, "_ask", lambda *a, **k: pytest.fail("prompted mid-session"))
        ui.check_for_updates(None, home=tmp_path).wait(5000)
        _app.processEvents()
    finally:
        win.close()
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda parent, info, home=None: offered.append((info, home)) or True)
    assert ui.prompt_pending_update() is True
    assert offered == [(INFO, tmp_path)]
    assert not ui._PENDING, "offered once, then forgotten"
    assert ui.prompt_pending_update() is False


def test_a_result_still_in_flight_when_the_session_ends_is_delivered(monkeypatch, tmp_path):
    """The found signal is queued to the main thread; after app.exec_()
    returns nothing pumps it unless prompt_pending_update() does."""
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    release = threading.Event()
    monkeypatch.setattr(ui.checker, "find_update",
                        lambda *a, **k: release.wait(5) and INFO)
    asked = []
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda parent, info, home=None: asked.append(info) or False)
    ui.check_for_updates(None, home=tmp_path)
    release.set()
    ui.prompt_pending_update()     # no window open: the result prompts directly
    assert asked == [INFO]


def test_nothing_pending_means_no_prompt(monkeypatch):
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda *a, **k: pytest.fail("prompted with nothing pending"))
    assert ui.prompt_pending_update() is False


# ------------------------------------------------- I7: never run two checks
# at once.

def test_second_check_while_one_runs_does_not_start_another_thread(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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

    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "launch_installer", lambda *a, **k: None)
    ui.prompt_and_install(None, INFO, home=tmp_path)
    ui.prompt_and_install(None, INFO, home=tmp_path)
    assert seen_dirs[0] != seen_dirs[1]
    from labeling_tool.core import app_paths
    assert str(seen_dirs[0]).startswith(str(app_paths.user_cache_home()))


# ----------------------------------------------------------------- M12: a
# successful update hand-off must quit the app (the installer restarts it).

def test_prompt_and_install_true_quits_the_app(monkeypatch, tmp_path):
    def fake_download(url, dest, sha256, progress=None, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")

    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
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


def test_ask_warns_when_a_full_reinstall_is_needed(monkeypatch):
    """kind == "full" means the runtime layer changed, so the whole 1.5 GB
    installer has to come down. The prompt says why."""
    full_info = checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(checker.Asset(name="LM_LabelingTool-Setup-v1.0.1.exe",
                              url="https://x/s.exe",
                              size=1500 * 1024 * 1024,
                              sha256="a" * 64),),
        notes="", kind="full")
    captured = {}

    def fake_exec(self):
        captured["text"] = self.text()
        return None

    monkeypatch.setattr(QMessageBox, "exec_", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    ui._ask(None, full_info)
    from labeling_tool.core import i18n
    assert i18n.tr("update_full_warning") in captured["text"]


# ------------------------------------------------------- i18n: the prompt
# text must come from tr(), so it follows the active language.

def test_prompt_text_follows_language(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    captured = {}
    monkeypatch.setattr(ui.QMessageBox, "exec_", lambda self: captured.setdefault("text", self.text()))
    monkeypatch.setattr(ui.QMessageBox, "clickedButton", lambda self: None)
    i18n.set_language("en")
    ui._ask(None, INFO)
    assert captured["text"] == i18n.tr("update_available", version=INFO.version,
                                       size=INFO.total_size // (1024 * 1024))


# ---------------------------------------------- Task 7: multi-asset download

def _asset(name, size=100 * 1024 * 1024, sha="a" * 64):
    return checker.Asset(name=name, url=f"https://x/{name}", size=size, sha256=sha)


def _linux_full_info():
    return checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(_asset("lm-labeling-tool-runtime_1.0.1_amd64.deb", 700 * 1024 * 1024,
                       "b" * 64),
                _asset("lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", 20 * 1024 * 1024,
                       "c" * 64)),
        notes="fixes", kind="full")


def _linux_app_info():
    return checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(_asset("lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", 20 * 1024 * 1024),),
        notes="fixes", kind="app")


@pytest.fixture
def linux(monkeypatch):
    """Take the Linux branch, and never actually call pkexec."""
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)


def test_every_asset_is_downloaded_and_verified(linux, monkeypatch, tmp_path):
    # A Linux full update is two debs; downloading only the first would hand
    # dpkg half an install.
    got = []

    def _download(url, dest, sha, progress=None):
        got.append((dest.name, sha))
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.OK, ""))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    info = _linux_full_info()
    assert ui.prompt_and_install(None, info, home=tmp_path) is True
    assert [name for name, _ in got] == [a.name for a in info.assets]
    assert [sha for _, sha in got] == [a.sha256 for a in info.assets]


def test_both_debs_are_passed_to_dpkg_in_one_call(linux, monkeypatch, tmp_path):
    # dpkg must see both packages at once, or the app deb's Depends on the
    # runtime deb cannot be satisfied.
    calls = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (calls.append(list(paths))
                                             or (ui.installer.InstallOutcome.OK, "")))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    ui.prompt_and_install(None, _linux_full_info(), home=tmp_path)
    assert len(calls) == 1 and len(calls[0]) == 2


def test_progress_spans_the_total_of_all_assets(linux, monkeypatch, tmp_path):
    # Two debs must not each drive the bar from 0 to 100.
    totals = []

    def _download(url, dest, sha, progress=None):
        dest.write_bytes(b"deb")
        if progress is not None:
            progress(1024, 0)

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.OK, ""))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ui.QProgressDialog, "setLabelText",
                        lambda self, text: totals.append(text))

    info = _linux_full_info()
    ui.prompt_and_install(None, info, home=tmp_path)
    whole_mb = str(info.total_size // (1024 * 1024))
    assert all(whole_mb in t for t in totals), \
        f"the bar must be scaled to {whole_mb} MB, saw {totals}"


def test_cancelled_install_is_silent(linux, monkeypatch, tmp_path):
    # Dismissing the polkit dialog is not an error.
    boxes = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.CANCELLED, ""))
    monkeypatch.setattr(ui.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    monkeypatch.setattr(ui.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: boxes.append(a)))

    assert ui.prompt_and_install(None, _linux_app_info(), home=tmp_path) is False
    assert boxes == []


def test_missing_deps_names_the_apt_command(linux, monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"deb"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.MISSING_DEPS,
                                             "dpkg: dependency problems ... libxcb-xinerama0"))
    monkeypatch.setattr(ui.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: shown.append(a)))

    assert ui.prompt_and_install(None, _linux_app_info(), home=tmp_path) is False
    assert shown, "the user must be told which apt command fixes this"
    assert any("apt-get install -f" in str(arg) for arg in shown[0])


def test_a_failed_download_installs_nothing(linux, monkeypatch, tmp_path):
    # ~/.cache full or unwritable: report it, install nothing, keep the app
    # usable. Installing a partially downloaded deb would be worse.
    installs = []
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: installs.append(paths))
    monkeypatch.setattr(ui.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    def _boom(url, dest, sha, progress=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ui.net_download, "download_file", _boom)
    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
    assert installs == []


def test_a_failure_on_the_second_deb_installs_nothing(linux, monkeypatch, tmp_path):
    # The first deb downloaded fine. Installing it alone would leave a
    # runtime layer with no application on top of it.
    installs = []
    seen = []

    def _download(url, dest, sha, progress=None):
        seen.append(dest.name)
        if len(seen) == 2:
            raise OSError(28, "No space left on device")
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: installs.append(paths))
    monkeypatch.setattr(ui.QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
    assert installs == []


def test_windows_still_hands_over_to_the_installer(monkeypatch, tmp_path):
    # The Windows path must be untouched by the list refactor.
    launched = []
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"exe"))
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda dest, log: launched.append(dest))

    assert ui.prompt_and_install(None, INFO, home=tmp_path) is True
    assert len(launched) == 1
    assert launched[0].name == INFO.assets[0].name
