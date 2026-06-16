"""Canvas overlay rendering for bbox annotations.

Pure function. Caller passes the QPainter and the canvas's Viewport;
image-coord box geometry is converted to widget coords here.
"""

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor

from labeling_tool.core.canvas.viewport import Viewport
from labeling_tool.core.bbox.oriented_box import OrientedBox


_BOX_UNSEL   = QColor(255, 200,  60, 220)   # yellow line
_BOX_SEL     = QColor(255, 165,  20, 255)   # orange line, thicker
_HANDLE      = QColor(255, 255, 255, 255)
_HANDLE_EDGE = QColor( 30,  30,  30, 255)
_INPROG_POINT = QColor( 60, 200, 255, 255)  # cyan
_INPROG_LINE  = QColor( 60, 200, 255, 180)

_HANDLE_SIZE_PX = 5


def paint_bboxes(
    painter: QPainter, viewport: Viewport,
    boxes: list[OrientedBox], selected_idx: int | None,
    in_progress_clicks: list,
    rot_offset_image_px: float = 30.0,
) -> None:
    """Draw box outlines + handles on selected + in-progress click preview.

    rot_offset_image_px: distance from top edge midpoint to rotation grip,
    in IMAGE pixels. Caller should pass (30 / viewport.scale) so the grip
    sits ~30 widget pixels above the box regardless of zoom.
    """
    # 1. Box outlines
    for i, b in enumerate(boxes):
        cor = b.corners()
        pts = [QPointF(*viewport.image_to_widget(float(x), float(y)))
               for x, y in cor]
        pen = QPen(_BOX_SEL if i == selected_idx else _BOX_UNSEL,
                   3 if i == selected_idx else 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        for j in range(4):
            painter.drawLine(pts[j], pts[(j + 1) % 4])

    # 2. Handles on the selected box
    if (selected_idx is not None
            and 0 <= selected_idx < len(boxes)):
        b = boxes[selected_idx]
        hs = b.handles(rot_offset_px=rot_offset_image_px)
        # Connector from top edge midpoint to rotation grip
        tmid = QPointF(*viewport.image_to_widget(*hs["t"]))
        rgrip = QPointF(*viewport.image_to_widget(*hs["rot"]))
        painter.setPen(QPen(_BOX_SEL, 1))
        painter.drawLine(tmid, rgrip)
        # 9 handles
        for name, (hx, hy) in hs.items():
            wx, wy = viewport.image_to_widget(float(hx), float(hy))
            painter.setBrush(QBrush(_HANDLE))
            painter.setPen(QPen(_HANDLE_EDGE, 1))
            r = _HANDLE_SIZE_PX
            if name == "rot":
                painter.drawEllipse(QPointF(wx, wy), r, r)
            else:
                painter.drawRect(int(wx - r), int(wy - r), 2 * r, 2 * r)

    # 3. In-progress click preview
    if in_progress_clicks:
        widget_pts = [
            QPointF(*viewport.image_to_widget(float(x), float(y)))
            for x, y in in_progress_clicks
        ]
        painter.setPen(QPen(_INPROG_LINE, 1, Qt.DashLine))
        for i in range(1, len(widget_pts)):
            painter.drawLine(widget_pts[i - 1], widget_pts[i])
        painter.setBrush(QBrush(_INPROG_POINT))
        painter.setPen(QPen(_HANDLE_EDGE, 1))
        for p in widget_pts:
            painter.drawEllipse(p, 4, 4)
