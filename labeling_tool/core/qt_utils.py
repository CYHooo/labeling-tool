"""Qt-related conversion helpers."""

import os
import numpy as np
import cv2
import PyQt5

# cv2 forces QT_QPA_PLATFORM_PLUGIN_PATH; reset before PyQt5 imports
_pyqt_plugins = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(_pyqt_plugins, "platforms")
os.environ["QT_PLUGIN_PATH"] = _pyqt_plugins

from PyQt5.QtGui import QImage, QPixmap


def numpy_to_qpixmap(bgr: np.ndarray) -> QPixmap:
    """Convert OpenCV BGR ndarray to QPixmap."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)
