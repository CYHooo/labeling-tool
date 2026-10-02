"""Qt front end for the updater: background check, prompt, download, hand-off.

Two kinds of update (checker.UpdateInfo.kind):
  * "app"  -- a zip of our own code, a few MB. Downloaded in the background
              into a verified cache as soon as it is found, then offered;
              accepting applies it (patch.apply_patch) and restarts.
  * "full" -- the Setup exe / the deb, 1.5 GB or more, needed when the
              runtime layer changed. Downloaded only once the user agrees,
              then handed to the installer.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import threading
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QProgressDialog,
)

from labeling_tool.core import app_paths, net_download
from labeling_tool.core.i18n import tr
from labeling_tool.logging_setup import vlog
from labeling_tool.update import checker, installer, patch, state
from labeling_tool.update.version import read_build_info

UPDATE, LATER, SKIP = "update", "later", "skip"

# Threads started by check_for_updates() need an owner independent of what
# the caller does with the returned value (app.py's startup check discards
# it entirely) - otherwise CPython can drop the last reference to a running
# QThread and Qt aborts with "QThread: Destroyed while thread is still
# running". Every thread we start is kept here until its `finished` signal
# fires, then it is released and scheduled for deletion.
_RUNNING_CHECKS: set[QThread] = set()

# An update found while a session window was open. Prompting then would mean
# quitting under the user's unsaved work, so it waits here until the session
# ends and prompt_pending_update() offers it. (update info, state home)
_PENDING: list[tuple[object, Path | None]] = []

# The one periodic-check QTimer, kept alive for the app's lifetime.
_PERIODIC: list = []

# True while an update prompt (or its download / apply) is on screen, so a
# periodic check firing inside that modal loop does not stack a second one.
_PROMPTING: list[bool] = []

_MB = 1024 * 1024


class UpdateCheckThread(QThread):
    """Look for an update off the UI thread; emits UpdateInfo, None, or the
    exception that made the check fail (the caller decides whether a failure
    is worth reporting - see check_for_updates._on_found)."""
    found = pyqtSignal(object)

    # Bounds the worst case of a hung proxy / dead network so
    # wait_for_checks() at shutdown has a predictable ceiling.
    CHECK_TIMEOUT = 5

    def __init__(self, current_version: str, variant: str,
                 runtime: str | None = None, parent=None):
        super().__init__(parent)
        self._version, self._variant = current_version, variant
        self._runtime = runtime

    def run(self):
        try:
            self.found.emit(checker.find_update(
                self._version, self._variant, timeout=self.CHECK_TIMEOUT,
                runtime=self._runtime))
        except Exception as exc:  # noqa: BLE001 - reporting is the caller's call
            vlog().info("update check failed: %s: %s", type(exc).__name__, exc)
            self.found.emit(exc)


class UpdateDownloadThread(QThread):
    """Fetch an app-layer zip into the cache off the UI thread; emits the
    zip's path, or the exception that stopped it (logged here: a failed
    background download is never shown, the next check retries)."""
    done = pyqtSignal(object)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Stop at the next downloaded chunk (see wait_for_checks)."""
        self._cancelled.set()

    def run(self):
        try:
            self.done.emit(ensure_downloaded(
                self.info, progress=lambda done, total: not self._cancelled.is_set()))
        except Exception as exc:  # noqa: BLE001 - network / disk / checksum
            vlog().info("update download failed: %s: %s", type(exc).__name__, exc)
            self.done.emit(exc)


def wait_for_checks(msec: int = 3000) -> None:
    """Block until every running check/download thread finishes (or the
    timeout hits).

    Call this before the process exits: dropping the last reference to a
    QThread that is still running aborts with "QThread: Destroyed while
    thread is still running". A download still running after `msec` is
    cancelled and waited for once more; the zip is fetched again next time.
    """
    for thread in list(_RUNNING_CHECKS):
        if not thread.wait(msec) and isinstance(thread, UpdateDownloadThread):
            thread.cancel()
            thread.wait(msec)


def prompt_pending_update() -> bool:
    """Offer an update that was found while a session was open.

    Call once the session's event loop has returned -- its window closed
    through closeEvent, so the work is saved. Also finishes a check that is
    still in flight: its result is a queued signal, and with no event loop
    running it would otherwise never be delivered. True = installer started.
    """
    wait_for_checks()
    QApplication.processEvents()
    if not _PENDING:
        return False
    found, home = _PENDING.pop()
    _PENDING.clear()
    return prompt_and_install(None, found, home)


def _session_in_progress() -> bool:
    """True once a labeling/few-shot main window is open.

    The login dialog is a QDialog; ViewerMainWindow and the few-shot tool's
    MainWindow are both QMainWindow subclasses. Used to avoid prompting to
    install (and therefore calling QApplication.quit()) once the user has an
    active session with unsaved work, even if the found signal arrives late.
    """
    app = QApplication.instance()
    if app is None:
        return False
    return any(isinstance(w, QMainWindow) and w.isVisible()
              for w in app.topLevelWidgets())


def prompt_text(info) -> str:
    """The body of the update prompt.

    Extracted from _ask so it can be tested without building a QMessageBox
    (a modal box under offscreen Qt hangs the suite). The warning hangs off
    `kind`, not the variant: a full reinstall is needed when the runtime
    layer changed, which is what kind == "full" means."""
    size_mb = info.total_size // (1024 * 1024)
    text = tr("update_available", version=info.version, size=size_mb)
    if info.kind == "full":
        text += tr("update_full_warning")
    return text


def _ask(parent, info) -> str:
    """The three-button prompt; returns UPDATE / LATER / SKIP.

    The notes are shown whole: checker.extract_notes already cut the
    release body down to its change-notes section."""
    if info.kind == "app":
        # Already downloaded and verified: accepting just restarts.
        informative = tr("update_ready_informative", notes=info.notes)
        update_label = tr("update_btn_restart")
    else:
        informative = tr("update_informative", notes=info.notes)
        update_label = tr("update_btn_update")
    box = QMessageBox(parent)
    box.setWindowTitle(tr("update_title"))
    box.setIcon(QMessageBox.Information)
    # A release body is untrusted remote text: PlainText keeps AutoText from
    # rendering it as rich text (which could otherwise fetch remote images).
    box.setTextFormat(Qt.PlainText)
    box.setText(prompt_text(info))
    box.setInformativeText(informative)
    btn_update = box.addButton(update_label, QMessageBox.AcceptRole)
    box.addButton(tr("update_btn_later"), QMessageBox.RejectRole)
    btn_skip = box.addButton(tr("update_btn_skip"), QMessageBox.DestructiveRole)
    box.exec_()
    if box.clickedButton() is btn_update:
        return UPDATE
    return SKIP if box.clickedButton() is btn_skip else LATER


def prompt_and_install(parent, info, home: Path | None = None) -> bool:
    """Ask, then apply the zip / download + hand over the full installer.
    True = the update is under way (or done)."""
    _PROMPTING.append(True)
    try:
        choice = _ask(parent, info)
        if choice == SKIP:
            state.skip_version(info.version, home)
            return False
        if choice != UPDATE:
            # "Later" keeps a downloaded zip in the cache for next time.
            return False
        if info.kind == "app":
            return _install_zip(parent, info)
        return _install_full(parent, info)
    finally:
        _PROMPTING.pop()


def _progress_dialog(parent) -> QProgressDialog:
    bar = QProgressDialog(tr("update_progress_label"), tr("update_cancel"), 0, 100, parent)
    bar.setWindowTitle(tr("update_title"))
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)
    return bar


def _progress_callback(bar: QProgressDialog, total_size: int):
    def on_progress(done, total):
        bar.setValue(min(100, done * 100 // max(1, total_size)))
        bar.setLabelText(tr("update_progress_template",
                            done=done // _MB, total=total_size // _MB))
        QApplication.processEvents()
        return not bar.wasCanceled()
    return on_progress


def _report_failure(parent, kind: str, exc) -> None:
    QMessageBox.critical(parent, tr("update_failed_title"),
                         tr("update_failed_msg", type=kind, exc=exc,
                            url=f"https://github.com/{checker.GITHUB_REPO}/releases/latest"))


def _install_zip(parent, info) -> bool:
    """Make sure the zip is in the cache (normally the background download
    already put it there, so no progress shows), then apply it."""
    bar = None if _is_cached(info) else _progress_dialog(parent)
    try:
        zip_path = ensure_downloaded(
            info, progress=None if bar is None else _progress_callback(bar, info.total_size))
    except net_download.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum
        vlog().exception("update download failed")
        _report_failure(parent, type(exc).__name__, exc)
        return False
    finally:
        if bar is not None:
            bar.close()
    return apply_and_restart(parent, info, zip_path)


def _install_full(parent, info) -> bool:
    """Download the full installer, verify it and hand over."""
    # A fresh directory per download avoids the TOCTOU on a fixed,
    # user-writable path and stops packages (1.5 GB or more) accumulating
    # forever under a single well-known name.
    cache_root = app_paths.user_cache_home()
    cache_root.mkdir(parents=True, exist_ok=True)
    target_dir = Path(tempfile.mkdtemp(prefix="update-", dir=cache_root))
    bar = _progress_dialog(parent)
    try:
        asset = info.assets[0]
        dest = target_dir / asset.name
        net_download.download_file(asset.url, dest, asset.sha256,
                                   progress=_progress_callback(bar, info.total_size))
        return _hand_over(parent, info, [dest], target_dir)
    except net_download.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum / launch
        vlog().exception("update failed")
        _report_failure(parent, type(exc).__name__, exc)
        return False
    finally:
        bar.close()


def _hand_over(parent, info, paths, target_dir) -> bool:
    """Install what was downloaded. True = the update is under way."""
    if checker.current_platform() == checker.WINDOWS:
        # Windows cannot replace a running exe: hand over and exit.
        installer.launch_installer(paths[0], target_dir / "update.log")
        return True
    outcome, detail = installer.install_debs(paths)
    if outcome is installer.InstallOutcome.OK:
        QMessageBox.information(parent, tr("update_linux_restart_title"),
                                tr("update_linux_restart_msg"))
        return True
    if outcome is installer.InstallOutcome.CANCELLED:
        # The user dismissed the polkit dialog. Not an error.
        return False
    if outcome is installer.InstallOutcome.MISSING_DEPS:
        QMessageBox.warning(parent, tr("update_linux_deps_title"),
                            tr("update_linux_deps_msg", detail=detail))
        return False
    _report_failure(parent, "dpkg", detail)
    return False


# -- app-layer zip: cache, apply, restart -------------------------------------

def cached_update_path(info) -> Path:
    return app_paths.user_cache_home() / "updates" / info.assets[0].name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_cached(info) -> bool:
    path = cached_update_path(info)
    return path.is_file() and _sha256(path) == info.assets[0].sha256


def ensure_downloaded(info, progress=None) -> Path:
    """The verified update file, from the cache when it is already there.

    A partial or tampered cache entry is downloaded again; other cached
    updates (older versions, a stale .part) are removed."""
    path = cached_update_path(info)
    path.parent.mkdir(parents=True, exist_ok=True)
    for other in path.parent.iterdir():
        if other != path and other.is_file():
            other.unlink(missing_ok=True)
    if _is_cached(info):
        return path
    path.unlink(missing_ok=True)
    asset = info.assets[0]
    net_download.download_file(asset.url, path, asset.sha256, progress=progress)
    return path


def _installed_exe() -> Path:
    name = ("LM_LabelingTool.exe" if checker.current_platform() == checker.WINDOWS
            else "LM_LabelingTool")
    return app_paths.app_home() / name


def apply_and_restart(parent, info, zip_path: Path) -> bool:
    """Apply a downloaded zip and relaunch. False = still on the old version.

    Windows: the install dir is user-writable, so this process swaps the
    files itself (a running exe can be renamed into the backup). Linux:
    /opt is root-owned, so the installed app does it as root via pkexec.
    Never raises: this runs inside Qt slots, where an exception aborts."""
    sha = info.assets[0].sha256
    exe = _installed_exe()
    if checker.current_platform() == checker.WINDOWS:
        try:
            patch.apply_patch(zip_path, app_paths.app_home(), sha)
        except Exception as exc:  # noqa: BLE001 - PatchError, a locked file, ...
            vlog().exception("update apply failed")
            QMessageBox.warning(parent, tr("update_failed_title"),
                                tr("update_apply_failed_msg", exc=exc))
            return False
    else:
        try:
            outcome, detail = installer.apply_zip_linux(exe, zip_path, sha)
        except OSError as exc:
            outcome, detail = installer.InstallOutcome.FAILED, str(exc)
        if outcome is installer.InstallOutcome.CANCELLED:
            return False  # the user dismissed the password dialog
        if outcome is not installer.InstallOutcome.OK:
            vlog().info("update apply failed: %s", detail)
            QMessageBox.warning(parent, tr("update_failed_title"),
                                tr("update_apply_failed_msg", exc=detail))
            return False
    try:
        subprocess.Popen([str(exe)], **installer.launch_and_exit_args())
    except OSError:
        # The update is in place; only the relaunch failed.
        vlog().exception("relaunch after update failed")
        QMessageBox.information(parent, tr("update_linux_restart_title"),
                                tr("update_linux_restart_msg"))
    QApplication.quit()
    return True


def _live(parent):
    """`parent`, or None once its C++ object is gone (see _on_found)."""
    if parent is not None and sip.isdeleted(parent):
        return None
    return parent


def _show_ready_status(version: str) -> None:
    for widget in QApplication.instance().topLevelWidgets():
        if isinstance(widget, QMainWindow) and widget.isVisible():
            widget.statusBar().showMessage(tr("update_ready_status", version=version))


def _offer(parent, found, home) -> None:
    """Prompt now, or hold the update until the session ends."""
    if _session_in_progress():
        # A session with unsaved work is already open. Quitting via
        # QApplication.quit() would bypass ViewerMainWindow.closeEvent
        # and lose it, so hold the update until the session ends:
        # app.py calls prompt_pending_update() after its window closes.
        vlog().info("update %s found mid-session; offering it on exit", found.version)
        _PENDING[:] = [(found, home)]
        if found.kind == "app":
            _show_ready_status(found.version)
        return
    if prompt_and_install(parent, found, home) and checker.current_platform() == checker.WINDOWS:
        # Windows: the installer (or the restarted app) replaces this
        # process, so quit now. Linux: a deb was installed in place and the
        # user was told to restart; a zip already restarted the app.
        QApplication.quit()


def _download_then_offer(parent, found, home, force: bool) -> None:
    """Download an app-layer zip in the background, then _offer it.

    A failed download stays silent (logged by the thread) unless the user
    asked for this check. The thread is owned by _RUNNING_CHECKS exactly
    like a check thread, so wait_for_checks() covers it at shutdown."""
    thread = UpdateDownloadThread(found)

    def _on_done(result):
        if isinstance(result, Exception):
            if force:
                _report_failure(_live(parent), type(result).__name__, result)
            return
        _offer(_live(parent), found, home)

    def _on_finished():
        _RUNNING_CHECKS.discard(thread)
        thread.deleteLater()

    thread.done.connect(_on_done)
    thread.finished.connect(_on_finished)
    _RUNNING_CHECKS.add(thread)
    thread.start()


def check_for_updates(parent, *, force: bool = False, home: Path | None = None):
    """Start a background check. Returns the thread, or None when skipped."""
    info = read_build_info()
    if not info.is_release_build:
        if force:
            QMessageBox.information(parent, tr("update_title"), tr("update_dev_build_msg"))
        return None
    if _RUNNING_CHECKS:
        # Never run two checks at once: two writers into the same download
        # dir, a second prompt nested over the modal progress dialog, and
        # twice the unauthenticated GitHub API calls against a 60/hr/IP quota.
        if force:
            QMessageBox.information(parent, tr("update_title"), tr("update_checking_msg"))
        return None
    # Deliberately not Qt-parented to `parent`: Qt would then destroy this
    # QThread automatically if that widget is destroyed first (e.g. the
    # login dialog is recreated every loop iteration in app.py), which is
    # exactly the "destroyed while still running" crash this module must
    # avoid. Lifetime is owned by _RUNNING_CHECKS/_on_finished instead.
    thread = UpdateCheckThread(info.version, info.variant, info.runtime)

    def _on_found(found):
        # The found signal is a queued cross-thread connection, so this can
        # run well after the caller moved on - e.g. app.py recreates the
        # login dialog on every loop iteration, so `parent` may already be a
        # destroyed C++ object by the time this fires. A parentless message
        # box is fine; a dangling pointer is not.
        box_parent = _live(parent)
        state.mark_checked(home)
        if isinstance(found, Exception):
            # Silent by default (offline/rate-limited networks are routine);
            # a forced check must not lie by reporting "up to date" instead.
            if force:
                QMessageBox.warning(
                    box_parent, tr("update_check_failed_title"),
                    tr("update_check_failed_msg", type=type(found).__name__, exc=found,
                       url=f"https://github.com/{checker.GITHUB_REPO}/releases/latest"))
            return
        if found is None:
            if force:
                QMessageBox.information(box_parent, tr("update_title"),
                                        tr("update_uptodate_msg"))
            return
        if not force and state.load(home).skipped_version == found.version:
            return
        if found.kind == "app":
            # A few MB: fetch it now, offer it once it is verified on disk.
            _download_then_offer(parent, found, home, force)
            return
        _offer(box_parent, found, home)

    def _on_finished():
        _RUNNING_CHECKS.discard(thread)
        thread.deleteLater()

    thread.found.connect(_on_found)
    thread.finished.connect(_on_finished)
    _RUNNING_CHECKS.add(thread)
    thread.start()
    return thread


def _periodic_check() -> None:
    if _PROMPTING:
        return  # a prompt is open; its own result is still being handled
    check_for_updates(None)


def start_periodic_checks(interval_ms: int = 4 * 3600 * 1000) -> None:
    """Check again every `interval_ms` while the app runs (once per app)."""
    if _PERIODIC:
        return
    timer = QTimer()
    timer.setInterval(interval_ms)
    timer.timeout.connect(_periodic_check)
    timer.start()
    _PERIODIC.append(timer)
