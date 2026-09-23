"""Qt front end for the updater: background check, prompt, download, hand-off."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QProgressDialog,
)

from labeling_tool.core import net_download
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


class UpdateCheckThread(QThread):
    """Look for an update off the UI thread; emits UpdateInfo, None, or the
    exception that made the check fail (the caller decides whether a failure
    is worth reporting - see check_for_updates._on_found)."""
    found = pyqtSignal(object)

    # Bounds the worst case of a hung proxy / dead network so
    # wait_for_checks() at shutdown has a predictable ceiling.
    CHECK_TIMEOUT = 5

    def __init__(self, current_version: str, variant: str, parent=None):
        super().__init__(parent)
        self._version, self._variant = current_version, variant

    def run(self):
        try:
            self.found.emit(checker.find_update(
                self._version, self._variant, timeout=self.CHECK_TIMEOUT))
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


def _ask(parent, info) -> str:
    """The three-button prompt; returns UPDATE / LATER / SKIP."""
    size_mb = info.size // (1024 * 1024)
    notes = "\n".join(info.notes.splitlines()[:8])
    box = QMessageBox(parent)
    box.setWindowTitle("업데이트")
    box.setIcon(QMessageBox.Information)
    # A release body is untrusted remote text: PlainText keeps AutoText from
    # rendering it as rich text (which could otherwise fetch remote images).
    box.setTextFormat(Qt.PlainText)
    text = (f"새 버전이 있습니다: v{info.version}\n"
           f"다운로드 크기: 약 {size_mb} MB")
    if info.variant == "full":
        text += "\n\n⚠ full 버전 업데이트는 약 1.5 GB 를 다운로드합니다. " \
               "충분한 네트워크/디스크 공간을 확인하세요."
    box.setText(text)
    box.setInformativeText(f"설치 후 자동으로 다시 시작됩니다.\n\n{notes}")
    btn_update = box.addButton("지금 업데이트", QMessageBox.AcceptRole)
    box.addButton("나중에", QMessageBox.RejectRole)
    btn_skip = box.addButton("이 버전 건너뛰기", QMessageBox.DestructiveRole)
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
    # user-writable path and stops installers (up to ~1.5 GB each)
    # accumulating forever under a single well-known name.
    target_dir = Path(tempfile.mkdtemp(prefix="LabelingTool-update-"))
    dest = target_dir / info.asset_name
    bar = QProgressDialog("업데이트 다운로드 중…", "취소", 0, 100, parent)
    bar.setWindowTitle("업데이트")
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    def on_progress(done: int, total: int) -> bool:
        total = total or info.size
        bar.setValue(min(100, done * 100 // max(1, total)))
        bar.setLabelText(f"업데이트 다운로드 중… {done // (1024 * 1024)} / "
                         f"{total // (1024 * 1024)} MB")
        QApplication.processEvents()
        return not bar.wasCanceled()

    try:
        net_download.download_file(info.asset_url, dest, info.sha256, progress=on_progress)
        installer.launch_installer(dest, target_dir / "update.log")
        return True
    except net_download.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum / launch
        vlog().exception("update failed")
        QMessageBox.critical(parent, "업데이트 실패",
                             f"{type(exc).__name__}: {exc}\n\n"
                             f"나중에 다시 시도하거나 직접 내려받으세요:\n"
                             f"https://github.com/{checker.GITHUB_REPO}/releases/latest")
        return False
    finally:
        bar.close()


def check_for_updates(parent, *, force: bool = False, home: Path | None = None):
    """Start a background check. Returns the thread, or None when skipped."""
    info = read_build_info()
    if not info.is_release_build:
        if force:
            QMessageBox.information(parent, "업데이트",
                                    "개발 빌드에서는 업데이트를 확인할 수 없습니다.")
        return None
    if _RUNNING_CHECKS:
        # Never run two checks at once: two writers into the same download
        # dir, a second prompt nested over the modal progress dialog, and
        # twice the unauthenticated GitHub API calls against a 60/hr/IP quota.
        if force:
            QMessageBox.information(parent, "업데이트", "업데이트 확인 중입니다.")
        return None
    st = state.load(home)
    if not force and not state.should_check(st):
        return None

    # Deliberately not Qt-parented to `parent`: Qt would then destroy this
    # QThread automatically if that widget is destroyed first (e.g. the
    # login dialog is recreated every loop iteration in app.py), which is
    # exactly the "destroyed while still running" crash this module must
    # avoid. Lifetime is owned by _RUNNING_CHECKS/_on_finished instead.
    thread = UpdateCheckThread(info.version, info.variant)

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
                    box_parent, "업데이트 확인 실패",
                    f"업데이트 확인 중 오류가 발생했습니다: "
                    f"{type(found).__name__}: {found}\n\n"
                    f"https://github.com/{checker.GITHUB_REPO}/releases/latest")
            return
        if found is None:
            if force:
                QMessageBox.information(box_parent, "업데이트",
                                        "최신 버전을 사용 중입니다.")
            return
        if not force and state.load(home).skipped_version == found.version:
            return
        if _session_in_progress():
            # A session with unsaved work is already open. Quitting via
            # QApplication.quit() would bypass ViewerMainWindow.closeEvent
            # and lose it, so stay silent - the next launch/manual check
            # asks again.
            return
        if prompt_and_install(box_parent, found, home):
            QApplication.quit()   # the installer restarts the new version

    def _on_finished():
        _RUNNING_CHECKS.discard(thread)
        thread.deleteLater()

    thread.found.connect(_on_found)
    thread.finished.connect(_on_finished)
    _RUNNING_CHECKS.add(thread)
    thread.start()
    return thread
