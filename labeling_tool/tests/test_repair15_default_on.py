from PyQt5.QtWidgets import QApplication

from labeling_tool.core.canvas.image_canvas import ImageCanvas

_app = QApplication.instance() or QApplication([])


def test_repair15_shown_by_default():
    c = ImageCanvas()
    assert c.show_repair15 is True          # 15cm contour shown by default
