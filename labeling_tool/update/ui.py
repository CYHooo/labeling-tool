"""Qt front end for the updater: background check, prompt, download, hand-off."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from labeling_tool.core import net_download
from labeling_tool.logging_setup import vlog
from labeling_tool.update import checker, installer, state
from labeling_tool.update.version import read_build_info

UPDATE, LATER, SKIP = "update", "later", "skip"


class UpdateCheckThread(QThread):
    """Look for an update off the UI thread; emits UpdateInfo or None."""
    found = pyqtSignal(object)

    def __init__(self, current_version: str, variant: str, parent=None):
        super().__init__(parent)
        self._version, self._variant = current_version, variant

    def run(self):
        try:
            self.found.emit(checker.find_update(self._version, self._variant))
        except Exception as exc:  # noqa: BLE001 - a failed check must stay silent
            vlog().info("update check failed: %s: %s", type(exc).__name__, exc)
            self.found.emit(None)


def _ask(parent, info) -> str:
    """The three-button prompt; returns UPDATE / LATER / SKIP."""
    size_mb = info.size // (1024 * 1024)
    notes = "\n".join(info.notes.splitlines()[:8])
    box = QMessageBox(parent)
    box.setWindowTitle("업데이트")
    box.setIcon(QMessageBox.Information)
    box.setText(f"새 버전이 있습니다: v{info.version}\n"
                f"다운로드 크기: 약 {size_mb} MB")
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

    target_dir = Path(tempfile.gettempdir()) / "LabelingTool-update"
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
        return None
    st = state.load(home)
    if not force and not state.should_check(st):
        return None

    thread = UpdateCheckThread(info.version, info.variant, parent)

    def _on_found(found):
        state.mark_checked(home)
        if found is None:
            if force:
                QMessageBox.information(parent, "업데이트",
                                        "최신 버전을 사용 중입니다.")
            return
        if not force and state.load(home).skipped_version == found.version:
            return
        if prompt_and_install(parent, found, home):
            QApplication.quit()   # the installer restarts the new version

    thread.found.connect(_on_found)
    thread.start()
    return thread
