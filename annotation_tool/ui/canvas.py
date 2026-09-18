# annotation_tool/ui/canvas.py
"""Zoomable image canvas: collects point/box prompts, renders committed
class layers + candidate mask overlays."""
from __future__ import annotations

import numpy as np
from PIL import Image
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsItem,
)

from annotation_tool.configs import CLASS_COLORS, OVERLAY_ALPHA, EXPORT_ORDER
from annotation_tool.ui.geometry import clamp_point


def _pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, 3 * rgb.width, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


def _mask_to_rgba_pixmap(mask: np.ndarray, color, alpha: float) -> QPixmap:
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask, 0], rgba[mask, 1], rgba[mask, 2] = color
    rgba[mask, 3] = int(alpha * 255)
    qimg = QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class ImageCanvas(QGraphicsView):
    promptChanged = pyqtSignal(list, list, object)  # points, labels, box
    strokeFinished = pyqtSignal(object, bool)       # (stroke bool[H,W], is_erase)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.NoDrag)
        self._base_item = None
        self._layer_items = {}
        self._cand_item = None
        self._img_wh = (0, 0)
        self._points: list[tuple[int, int]] = []
        self._labels: list[int] = []
        self._box = None
        self._box_start = None
        self._space_pan = False
        self._point_items: list = []   # green/red dot markers, parallel to _points
        self._box_item = None          # dashed rectangle marker for the box prompt
        self._panning = False          # Ctrl+left-drag panning
        self._pan_start = None
        # manual brush / eraser
        self._tool = "sam"             # "sam" | "brush" | "eraser"
        self._brush_size = 40          # radius in image pixels
        self._brush_color = (255, 255, 255)
        self._painting = False
        self._stroke = None            # bool[H,W] accumulator for the current stroke
        self._stroke_item = None
        self._last_paint = None        # last image-coord point while painting

    # --- image / layers ---
    def set_image(self, pil_img: Image.Image):
        self._scene.clear()
        self._layer_items.clear()
        self._cand_item = None
        self._point_items = []   # scene.clear() already removed the items
        self._box_item = None
        self._stroke_item = None
        self._stroke = None
        self._painting = False
        self._img_wh = pil_img.size
        self._base_item = QGraphicsPixmapItem(_pil_to_qpixmap(pil_img))
        self._scene.addItem(self._base_item)
        self._scene.setSceneRect(0, 0, pil_img.width, pil_img.height)
        self.clear_prompt()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    @property
    def image_size(self):
        return self._img_wh

    def set_committed_layers(self, layers: dict[int, np.ndarray],
                             colors: dict[int, tuple] | None = None,
                             export_order: list[int] | None = None):
        """Render committed class layers. `colors` / `export_order` come from the
        runtime ClassRegistry; they default to the configs factory values."""
        colors = CLASS_COLORS if colors is None else colors
        order = EXPORT_ORDER if export_order is None else export_order
        w, h = self._img_wh
        for c, m in layers.items():
            if m is not None:
                assert m.shape == (h, w), f"layer {c} shape {m.shape} != image (h,w)=({h},{w})"
        for item in self._layer_items.values():
            if item is not None:
                self._scene.removeItem(item)
        self._layer_items.clear()
        for c, m in layers.items():
            if m is not None and m.any() and c in colors:
                item = QGraphicsPixmapItem(_mask_to_rgba_pixmap(m, colors[c], OVERLAY_ALPHA))
                # higher-priority classes render on top; all stay below the
                # candidate (z=2) by squeezing into (1, 2)
                rank = order.index(c) if c in order else len(order)
                item.setZValue(1 + rank / (len(order) + 1))
                self._scene.addItem(item)
                self._layer_items[c] = item

    def set_candidate(self, mask):
        if mask is not None:
            w, h = self._img_wh
            assert mask.shape == (h, w), f"candidate shape {mask.shape} != image (h,w)=({h},{w})"
        if self._cand_item is not None:
            self._scene.removeItem(self._cand_item)
            self._cand_item = None
        if mask is not None and mask.any():
            self._cand_item = QGraphicsPixmapItem(
                _mask_to_rgba_pixmap(mask, (255, 255, 0), 0.5))
            self._cand_item.setZValue(2)
            self._scene.addItem(self._cand_item)

    # --- prompt collection ---
    def add_point_image_coords(self, x: int, y: int, positive: bool):
        if self._img_wh == (0, 0):
            return
        w, h = self._img_wh
        x, y = clamp_point(x, y, w, h)
        self._points.append((x, y))
        self._labels.append(1 if positive else 0)
        self._add_point_marker(x, y, positive)
        self._emit_prompt()

    def current_prompt(self):
        return list(self._points), list(self._labels), self._box

    def clear_prompt(self):
        self._points, self._labels, self._box = [], [], None
        self._box_start = None
        self._clear_markers()

    def _emit_prompt(self):
        self.promptChanged.emit(list(self._points), list(self._labels), self._box)

    # --- prompt markers (point dots + box rectangle) ---
    def _add_point_marker(self, x: int, y: int, positive: bool):
        r = 5  # screen pixels (kept constant via ItemIgnoresTransformations)
        color = QColor(40, 220, 90) if positive else QColor(255, 60, 60)
        item = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        item.setBrush(QBrush(color))
        item.setPen(QPen(QColor(255, 255, 255), 1.5))
        item.setZValue(3)  # above committed layers (1) and candidate (2)
        item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        item.setPos(x, y)
        self._scene.addItem(item)
        self._point_items.append(item)

    def _pop_point_marker(self):
        if self._point_items:
            self._scene.removeItem(self._point_items.pop())

    def _set_box_marker(self, x0: int, y0: int, x1: int, y1: int):
        self._clear_box_marker()
        rect = QGraphicsRectItem(x0, y0, x1 - x0, y1 - y0)
        pen = QPen(QColor(255, 220, 0), 2, Qt.DashLine)
        pen.setCosmetic(True)  # constant screen line width regardless of zoom
        rect.setPen(pen)
        rect.setZValue(3)
        self._scene.addItem(rect)
        self._box_item = rect

    def _clear_box_marker(self):
        if self._box_item is not None:
            self._scene.removeItem(self._box_item)
            self._box_item = None

    def _clear_markers(self):
        for it in self._point_items:
            self._scene.removeItem(it)
        self._point_items = []
        self._clear_box_marker()

    # --- manual brush / eraser ---
    def set_tool(self, tool: str):
        """Switch between 'sam' (point/box) and manual 'brush' / 'eraser'."""
        self._tool = tool
        self.clear_prompt()        # tools are mutually exclusive with SAM prompts
        self.set_candidate(None)

    def set_brush_size(self, px: int):
        self._brush_size = max(1, int(px))

    def set_brush_color(self, rgb):
        self._brush_color = rgb

    def _stamp_disc(self, ix: int, iy: int):
        """Paint a filled circle of radius=_brush_size into the stroke buffer."""
        w, h = self._img_wh
        r = self._brush_size
        x0, x1 = max(0, ix - r), min(w, ix + r + 1)
        y0, y1 = max(0, iy - r), min(h, iy + r + 1)
        if x0 >= x1 or y0 >= y1:
            return
        ys, xs = np.ogrid[y0:y1, x0:x1]
        self._stroke[y0:y1, x0:x1] |= (xs - ix) ** 2 + (ys - iy) ** 2 <= r * r

    def _stamp_segment(self, p0, p1):
        """Stamp discs along the segment p0->p1 so fast drags leave no gaps."""
        (x0, y0), (x1, y1) = p0, p1
        steps = max(1, int(np.hypot(x1 - x0, y1 - y0) / max(1, self._brush_size // 2)))
        for i in range(steps + 1):
            t = i / steps
            self._stamp_disc(int(round(x0 + (x1 - x0) * t)),
                             int(round(y0 + (y1 - y0) * t)))

    def _update_stroke_item(self):
        if self._stroke_item is not None:
            self._scene.removeItem(self._stroke_item)
            self._stroke_item = None
        if self._stroke is not None and self._stroke.any():
            color = (230, 230, 230) if self._tool == "eraser" else self._brush_color
            self._stroke_item = QGraphicsPixmapItem(
                _mask_to_rgba_pixmap(self._stroke, color, 0.6))
            self._stroke_item.setZValue(2)
            self._scene.addItem(self._stroke_item)

    def _finish_stroke(self):
        if self._stroke is not None and self._stroke.any():
            self.strokeFinished.emit(self._stroke, self._tool == "eraser")
        if self._stroke_item is not None:
            self._scene.removeItem(self._stroke_item)
            self._stroke_item = None
        self._stroke = None
        self._painting = False
        self._last_paint = None

    # --- mouse / zoom ---
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._space_pan = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._space_pan = False
            self.setDragMode(QGraphicsView.NoDrag)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        # Ctrl + left-drag pans the view (works regardless of keyboard focus)
        if (event.button() == Qt.LeftButton
                and event.modifiers() & Qt.ControlModifier):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if self._space_pan or self._base_item is None:
            return super().mousePressEvent(event)
        sp = self.mapToScene(event.pos())
        ix, iy = int(sp.x()), int(sp.y())
        # brush / eraser: left-drag paints into the stroke buffer
        if self._tool in ("brush", "eraser"):
            if event.button() == Qt.LeftButton:
                w, h = self._img_wh
                self._stroke = np.zeros((h, w), dtype=bool)
                self._painting = True
                self._last_paint = (ix, iy)
                self._stamp_disc(ix, iy)
                self._update_stroke_item()
            return
        if event.button() == Qt.LeftButton:
            self._box_start = (ix, iy)  # may become a drag box
            self.add_point_image_coords(ix, iy, positive=True)
        elif event.button() == Qt.RightButton:
            self.add_point_image_coords(ix, iy, positive=False)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            return
        if self._painting:
            sp = self.mapToScene(event.pos())
            pt = (int(sp.x()), int(sp.y()))
            self._stamp_segment(self._last_paint, pt)
            self._last_paint = pt
            self._update_stroke_item()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._painting and event.button() == Qt.LeftButton:
            self._finish_stroke()
            return
        if self._space_pan or self._base_item is None:
            # a press that transitioned into pan: discard the stray point + box_start
            if event.button() == Qt.LeftButton and self._box_start is not None:
                if self._points:
                    self._points.pop()
                    self._labels.pop()
                    self._pop_point_marker()
                self._box_start = None
            return super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self._box_start is not None:
            sp = self.mapToScene(event.pos())
            x0, y0 = self._box_start
            x1, y1 = int(sp.x()), int(sp.y())
            moved = abs(x1 - x0) > 1 or abs(y1 - y0) > 1
            if moved and self._points:  # user dragged -> press point was unintended
                self._points.pop()
                self._labels.pop()
                self._pop_point_marker()
            if abs(x1 - x0) > 5 and abs(y1 - y0) > 5:  # accept as box drag
                w, h = self._img_wh
                bx0, by0 = clamp_point(min(x0, x1), min(y0, y1), w, h)
                bx1, by1 = clamp_point(max(x0, x1), max(y0, y1), w, h)
                self._box = (bx0, by0, bx1, by1)
                self._set_box_marker(bx0, by0, bx1, by1)
            if moved:
                self._emit_prompt()
            self._box_start = None
