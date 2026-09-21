"""Ask for and download the SAM2.1 weights the first time few-shot opens.

Follows the fetch dialog's pattern: a synchronous download that keeps the UI
alive with processEvents() from the progress callback.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog


def ensure_sam2_weights(parent=None) -> bool:
    """True when the SAM2.1 checkpoint exists or was just downloaded."""
    from annotation_tool import configs
    from annotation_tool.segmenter import weights

    dest = Path(configs.SAM2_CHECKPOINT)
    if dest.is_file():
        return True
    size_mb = weights.SAM2_WEIGHTS_SIZE // (1024 * 1024)
    answer = QMessageBox.question(
        parent, "SAM2.1 모델 다운로드",
        f"Few-shot 라벨링에는 SAM2.1 모델(약 {size_mb} MB)이 필요합니다.\n"
        f"처음 한 번만 내려받으며, 다음부터는 바로 사용됩니다.\n\n"
        f"저장 위치: {dest}\n\n지금 다운로드할까요?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if answer != QMessageBox.Yes:
        return False

    bar = QProgressDialog("SAM2.1 모델 다운로드 중…", "취소", 0, 100, parent)
    bar.setWindowTitle("SAM2.1 모델 다운로드")
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    def on_progress(done: int, total: int) -> bool:
        total = total or weights.SAM2_WEIGHTS_SIZE
        bar.setValue(min(100, done * 100 // total))
        bar.setLabelText(f"SAM2.1 모델 다운로드 중… {done // (1024 * 1024)} / "
                         f"{total // (1024 * 1024)} MB")
        QApplication.processEvents()
        return not bar.wasCanceled()

    try:
        weights.download_weights(weights.SAM2_WEIGHTS_URL, dest,
                                 weights.SAM2_WEIGHTS_SHA256, progress=on_progress)
        return True
    except weights.DownloadCancelled:
        return False
    except Exception as exc:  # noqa: BLE001 - network / disk / checksum: tell the user
        QMessageBox.critical(
            parent, "다운로드 실패",
            f"SAM2.1 모델을 내려받지 못했습니다.\n{type(exc).__name__}: {exc}\n\n"
            f"인터넷 연결을 확인하거나, 파일을 직접 받아 {dest} 에 두세요:\n"
            f"{weights.SAM2_WEIGHTS_URL}")
        return False
    finally:
        bar.close()
