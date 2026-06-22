"""Image canvas widget with zoom/pan and a category-aware brush layer."""

import numpy as np
import cv2
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPixmap

from labeling_tool.core.constants import BRUSH_DEFAULT_SIZE, DEFAULT_CATEGORY
from labeling_tool.core.qt_utils import numpy_to_qpixmap
from labeling_tool.core.canvas.viewport import Viewport
from labeling_tool.core.canvas.overlay_painter import paint_mask_overlay
from labeling_tool.core.bbox import BBoxInteraction, paint_bboxes
from labeling_tool.core.canvas.stroke_thinning import thin_stroke_into


class ImageCanvas(QWidget):
    """
    Image canvas with zoom/pan plus a category-aware brush layer.

    The brush layer is the live mask being edited: initialized from the
    detected mask on image load, written back on save.
    """

    mask_edited = pyqtSignal()
    bbox_edited = pyqtSignal()
    measure_completed = pyqtSignal(float)   # pixel distance of the 2-point line

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(600, 400)

        self._pixmap = None
        self.viewport = Viewport()

        self.brush_mask_crack: np.ndarray | None = None
        self.brush_mask_spalling: np.ndarray | None = None

        self.current_category: str = DEFAULT_CATEGORY
        self.brush_mode: bool = False
        self.brush_size: int = BRUSH_DEFAULT_SIZE
        # Fine-annotation: when True a crack stroke keeps its painted thickness
        # (no 1px thinning on mouse release), so width metrics reflect the real
        # drawn width. Default False = the original 1px-centerline behaviour.
        self.fine_annotation: bool = False

        self._brushing: bool = False
        self._brush_erase: bool = False
        self._brush_last_pt: tuple[int, int] | None = None
        self._mouse_pos_widget: tuple[int, int] | None = None

        # Coarse-annotation: a crack paint stroke is tracked separately so it
        # can be thinned to a 1-px centerline on mouse release.
        self._crack_stroke: np.ndarray | None = None

        # Overlay cache: the (expensive) mask overlay is rebuilt only when the
        # masks or the viewport change, not on every brush-cursor move.
        self._mask_revision: int = 0
        self._overlay_pixmap: QPixmap | None = None
        self._overlay_key = None

        self._panning = False
        self._pan_start_widget = (0, 0)
        self._pan_start_offset = QPoint(0, 0)

        # ----- bbox state -----
        self.bbox_mode: bool = False
        self.bbox_interaction = BBoxInteraction()
        self._bbox_padding_px: float = 0.0

        # ----- ArUco overlay (display only; never saved to Result) -----
        self._aruco_corners: np.ndarray | None = None

        # ----- manual scale measurement (fallback when ArUco not found) -----
        self.measure_mode: bool = False
        self._measure_points: list[tuple[float, float]] = []   # image coords

        # ----- derived-mask overlays (display-only; default hidden) -----
        self.highlight_mask: np.ndarray | None = None
        self._highlight_halo: np.ndarray | None = None   # ring = highlight - mask
        self.repair15_contours: list | None = None
        self.show_highlight: bool = False
        self.show_repair15: bool = False

        # ----- SAM (MobileSAM point-select for spalling) -----
        self.sam_mode: bool = False
        self._sam_predictor = None                 # injected; None = unavailable
        self._origin_bgr: np.ndarray | None = None  # kept for predictor.set_image
        self._sam_points: list[tuple[int, int]] = []
        self._sam_labels: list[int] = []
        self._sam_preview: np.ndarray | None = None
        self._sam_image_set: bool = False           # encoder run for current image

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_image(self, origin_bgr: np.ndarray,
                  crack_mask: np.ndarray | None,
                  spalling_mask: np.ndarray | None):
        h, w = origin_bgr.shape[:2]
        self.viewport.set_image_size(w, h)
        self._pixmap = numpy_to_qpixmap(origin_bgr)
        self._origin_bgr = origin_bgr.copy()
        self.viewport.fit_to(self.width(), self.height())

        self.brush_mask_crack = (
            crack_mask.copy() if crack_mask is not None
            else np.zeros((h, w), dtype=np.uint8)
        )
        self.brush_mask_spalling = (
            spalling_mask.copy() if spalling_mask is not None
            else np.zeros((h, w), dtype=np.uint8)
        )

        self._brushing = False
        self._brush_last_pt = None
        self._crack_stroke = None
        self.bbox_interaction.clear_for_image_switch()
        self._aruco_corners = None    # cleared until caller sets fresh ones
        self._measure_points = []     # stale measurement line off the new image
        self.highlight_mask = None
        self._highlight_halo = None
        self.repair15_contours = None
        self._clear_sam_state()
        self._touch_mask()
        self.update()

    def _touch_mask(self):
        """Invalidate the overlay cache after a mask edit."""
        self._mask_revision += 1

    def clear(self):
        self._pixmap = None
        self.brush_mask_crack = None
        self.brush_mask_spalling = None
        self._touch_mask()
        self.update()

    # Public API for bbox
    def set_bbox_padding_px(self, px: float) -> None:
        self._bbox_padding_px = float(px)

    def set_bbox_mode(self, enabled: bool) -> None:
        self.bbox_mode = bool(enabled)
        if not enabled:
            self.bbox_interaction.in_progress_clicks = []
            self.bbox_interaction.selected_idx = None
            self.unsetCursor()
        self.update()

    # ----- internal scale-aware helpers for bbox handles -----
    def _bbox_hit_tol_image_px(self) -> float:
        """Image-px equivalent of 10 widget px (handle hit radius)."""
        return 10.0 / max(self.viewport.scale, 1e-6)

    def _bbox_rot_offset_image_px(self) -> float:
        """Image-px equivalent of 30 widget px (rotation grip distance)."""
        return 30.0 / max(self.viewport.scale, 1e-6)

    _CURSOR_BY_HANDLE = {
        "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
        "t":  Qt.SizeVerCursor,   "b":  Qt.SizeVerCursor,
        "l":  Qt.SizeHorCursor,   "r":  Qt.SizeHorCursor,
        "rot": Qt.CrossCursor,
    }

    @property
    def bbox_padding_px(self) -> float:
        return self._bbox_padding_px

    def set_measure_mode(self, enabled: bool) -> None:
        """Enter/leave manual 2-point scale measurement mode."""
        self.measure_mode = bool(enabled)
        self._measure_points = []
        if enabled:
            self.setCursor(Qt.CrossCursor)
        else:
            self.unsetCursor()
        self.update()

    def set_sam_predictor(self, predictor) -> None:
        """Inject the MobileSAM predictor (None when unavailable)."""
        self._sam_predictor = predictor

    def set_sam_mode(self, enabled: bool) -> None:
        self.sam_mode = bool(enabled)
        if not enabled:
            self._clear_sam_state()
        self.update()

    def _clear_sam_state(self) -> None:
        self._sam_points = []
        self._sam_labels = []
        self._sam_preview = None
        self._sam_image_set = False

    def has_sam_preview(self) -> bool:
        return self._sam_preview is not None

    def _sam_add_point(self, ix: int, iy: int, label: int) -> None:
        if self._sam_predictor is None or self._origin_bgr is None:
            return
        if not self._sam_image_set:
            self._sam_predictor.set_image(self._origin_bgr)   # lazy encode
            self._sam_image_set = True
        self._sam_points.append((int(ix), int(iy)))
        self._sam_labels.append(int(label))
        self._sam_recompute()

    def _sam_recompute(self) -> None:
        """Re-predict the preview from the current points (or clear if none)."""
        if not self._sam_points:
            self._sam_preview = None
            self.update()
            return
        try:
            self._sam_preview = self._sam_predictor.predict(
                self._sam_points, self._sam_labels)
        except Exception:
            from labeling_tool.logging_setup import vlog
            vlog().exception("SAM predict failed")
            self._sam_preview = None
        self.update()

    def undo_sam_point(self) -> bool:
        """Drop the last clicked point and re-predict; returns True if a point
        was removed. Recovers from a click that selected too much."""
        if not self._sam_points:
            return False
        self._sam_points.pop()
        self._sam_labels.pop()
        self._sam_recompute()
        return True

    def commit_sam(self) -> bool:
        """OR the preview into the spalling layer; returns True if anything written."""
        if self._sam_preview is None or self.brush_mask_spalling is None:
            return False
        self.brush_mask_spalling[self._sam_preview > 0] = 255
        self._clear_sam_state()
        self._touch_mask()
        self.mask_edited.emit()
        self.update()
        return True

    def cancel_sam(self) -> None:
        self._clear_sam_state()
        self.update()

    def clear_measurement(self) -> None:
        self._measure_points = []
        self.update()

    def measure_points(self) -> list[tuple[float, float]]:
        """The current manual-measurement points (image coords); copy."""
        return list(self._measure_points)

    def set_measure_points(self, points) -> None:
        """Restore a persisted manual-measurement line (display only). The line
        is drawn whenever points are set, independent of measure mode."""
        self._measure_points = (
            [(float(x), float(y)) for x, y in points] if points else [])
        self.update()

    def set_aruco_corners(self, corners) -> None:
        """Set the ArUco marker corners (4x2) to overlay, or None to clear.
        Display-only; not written to Result/<stem>.png by export_result()."""
        self._aruco_corners = corners
        self.update()

    def set_highlight(self, arr: np.ndarray | None) -> None:
        """Store the 0/1/2 highlight mask + precompute its halo ring (the
        dilated region minus the current mask, so the mask keeps its colour)."""
        from labeling_tool.core.canvas.overlay_painter import compute_highlight_halo
        self.highlight_mask = arr
        self._highlight_halo = compute_highlight_halo(
            arr, self.brush_mask_crack, self.brush_mask_spalling)
        self._touch_mask()
        self.update()

    def set_repair15(self, arr: np.ndarray | None) -> None:
        """Compute external contours (image coords) of the 0/255 mask, once."""
        if arr is None:
            self.repair15_contours = None
        else:
            binu = (arr > 0).astype(np.uint8)
            cnts, _ = cv2.findContours(
                binu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            self.repair15_contours = list(cnts) if cnts else None
        self.update()

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        if self._pixmap is not None:
            self.viewport.fit_to(self.width(), self.height())
        super().resizeEvent(event)

    def wheelEvent(self, event):
        if self._pixmap is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1 / 1.15)
        if self.viewport.zoom_at(event.x(), event.y(), factor,
                                 self.width(), self.height()):
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(40, 40, 40))

        if self._pixmap:
            from PyQt5.QtCore import QRect
            sw = int(self.viewport.img_w * self.viewport.scale)
            sh = int(self.viewport.img_h * self.viewport.scale)
            dest = QRect(self.viewport.offset.x(), self.viewport.offset.y(), sw, sh)
            painter.drawPixmap(dest, self._pixmap)

        if self._pixmap is not None:
            self._draw_cached_overlay(painter)

        if (self._pixmap is not None and self.show_highlight
                and self._highlight_halo is not None):
            from labeling_tool.core.canvas.overlay_painter import (
                paint_single_color_overlay,
            )
            paint_single_color_overlay(
                painter, self.viewport, self.width(), self.height(),
                self._highlight_halo, (255, 255, 0), alpha=90)

        if (self._pixmap is not None and self.show_repair15
                and self.repair15_contours is not None):
            self._paint_repair15(painter)

        if (self._pixmap is not None and self.sam_mode
                and self._sam_preview is not None):
            from labeling_tool.core.canvas.overlay_painter import (
                paint_single_color_overlay,
            )
            paint_single_color_overlay(
                painter, self.viewport, self.width(), self.height(),
                self._sam_preview, (60, 220, 90), alpha=110)
            self._paint_sam_points(painter)

        # bbox overlay (always visible, including when bbox_mode is off)
        if self._pixmap is not None:
            paint_bboxes(
                painter, self.viewport,
                self.bbox_interaction.boxes,
                self.bbox_interaction.selected_idx,
                self.bbox_interaction.in_progress_clicks,
                rot_offset_image_px=self._bbox_rot_offset_image_px(),
            )

        # ArUco overlay (display only; never written to Result/<stem>.png)
        if self._pixmap is not None and self._aruco_corners is not None:
            self._paint_aruco_outline(painter)

        if self._pixmap is not None and self._measure_points:
            self._paint_measurement(painter)

        if self.brush_mode and self._mouse_pos_widget is not None:
            self._paint_brush_cursor(painter)

    def _draw_cached_overlay(self, painter: QPainter):
        """Composite the mask overlay, rebuilding it only when the masks or the
        viewport actually change. Brush-cursor moves (the common case while
        hovering) reuse the cached pixmap instead of re-resizing the masks."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        key = (round(self.viewport.scale, 6),
               self.viewport.offset.x(), self.viewport.offset.y(),
               w, h, self._mask_revision)
        if self._overlay_pixmap is None or key != self._overlay_key:
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            op = QPainter(pm)
            paint_mask_overlay(op, self.viewport, w, h,
                               self.brush_mask_crack, self.brush_mask_spalling)
            op.end()
            self._overlay_pixmap = pm
            self._overlay_key = key
        painter.drawPixmap(0, 0, self._overlay_pixmap)

    def _paint_sam_points(self, painter: QPainter):
        from PyQt5.QtGui import QColor, QPen
        from PyQt5.QtCore import QPointF
        for (ix, iy), lab in zip(self._sam_points, self._sam_labels):
            wx, wy = self.viewport.image_to_widget(ix, iy)
            color = QColor(60, 220, 90) if lab == 1 else QColor(230, 70, 70)
            painter.setPen(QPen(QColor(20, 20, 20), 2))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(wx, wy), 5, 5)

    def _paint_repair15(self, painter: QPainter):
        """Draw the 15cm boundary as cyan outline polylines (line only)."""
        pen = QPen(QColor(0, 200, 255, 230), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        for cnt in self.repair15_contours:
            pts = cnt.reshape(-1, 2)
            if len(pts) < 2:
                continue
            wpts = [QPointF(*self.viewport.image_to_widget(float(x), float(y)))
                    for x, y in pts]
            for i in range(len(wpts)):
                painter.drawLine(wpts[i], wpts[(i + 1) % len(wpts)])

    def _paint_aruco_outline(self, painter: QPainter):
        """Draw the detected ArUco marker outline + corner dots."""
        corners = self._aruco_corners
        widget_pts = [
            QPointF(*self.viewport.image_to_widget(float(x), float(y)))
            for x, y in corners
        ]
        pen = QPen(QColor(0, 220, 220, 230), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        for i in range(4):
            painter.drawLine(widget_pts[i], widget_pts[(i + 1) % 4])
        # Corner dots so the user can spot the detected marker easily.
        painter.setBrush(QBrush(QColor(0, 220, 220, 230)))
        painter.setPen(QPen(QColor(20, 20, 20, 255), 1))
        for p in widget_pts:
            painter.drawEllipse(p, 4, 4)
        # Label "ArUco" near TL corner
        tl = widget_pts[0]
        painter.setPen(QPen(QColor(0, 220, 220, 230), 1))
        painter.drawText(QPointF(tl.x() + 6, tl.y() - 6), "ArUco")

    def _paint_measurement(self, painter: QPainter):
        """Draw the manual measurement points and connecting line."""
        pts = [QPointF(*self.viewport.image_to_widget(float(x), float(y)))
               for x, y in self._measure_points]
        pen = QPen(QColor(255, 200, 0, 240), 2, Qt.SolidLine)
        painter.setPen(pen)
        if len(pts) == 2:
            painter.drawLine(pts[0], pts[1])
        painter.setBrush(QBrush(QColor(255, 200, 0, 240)))
        painter.setPen(QPen(QColor(20, 20, 20, 255), 1))
        for p in pts:
            painter.drawEllipse(p, 4, 4)

    def _paint_brush_cursor(self, painter: QPainter):
        wx, wy = self._mouse_pos_widget
        radius_w = self.brush_size * self.viewport.scale
        if self._brush_erase:
            color = QColor(255, 80, 80)
        elif self.current_category == "spalling":
            color = QColor(60, 230, 60)
        else:
            color = QColor(255, 60, 60)
        painter.setPen(QPen(color, 2, Qt.DashLine))
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.drawEllipse(QPointF(wx, wy), radius_w, radius_w)

    # ------------------------------------------------------------------
    # Brush helpers
    # ------------------------------------------------------------------
    def _active_brush_mask(self) -> np.ndarray | None:
        return self.brush_mask_spalling if self.current_category == "spalling" \
                                       else self.brush_mask_crack

    def _brush_paint_at(self, p1, p2):
        m = self._active_brush_mask()
        if m is None:
            return
        x1, y1 = int(p1[0]), int(p1[1])
        x2, y2 = int(p2[0]), int(p2[1])
        thickness = max(1, int(self.brush_size * 2))
        value = 0 if self._brush_erase else 255
        cv2.line(m, (x1, y1), (x2, y2),
                 value, thickness=thickness, lineType=cv2.LINE_8)
        # Mirror the crack paint into the stroke layer so it can be thinned
        # to a 1-px line when the mouse is released.
        if (self._crack_stroke is not None and not self._brush_erase
                and self.current_category == "crack"):
            cv2.line(self._crack_stroke, (x1, y1), (x2, y2),
                     255, thickness=thickness, lineType=cv2.LINE_8)
        self._touch_mask()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self._pixmap is None:
            return
        ix, iy = self.viewport.widget_to_image(event.x(), event.y())

        if (event.button() == Qt.LeftButton and
                (event.modifiers() & Qt.ControlModifier)):
            self._panning = True
            self._pan_start_widget = (event.x(), event.y())
            self._pan_start_offset = QPoint(self.viewport.offset)
            self.setCursor(Qt.ClosedHandCursor)
            return

        if self.sam_mode:
            if event.button() == Qt.LeftButton:
                self._sam_add_point(ix, iy, 1)     # foreground
            elif event.button() == Qt.RightButton:
                self._sam_add_point(ix, iy, 0)     # background
            return

        if self.measure_mode:
            if event.button() == Qt.LeftButton:
                if len(self._measure_points) >= 2:
                    self._measure_points = []      # start a fresh measurement
                self._measure_points.append((ix, iy))
                if len(self._measure_points) == 2:
                    (x1, y1), (x2, y2) = self._measure_points
                    dist = float(np.hypot(x2 - x1, y2 - y1))
                    self.measure_completed.emit(dist)
                self.update()
            return

        if self.bbox_mode:
            if event.button() == Qt.LeftButton:
                changed = self.bbox_interaction.on_left_press(
                    ix, iy,
                    hit_tol_image_px=self._bbox_hit_tol_image_px(),
                    rot_offset_image_px=self._bbox_rot_offset_image_px(),
                )
                if changed:
                    self.bbox_edited.emit()
                    self.update()
            return

        if self.brush_mode:
            if event.button() == Qt.LeftButton:
                self._brushing = True
                self._brush_erase = False
                # Start tracking this crack paint stroke for release-time thinning.
                if (self.current_category == "crack"
                        and self.brush_mask_crack is not None):
                    self._crack_stroke = np.zeros_like(self.brush_mask_crack)
            elif event.button() == Qt.RightButton:
                self._brushing = True
                self._brush_erase = True
            else:
                return
            self._brush_paint_at((ix, iy), (ix, iy))
            self._brush_last_pt = (int(ix), int(iy))
            self.mask_edited.emit()
            self.update()

    def mouseMoveEvent(self, event):
        ix, iy = self.viewport.widget_to_image(event.x(), event.y())

        if self._panning:
            dx = event.x() - self._pan_start_widget[0]
            dy = event.y() - self._pan_start_widget[1]
            self.viewport.pan_to(self._pan_start_offset, dx, dy)
            self.update()
            return

        if self.bbox_mode:
            if self.bbox_interaction.dragging is not None:
                if self.bbox_interaction.on_mouse_drag(ix, iy):
                    self.bbox_edited.emit()
                    self.update()
            else:
                # Hover feedback: pick a cursor that hints what the click
                # would do at the current position.
                kind, detail = self.bbox_interaction.hit_test(
                    ix, iy,
                    hit_tol_image_px=self._bbox_hit_tol_image_px(),
                    rot_offset_image_px=self._bbox_rot_offset_image_px(),
                )
                if kind == "handle":
                    self.setCursor(
                        self._CURSOR_BY_HANDLE.get(detail, Qt.ArrowCursor))
                elif kind == "body":
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            return

        if self.brush_mode:
            self._mouse_pos_widget = (event.x(), event.y())
            if self._brushing:
                cur = (int(ix), int(iy))
                last = self._brush_last_pt or cur
                self._brush_paint_at(last, cur)
                self._brush_last_pt = cur
                self.mask_edited.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.LeftButton:
            self._panning = False
            self.unsetCursor()
            return

        if self.bbox_mode and event.button() == Qt.LeftButton:
            if self.bbox_interaction.on_release():
                self.update()
            return

        if self.brush_mode and self._brushing:
            self._brushing = False
            self._brush_last_pt = None
            # Coarse-annotation: collapse the just-drawn crack stroke to a
            # 1-px centerline (only this stroke; existing crack untouched).
            # In fine-annotation mode this thinning is skipped, so the painted
            # thickness — already in brush_mask_crack — is kept as-is.
            if self._crack_stroke is not None:
                if self.brush_mask_crack is not None and not self.fine_annotation:
                    thin_stroke_into(self.brush_mask_crack, self._crack_stroke)
                    self._touch_mask()
                    self.mask_edited.emit()
                self._crack_stroke = None
            self.update()

    def leaveEvent(self, event):
        self._mouse_pos_widget = None
        self.update()
        super().leaveEvent(event)
