"""Update prompt: three buttons, progress, and handing over to the installer."""
import threading

import pytest
from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QPushButton, QWidget

from labeling_tool.core import app_paths
from labeling_tool.update import checker, state, ui
from labeling_tool.update.version import BuildInfo

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _cache_in_tmp_path(monkeypatch, tmp_path):
    """Keep downloaded packages out of the real repo cache.

    user_cache_home() falls back to REPO_ROOT/.cache outside a frozen build,
    which is exactly where the dev checkout and the test suite run - without
    this, every download test litters the repository with update-* dirs.
    """
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)


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


# A full update: the Setup exe, downloaded only once the user agrees.
INFO = checker.UpdateInfo(
    version="1.0.1", variant="full",
    assets=(checker.Asset(name="LM_LabelingTool-Setup-v1.0.1.exe",
                          url="https://x/s.exe",
                          size=1500 * 1024 * 1024,
                          sha256="a" * 64),),
    notes="fixes", kind="full")


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


def test_a_successful_linux_install_does_not_quit_the_app(monkeypatch, tmp_path):
    # dpkg already installed the update in place; the user was told to
    # restart manually. Quitting here would be unprompted and could drop
    # unsaved work, contradicting the restart message just shown.
    info = _linux_full_info()

    def fake_download(url, dest, sha, progress=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: info)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file", fake_download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (ui.installer.InstallOutcome.OK, ""))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    quit_calls = []
    monkeypatch.setattr(QApplication, "quit", lambda: quit_calls.append(True))
    thread = ui.check_for_updates(None, home=tmp_path)
    thread.wait(5000)
    _app.processEvents()
    assert quit_calls == []


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
    assert captured["text"] == i18n.tr("update_available", version=INFO.version) \
        + i18n.tr("update_download_size", size=INFO.total_size // (1024 * 1024)) \
        + i18n.tr("update_full_warning")


@pytest.mark.parametrize("lang", ["en", "ko", "zh"])
def test_a_downloaded_zip_prompt_shows_no_download_size(monkeypatch, tmp_path, lang):
    """The zip is already on disk, and a few MB would read "about 0 MB"."""
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    i18n.set_language(lang)
    app_info = checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(checker.Asset(name="LM_LabelingTool-update-v1.0.1-win.zip",
                              url="https://x/u.zip", size=300 * 1024, sha256="a" * 64),),
        notes="", kind="app")
    text = ui.prompt_text(app_info)
    assert text == i18n.tr("update_available", version="1.0.1")
    assert "MB" not in text
    full = ui.prompt_text(INFO)
    assert i18n.tr("update_download_size", size=1500) in full


# ------------------------------------------------- Linux full update: one deb

def _asset(name, size=100 * 1024 * 1024, sha="a" * 64):
    return checker.Asset(name=name, url=f"https://x/{name}", size=size, sha256=sha)


def _linux_full_info():
    return checker.UpdateInfo(
        version="1.0.1", variant="full",
        assets=(_asset("lm-labeling-tool_1.0.1_amd64.deb", 1500 * 1024 * 1024, "b" * 64),),
        notes="fixes", kind="full")


@pytest.fixture
def linux(monkeypatch):
    """Take the Linux branch, and never actually call pkexec."""
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)


def test_the_deb_is_downloaded_verified_and_passed_to_dpkg(linux, monkeypatch, tmp_path):
    got, calls = [], []

    def _download(url, dest, sha, progress=None):
        got.append((dest.name, sha))
        dest.write_bytes(b"deb")

    monkeypatch.setattr(ui.net_download, "download_file", _download)
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda paths, **kw: (calls.append([p.name for p in paths])
                                             or (ui.installer.InstallOutcome.OK, "")))
    monkeypatch.setattr(ui.QMessageBox, "information", staticmethod(lambda *a, **k: None))

    info = _linux_full_info()
    assert ui.prompt_and_install(None, info, home=tmp_path) is True
    assert got == [(info.assets[0].name, info.assets[0].sha256)]
    assert calls == [[info.assets[0].name]]


def test_progress_is_scaled_to_the_download_size(linux, monkeypatch, tmp_path):
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
    assert totals and all(whole_mb in t for t in totals), \
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

    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
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

    assert ui.prompt_and_install(None, _linux_full_info(), home=tmp_path) is False
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


def test_windows_still_hands_over_to_the_installer(monkeypatch, tmp_path):
    # A full update on Windows: the Setup exe takes over and restarts the app.
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


# ------------------------------------------------ app-layer zip: cache, apply

def _zip_info(sha="a" * 64):
    return checker.UpdateInfo(
        version="0.2.1", variant="full", kind="app", notes="- 개선",
        assets=(checker.Asset("update-v0.2.1-r11111111-windows.zip", "https://x/u.zip", 10, sha),))


def test_a_cached_zip_with_the_right_checksum_is_not_downloaded_again(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    data = b"zip bytes"
    info = _zip_info(hashlib.sha256(data).hexdigest())
    path = ui.cached_update_path(info)
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded again")))
    assert ui.ensure_downloaded(info) == path


def test_a_corrupt_cached_zip_is_downloaded_again(tmp_path, monkeypatch):
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    info = _zip_info()
    path = ui.cached_update_path(info)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"half a download")
    calls = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: calls.append(dest) or dest.write_bytes(b"ok"))
    ui.ensure_downloaded(info)
    assert calls == [path]


def test_other_cached_updates_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(ui.app_paths, "user_cache_home", lambda: tmp_path)
    info = _zip_info()
    stale = tmp_path / "updates" / "update-v0.1.9-r11111111-windows.zip"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"ok"))
    ui.ensure_downloaded(info)
    assert not stale.exists()


def test_periodic_checks_start_one_timer(monkeypatch):
    monkeypatch.setattr(ui, "_PERIODIC", [])
    ui.start_periodic_checks(1000)
    ui.start_periodic_checks(1000)
    try:
        assert len(ui._PERIODIC) == 1 and ui._PERIODIC[0].interval() == 1000
        assert ui._PERIODIC[0].isActive()
    finally:
        ui._PERIODIC[0].stop()


@pytest.fixture
def no_restart(monkeypatch):
    """Record the relaunch and the quit instead of doing either."""
    seen = {"popen": [], "quit": []}
    monkeypatch.setattr(ui.subprocess, "Popen",
                        lambda cmd, **kw: seen["popen"].append(cmd))
    monkeypatch.setattr(QApplication, "quit", lambda: seen["quit"].append(True))
    return seen


def test_windows_applies_the_zip_in_process_and_restarts(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    applied = []
    monkeypatch.setattr(ui.patch, "apply_patch",
                        lambda z, root, sha: applied.append((z, root, sha)))
    info = _zip_info()
    assert ui.apply_and_restart(None, info, tmp_path / "u.zip") is True
    assert applied == [(tmp_path / "u.zip", tmp_path, info.assets[0].sha256)]
    assert no_restart["popen"] == [[str(tmp_path / "LM_LabelingTool.exe")]]
    assert no_restart["quit"] == [True]


def test_windows_apply_runs_off_the_ui_thread_behind_the_notice(monkeypatch, tmp_path, no_restart):
    # Windows swapped the files on the UI thread with no window at all: the
    # app looked frozen ("not responding" past ~5 s) until it restarted.
    import time
    from PyQt5.QtCore import QTimer
    from labeling_tool.core import i18n
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    seen = {}

    def slow_patch(z, root, sha):
        seen["thread"] = threading.current_thread()
        time.sleep(0.3)

    def look():
        seen["labels"] = [w.labelText() for w in QApplication.topLevelWidgets()
                          if isinstance(w, ui.QProgressDialog) and w.isVisible()]

    monkeypatch.setattr(ui.patch, "apply_patch", slow_patch)
    QTimer.singleShot(100, look)
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is True
    assert seen["thread"] is not threading.main_thread()
    assert seen["labels"] == [i18n.tr("update_applying")]
    assert no_restart["popen"] == [[str(tmp_path / "LM_LabelingTool.exe")]]


def test_a_failed_windows_apply_keeps_the_old_version_running(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.WINDOWS)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)

    def locked(*a, **k):
        raise ui.patch.PatchError("could not apply the update: file in use")

    monkeypatch.setattr(ui.patch, "apply_patch", locked)
    shown = []
    monkeypatch.setattr(ui.QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is False
    assert shown and "file in use" in shown[0][2]
    assert no_restart == {"popen": [], "quit": []}


def test_linux_applies_the_zip_through_pkexec_and_restarts(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(ui.installer, "apply_zip_linux",
                        lambda exe, z, sha: calls.append((exe, z, sha))
                        or (ui.installer.InstallOutcome.OK, ""))
    info = _zip_info()
    assert ui.apply_and_restart(None, info, tmp_path / "u.zip") is True
    assert calls == [(tmp_path / "LM_LabelingTool", tmp_path / "u.zip", info.assets[0].sha256)]
    assert no_restart["popen"] == [[str(tmp_path / "LM_LabelingTool")]]


def test_linux_cancelled_apply_is_silent(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.installer, "apply_zip_linux",
                        lambda *a: (ui.installer.InstallOutcome.CANCELLED, ""))
    monkeypatch.setattr(ui.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: pytest.fail("cancel reported")))
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is False
    assert no_restart["popen"] == []


def test_linux_failed_apply_is_reported(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.installer, "apply_zip_linux",
                        lambda *a: (ui.installer.InstallOutcome.FAILED, "update failed: runtime mismatch"))
    shown = []
    monkeypatch.setattr(ui.QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is False
    assert "runtime mismatch" in shown[0][2]
    assert no_restart["popen"] == []


def test_linux_apply_waits_off_the_ui_thread_so_the_window_stays_responsive(
        monkeypatch, tmp_path, no_restart):
    # pkexec (password prompt + the root-run swap) takes several seconds; run
    # on the UI thread it froze the window long enough for GNOME's 5 s
    # check-alive to offer "Force Quit".
    import time
    from PyQt5.QtCore import QTimer
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    seen = {}
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)

    def slow_apply(exe, z, sha):
        seen["thread"] = threading.current_thread()
        time.sleep(0.3)
        return ui.installer.InstallOutcome.OK, ""

    monkeypatch.setattr(ui.installer, "apply_zip_linux", slow_apply)
    try:
        assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is True
    finally:
        timer.stop()
    assert seen["thread"] is not threading.main_thread()
    assert len(ticks) >= 5                 # the event loop ran while waiting
    assert no_restart["popen"] == [[str(tmp_path / "LM_LabelingTool")]]


def _visible_notices():
    return [w for w in QApplication.topLevelWidgets()
            if isinstance(w, ui.QProgressDialog) and w.isVisible()]


def _slow_ok(seconds=0.4):
    import time

    def apply(exe, z, sha):
        time.sleep(seconds)
        return ui.installer.InstallOutcome.OK, ""
    return apply


def test_linux_apply_shows_a_busy_notice_while_waiting(monkeypatch, tmp_path, no_restart):
    from PyQt5.QtCore import QTimer
    from labeling_tool.core import i18n
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    monkeypatch.setattr(ui.installer, "apply_zip_linux", _slow_ok())
    seen = {}

    def look():                            # on the UI thread, mid-wait
        bars = _visible_notices()
        seen["labels"] = [b.labelText() for b in bars]
        seen["cancel"] = [b.findChildren(QPushButton) for b in bars]

    QTimer.singleShot(100, look)
    ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip")
    assert seen["labels"] == [i18n.tr("update_applying")]
    assert seen["cancel"] == [[]]          # nothing to cancel: pkexec owns it now
    assert _visible_notices() == []


def test_the_busy_notice_cannot_be_dismissed(monkeypatch, tmp_path, no_restart):
    # Esc or the window manager's close would drop the modality while the
    # root swap still runs, and the app would quit under the user.
    from PyQt5.QtCore import QTimer
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    monkeypatch.setattr(ui.installer, "apply_zip_linux", _slow_ok())
    seen = {}

    def dismiss():
        for bar in _visible_notices():
            bar.reject()                   # what Esc does
            bar.close()                    # what the window's close button does
        seen["after"] = len(_visible_notices())
        seen["modal"] = QApplication.activeModalWidget() is not None

    QTimer.singleShot(100, dismiss)
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is True
    assert seen == {"after": 1, "modal": True}
    assert _visible_notices() == []


def test_a_quit_request_while_waiting_does_not_freeze_the_window(monkeypatch, tmp_path, no_restart):
    import time
    from PyQt5.QtCore import QCoreApplication, QTimer
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)
    monkeypatch.setattr(ui.app_paths, "app_home", lambda: tmp_path)
    monkeypatch.setattr(ui.installer, "apply_zip_linux", _slow_ok(0.6))
    late_ticks = []
    timer = QTimer()
    start = time.monotonic()
    timer.timeout.connect(lambda: time.monotonic() - start > 0.3 and late_ticks.append(1))
    timer.start(10)
    QTimer.singleShot(100, QCoreApplication.quit)   # e.g. session logout
    try:
        assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is True
    finally:
        timer.stop()
        # quit() leaves Qt's quitNow flag set, which makes every later
        # QEventLoop.exec() return at once; QApplication.exec_() clears it.
        QTimer.singleShot(0, QCoreApplication.quit)
        QApplication.exec_()
    assert len(late_ticks) >= 5


def test_linux_apply_unexpected_error_is_reported_not_raised(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)

    def broken(*a):
        raise RuntimeError("weird")

    monkeypatch.setattr(ui.installer, "apply_zip_linux", broken)
    shown = []
    monkeypatch.setattr(ui.QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is False
    assert shown and "weird" in shown[0][2]
    assert no_restart["popen"] == []


def test_linux_apply_os_error_in_the_worker_is_reported(monkeypatch, tmp_path, no_restart):
    monkeypatch.setattr(ui.checker, "current_platform", lambda: ui.checker.LINUX)

    def broken(*a):
        raise FileNotFoundError("u.zip")

    monkeypatch.setattr(ui.installer, "apply_zip_linux", broken)
    shown = []
    monkeypatch.setattr(ui.QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a)))
    assert ui.apply_and_restart(None, _zip_info(), tmp_path / "u.zip") is False
    assert shown and "u.zip" in shown[0][2]
    assert no_restart["popen"] == []


def test_accepting_a_zip_update_downloads_then_applies(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"zip"))
    applied = []
    monkeypatch.setattr(ui, "apply_and_restart",
                        lambda parent, info, z: applied.append(z) or True)
    monkeypatch.setattr(ui.installer, "launch_installer",
                        lambda *a, **k: pytest.fail("a zip went to the Setup hand-off"))
    monkeypatch.setattr(ui.installer, "install_debs",
                        lambda *a, **k: pytest.fail("a zip went to dpkg"))
    info = _zip_info()
    assert ui.prompt_and_install(None, info, home=tmp_path) is True
    assert applied == [ui.cached_update_path(info)]


def test_a_cached_zip_update_shows_no_download_progress(monkeypatch, tmp_path):
    import hashlib
    data = b"zip"
    info = _zip_info(hashlib.sha256(data).hexdigest())
    path = ui.cached_update_path(info)
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    monkeypatch.setattr(ui, "_ask", lambda *a, **k: ui.UPDATE)
    monkeypatch.setattr(ui, "QProgressDialog",
                        lambda *a, **k: pytest.fail("progress shown for a cached zip"))
    monkeypatch.setattr(ui, "apply_and_restart", lambda parent, info, z: True)
    assert ui.prompt_and_install(None, info, home=tmp_path) is True


def test_ask_offers_a_restart_for_a_zip_and_shows_every_note_line(monkeypatch):
    from labeling_tool.core import i18n
    notes = "\n".join(f"- change {n}" for n in range(12))
    info = checker.UpdateInfo(version="0.2.1", variant="full", kind="app", notes=notes,
                              assets=_zip_info().assets)
    captured = {}

    def fake_exec(self):
        captured["informative"] = self.informativeText()
        captured["buttons"] = [b.text() for b in self.buttons()]

    monkeypatch.setattr(QMessageBox, "exec_", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    ui._ask(None, info)
    assert captured["informative"] == i18n.tr("update_ready_informative", notes=notes)
    assert i18n.tr("update_btn_restart") in captured["buttons"]


def _found_zip(monkeypatch, info):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("0.2.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: info)


def _settle():
    """Run every check/download thread to completion and deliver its signals."""
    for _ in range(3):
        ui.wait_for_checks(5000)
        _app.processEvents()


def test_a_found_zip_is_downloaded_in_the_background_then_offered(monkeypatch, tmp_path):
    info = _zip_info()
    _found_zip(monkeypatch, info)
    order = []
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: order.append("download")
                        or dest.write_bytes(b"zip"))
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda parent, found, home=None: order.append("prompt") or False)
    ui.check_for_updates(None, home=tmp_path)
    _settle()
    assert order == ["download", "prompt"]


def test_a_zip_ready_mid_session_waits_and_says_so_in_the_status_bar(monkeypatch, tmp_path):
    from labeling_tool.core import i18n
    info = _zip_info()
    _found_zip(monkeypatch, info)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda url, dest, sha, progress=None: dest.write_bytes(b"zip"))
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda *a, **k: pytest.fail("prompted mid-session"))
    win = QMainWindow()
    win.show()
    try:
        ui.check_for_updates(None, home=tmp_path)
        _settle()
        message = win.statusBar().currentMessage()
    finally:
        win.close()
    assert ui._PENDING == [(info, tmp_path)]
    assert message == i18n.tr("update_ready_status", version=info.version)


def test_a_failed_background_download_is_silent(monkeypatch, tmp_path):
    _found_zip(monkeypatch, _zip_info())

    def offline(*a, **k):
        raise OSError("network unreachable")

    monkeypatch.setattr(ui.net_download, "download_file", offline)
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda *a, **k: pytest.fail("prompted without a download"))
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(ui.QMessageBox, name,
                            staticmethod(lambda *a, **k: pytest.fail("a box was shown")))
    ui.check_for_updates(None, home=tmp_path)
    _settle()
    assert ui._PENDING == []
    assert not ui._RUNNING_CHECKS


def test_a_full_update_is_not_downloaded_before_the_user_agrees(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "read_build_info", lambda: BuildInfo("1.0.0", "full", None))
    monkeypatch.setattr(ui.checker, "find_update", lambda *a, **k: INFO)
    monkeypatch.setattr(ui.net_download, "download_file",
                        lambda *a, **k: pytest.fail("a 1.5 GB download started unasked"))
    asked = []
    monkeypatch.setattr(ui, "prompt_and_install",
                        lambda parent, found, home=None: asked.append(found) or False)
    ui.check_for_updates(None, home=tmp_path)
    _settle()
    assert asked == [INFO]


def test_shutdown_cancels_a_download_still_running(monkeypatch, tmp_path):
    # A QThread still running when the process exits aborts it.
    started = threading.Event()

    def endless(url, dest, sha, progress=None):
        started.set()
        while progress(1, 0) is not False:
            threading.Event().wait(0.01)
        raise ui.net_download.DownloadCancelled()

    monkeypatch.setattr(ui.net_download, "download_file", endless)
    thread = ui.UpdateDownloadThread(_zip_info())
    ui._RUNNING_CHECKS.add(thread)
    try:
        thread.start()
        assert started.wait(5)
        ui.wait_for_checks(50)
        assert thread.isFinished()
    finally:
        ui._RUNNING_CHECKS.discard(thread)
        _app.processEvents()


def test_a_periodic_check_is_skipped_while_a_prompt_is_open(monkeypatch):
    checks = []
    monkeypatch.setattr(ui, "check_for_updates", lambda parent: checks.append(parent))
    monkeypatch.setattr(ui, "_PROMPTING", [True])
    ui._periodic_check()
    assert checks == []
    monkeypatch.setattr(ui, "_PROMPTING", [])
    ui._periodic_check()
    assert checks == [None]


def test_notes_shown_in_the_dialog_drop_markdown_markers():
    """The dialog is plain text, so the release notes' Markdown would show
    literally ("## 주요 변경 사항"); headings and bold lose their markers,
    list dashes stay."""
    notes = "## 주요 변경 사항\n\n- **설치** 파일 통합\n- 버전 0.x\n\n### 안내\n- 재설치"
    assert ui.plain_notes(notes) == "주요 변경 사항\n\n- 설치 파일 통합\n- 버전 0.x\n\n안내\n- 재설치"


def test_the_prompt_shows_the_notes_without_markdown(monkeypatch, tmp_path):
    from dataclasses import replace
    from labeling_tool.core import i18n
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path)
    captured = {}
    monkeypatch.setattr(ui.QMessageBox, "exec_", lambda self: captured.setdefault("info", self.informativeText()))
    monkeypatch.setattr(ui.QMessageBox, "clickedButton", lambda self: None)
    ui._ask(None, replace(INFO, notes="## 주요 변경 사항\n\n- 개선"))
    assert "##" not in captured["info"]
    assert "주요 변경 사항" in captured["info"]
