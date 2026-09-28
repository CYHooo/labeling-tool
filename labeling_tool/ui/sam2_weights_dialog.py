"""Ask for and download the SAM2.1 weights the first time few-shot opens.

Follows the fetch dialog's pattern: a synchronous download that keeps the UI
alive with processEvents() from the progress callback.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from labeling_tool.core.i18n import tr


def ensure_sam2_weights(parent=None) -> bool:
    """True when the SAM2.1 checkpoint exists or was just downloaded."""
    from annotation_tool import configs
    from annotation_tool.segmenter import weights

    dest = Path(configs.SAM2_CHECKPOINT)
    if dest.is_file():
        return True
    size_mb = weights.SAM2_WEIGHTS_SIZE // (1024 * 1024)
    answer = QMessageBox.question(
        parent, tr("weights_title"),
        tr("weights_confirm", size=size_mb, path=dest),
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if answer != QMessageBox.Yes:
        return False

    bar = QProgressDialog(tr("weights_progress_label"), tr("weights_cancel"), 0, 100, parent)
    bar.setWindowTitle(tr("weights_title"))
    bar.setWindowModality(Qt.ApplicationModal)
    bar.setMinimumDuration(0)
    bar.setValue(0)

    def on_progress(done: int, total: int) -> bool:
        total = total or weights.SAM2_WEIGHTS_SIZE
        bar.setValue(min(100, done * 100 // total))
        bar.setLabelText(tr("weights_progress_template",
                           done=done // (1024 * 1024), total=total // (1024 * 1024)))
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
            parent, tr("weights_failed_title"),
            tr("weights_failed_msg", type=type(exc).__name__, exc=exc,
               path=dest, url=weights.SAM2_WEIGHTS_URL))
        return False
    finally:
        bar.close()
