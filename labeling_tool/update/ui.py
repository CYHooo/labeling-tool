"""Qt front end for the updater: background check, prompt, download, hand-off."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QProgressDialog,
)

from labeling_tool.core import app_paths, net_download
from labeling_tool.core.i18n import tr
from labeling_tool.logging_setup import vlog
from labeling_tool.update import checker, installer, state
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


def wait_for_checks(msec: int = 3000) -> None:
    """Block until every running check thread finishes (or the timeout hits).

    Call this before the process exits: dropping the last reference to a
    QThread that is still running aborts with "QThread: Destroyed while
    thread is still running".
    """
    for thread in list(_RUNNING_CHECKS):
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
    """The three-button prompt; returns UPDATE / LATER / SKIP."""
    notes = "\n".join(info.notes.splitlines()[:8])
    box = QMessageBox(parent)
    box.setWindowTitle(tr("update_title"))
    box.setIcon(QMessageBox.Information)
    # A release body is untrusted remote text: PlainText keeps AutoText from
    # rendering it as rich text (which could otherwise fetch remote images).
    box.setTextFormat(Qt.PlainText)
    box.setText(prompt_text(info))
    box.setInformativeText(tr("update_informative", notes=notes))
    btn_update = box.addButton(tr("update_btn_update"), QMessageBox.AcceptRole)
    box.addButton(tr("update_btn_later"), QMessageBox.RejectRole)
    btn_skip = box.addButton(tr("update_btn_skip"), QMessageBox.DestructiveRole)
    box.exec_()
    if box.clickedButton() is btn_update:
        return UPDATE
    return SKIP if box.clickedButton() is btn_skip else LATER


def prompt_and_install(parent, info, home: Path | None = None) -> bool:
    """Ask, then download + verify + hand over. True = installer started."""
    choice = _ask(parent, info)
    if choice == SKIP:
        state.skip_version(info.version, home)
        return False
    if choice != UPDATE:
        return False

    # A fresh directory per download avoids the TOCTOU on a fixed,
    # user-writable path and stops packages (up to ~1.5 GB each)
    # accumulating forever under a single well-known name.
    cache_root = app_paths.user_cache_home()
    cache_root.mkdir(parents=True, exist_ok=True)
    target_dir = Path(tempfile.mkdtemp(prefix="update-", dir=cache_root))
    bar = QProgressDialog(tr("update_progress_label"), tr("update_cancel"), 0, 100, parent)
    bar.setWindowTitle(tr("update_title"))
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    done_before = 0
    paths = []
    try:
        for asset in info.assets:
            dest = target_dir / asset.name

            def on_progress(done, total, _base=done_before):
                # One bar across every asset: two 700 MB debs must not each
                # drive it from 0 to 100.
                overall = _base + done
                bar.setValue(min(100, overall * 100 // max(1, info.total_size)))
                bar.setLabelText(tr("update_progress_template",
                                    done=overall // (1024 * 1024),
                                    total=info.total_size // (1024 * 1024)))
                QApplication.processEvents()
                return not bar.wasCanceled()

            net_download.download_file(asset.url, dest, asset.sha256,
                                       progress=on_progress)
            paths.append(dest)
            done_before += asset.size
        return _hand_over(parent, info, paths, target_dir)
    except net_download.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum / launch
        vlog().exception("update failed")
        QMessageBox.critical(parent, tr("update_failed_title"),
                             tr("update_failed_msg", type=type(exc).__name__, exc=exc,
                                url=f"https://github.com/{checker.GITHUB_REPO}/releases/latest"))
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
    QMessageBox.critical(parent, tr("update_failed_title"),
                         tr("update_failed_msg", type="dpkg", exc=detail,
                            url=f"https://github.com/{checker.GITHUB_REPO}/releases/latest"))
    return False


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
        box_parent = parent
        if box_parent is not None and sip.isdeleted(box_parent):
            box_parent = None
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
        if _session_in_progress():
            # A session with unsaved work is already open. Quitting via
            # QApplication.quit() would bypass ViewerMainWindow.closeEvent
            # and lose it, so hold the update until the session ends:
            # app.py calls prompt_pending_update() after its window closes.
            vlog().info("update %s found mid-session; offering it on exit", found.version)
            _PENDING[:] = [(found, home)]
            return
        if prompt_and_install(box_parent, found, home) and checker.current_platform() == checker.WINDOWS:
            # Windows: the installer is about to replace the running exe, so
            # quit now. Linux already installed in place (install_debs ran
            # synchronously) and the user was told to restart manually.
            QApplication.quit()

    def _on_finished():
        _RUNNING_CHECKS.discard(thread)
        thread.deleteLater()

    thread.found.connect(_on_found)
    thread.finished.connect(_on_finished)
    _RUNNING_CHECKS.add(thread)
    thread.start()
    return thread
