"""Viewport state: zoom, pan, and coordinate transforms.

Pure-logic class (no Qt event handling) that owns the scale/offset state
of an image displayed inside a widget. ImageCanvas delegates all
coordinate math to it.
"""

from PyQt5.QtCore import QPoint


class Viewport:
    def __init__(self):
        self.scale: float = 1.0
        self.offset: QPoint = QPoint(0, 0)
        self.img_w: int = 1
        self.img_h: int = 1

    def set_image_size(self, w: int, h: int) -> None:
        self.img_w = w
        self.img_h = h

    def fit_to(self, widget_w: int, widget_h: int) -> None:
        """Center-fit the image in a widget of the given size."""
        sx = widget_w / self.img_w
        sy = widget_h / self.img_h
        self.scale = min(sx, sy)
        sw = self.img_w * self.scale
        sh = self.img_h * self.scale
        self.offset = QPoint(int((widget_w - sw) / 2), int((widget_h - sh) / 2))

    def widget_to_image(self, wx: float, wy: float) -> tuple[float, float]:
        return ((wx - self.offset.x()) / self.scale,
                (wy - self.offset.y()) / self.scale)

    def image_to_widget(self, ix: float, iy: float) -> tuple[float, float]:
        return (ix * self.scale + self.offset.x(),
                iy * self.scale + self.offset.y())

    def zoom_at(self, wx: int, wy: int, factor: float,
                widget_w: int, widget_h: int) -> bool:
        """
        Zoom around the cursor (pixel under cursor stays put).
        Returns True if the scale actually changed.
        """
        widget_w = max(widget_w, 1)
        widget_h = max(widget_h, 1)
        fit_scale = min(widget_w / self.img_w, widget_h / self.img_h)
        new_scale = self.scale * factor
        new_scale = max(fit_scale * 0.5, min(fit_scale * 20.0, new_scale))
        if abs(new_scale - self.scale) < 1e-6:
            return False
        ix, iy = self.widget_to_image(wx, wy)
        self.scale = new_scale
        self.offset = QPoint(int(wx - ix * new_scale), int(wy - iy * new_scale))
        return True

    def pan_to(self, start_offset: QPoint, dx: int, dy: int) -> None:
        self.offset = QPoint(start_offset.x() + dx, start_offset.y() + dy)
