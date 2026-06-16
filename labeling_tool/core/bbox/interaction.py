"""BBox click-to-add + select-and-edit state machine.

ImageCanvas dispatches mouse events to this class when bbox_mode is on.
This class owns the boxes list, the in-progress click buffer, the current
selection, and the active drag.
"""

import math

from labeling_tool.core.bbox.oriented_box import OrientedBox


class BBoxInteraction:
    def __init__(self):
        self.boxes: list[OrientedBox] = []
        self.in_progress_clicks: list[tuple[float, float]] = []
        self.selected_idx: int | None = None
        # Drag state
        self.dragging: str | None = None    # None / 'body' / 'tl'/'t'/.../'rot'
        self._anchor_image: tuple[float, float] | None = None
        self._initial_box: OrientedBox | None = None

    # ---------------- mouse ----------------
    def on_left_press(self, ix: float, iy: float,
                      hit_tol_image_px: float = 10.0,
                      rot_offset_image_px: float = 30.0) -> bool:
        """Returns True if state changed (caller should repaint).

        Both tolerance and rotation-grip offset are in IMAGE pixels;
        caller is expected to scale them with the current viewport so the
        on-screen click target and grip position match what's rendered.
        """
        # 1. If a box is currently selected, check handle hit first
        if (self.selected_idx is not None
                and 0 <= self.selected_idx < len(self.boxes)):
            handle = self.boxes[self.selected_idx].hit_test_handle(
                ix, iy, tol_px=hit_tol_image_px,
                rot_offset_px=rot_offset_image_px)
            if handle is not None:
                self.dragging = handle
                self._anchor_image = (ix, iy)
                self._initial_box = OrientedBox(
                    **self.boxes[self.selected_idx].__dict__)
                return True
        # 2. Hit-test against all boxes' bodies (top-most first = newest)
        for i in reversed(range(len(self.boxes))):
            if self.boxes[i].contains(ix, iy):
                self.selected_idx = i
                self.dragging = "body"
                self._anchor_image = (ix, iy)
                self._initial_box = OrientedBox(**self.boxes[i].__dict__)
                return True
        # 3. Otherwise this click is a new point
        self.in_progress_clicks.append((float(ix), float(iy)))
        self.selected_idx = None
        return True

    def on_mouse_drag(self, ix: float, iy: float) -> bool:
        if self.dragging is None or self.selected_idx is None:
            return False
        if self._initial_box is None or self._anchor_image is None:
            return False
        box = self.boxes[self.selected_idx]
        ax, ay = self._anchor_image
        ib = self._initial_box

        if self.dragging == "body":
            box.cx = ib.cx + (ix - ax)
            box.cy = ib.cy + (iy - ay)
            return True

        if self.dragging == "rot":
            dx, dy = ix - box.cx, iy - box.cy
            # Atan2 gives angle from +x axis; rotation grip is "up" (=-y in box
            # local frame), so adding 90 brings the grip-direction to the
            # box's local x-axis convention used by OrientedBox.angle_deg.
            box.angle_deg = math.degrees(math.atan2(dy, dx)) + 90.0
            return True

        # Resize via 4 corners or 4 edge mids: transform pointer to box local
        # frame using the INITIAL box's center & angle, then adjust local-frame
        # min/max bounds depending on which handle is being dragged.
        rad = math.radians(ib.angle_deg)
        c, s = math.cos(-rad), math.sin(-rad)
        # current pointer in local frame (around initial center)
        lx = (ix - ib.cx) * c - (iy - ib.cy) * s
        ly = (ix - ib.cx) * s + (iy - ib.cy) * c
        # initial bounds: [-w/2, w/2] x [-h/2, h/2]
        hw, hh = ib.w / 2, ib.h / 2
        x_min, x_max = -hw, hw
        y_min, y_max = -hh, hh
        h = self.dragging
        if "l" in h: x_min = lx
        if "r" in h: x_max = lx
        if "t" in h: y_min = ly
        if "b" in h: y_max = ly
        # Clamp to >= 1 px in either dimension to avoid collapse
        if x_max - x_min < 1.0:
            if "l" in h: x_min = x_max - 1.0
            else:        x_max = x_min + 1.0
        if y_max - y_min < 1.0:
            if "t" in h: y_min = y_max - 1.0
            else:        y_max = y_min + 1.0
        new_w = x_max - x_min
        new_h = y_max - y_min
        # New local center
        local_cx = (x_min + x_max) / 2.0
        local_cy = (y_min + y_max) / 2.0
        # Transform local center back to image coords with INITIAL angle
        rad2 = math.radians(ib.angle_deg)
        c2, s2 = math.cos(rad2), math.sin(rad2)
        box.cx = ib.cx + local_cx * c2 - local_cy * s2
        box.cy = ib.cy + local_cx * s2 + local_cy * c2
        box.w = new_w
        box.h = new_h
        return True

    def on_release(self) -> bool:
        was = self.dragging is not None
        self.dragging = None
        self._anchor_image = None
        self._initial_box = None
        return was

    # ---------------- keyboard ----------------
    def commit(self, padding_px: float) -> bool:
        """Build a new box from accumulated clicks. Returns True on success."""
        if len(self.in_progress_clicks) < 2:
            return False
        self.boxes.append(
            OrientedBox.from_clicks(self.in_progress_clicks, padding_px)
        )
        self.in_progress_clicks = []
        self.selected_idx = len(self.boxes) - 1
        return True

    def cancel(self) -> bool:
        """Esc: cancel in-progress points OR deselect. Returns True if something changed."""
        if self.in_progress_clicks:
            self.in_progress_clicks = []
            return True
        if self.selected_idx is not None:
            self.selected_idx = None
            return True
        return False

    def delete_selected(self) -> bool:
        if self.selected_idx is None:
            return False
        del self.boxes[self.selected_idx]
        self.selected_idx = None
        return True

    def clear_for_image_switch(self) -> None:
        """Reset interaction state but keep selected/dragging cleared. The
        boxes list itself is loaded fresh by the caller after this call."""
        self.in_progress_clicks = []
        self.selected_idx = None
        self.dragging = None
        self._anchor_image = None
        self._initial_box = None

    def hit_test(self, ix: float, iy: float,
                 hit_tol_image_px: float = 10.0,
                 rot_offset_image_px: float = 30.0
                 ) -> tuple[str, object]:
        """Non-mutating hit test for hover cursor feedback.

        Returns ('handle', handle_name) if the selected box's handle is
        under (ix, iy); ('body', box_idx) if a body is hit; ('none', None)
        otherwise.
        """
        if (self.selected_idx is not None
                and 0 <= self.selected_idx < len(self.boxes)):
            h = self.boxes[self.selected_idx].hit_test_handle(
                ix, iy, tol_px=hit_tol_image_px,
                rot_offset_px=rot_offset_image_px)
            if h is not None:
                return ("handle", h)
        for i in reversed(range(len(self.boxes))):
            if self.boxes[i].contains(ix, iy):
                return ("body", i)
        return ("none", None)
