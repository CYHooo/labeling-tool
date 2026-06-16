"""ArUco-marker-based px/cm scale detection + session fallback tracker.

The reference marker is DICT_4X4_50 with a known physical outer black
border length of 7 cm. We report the mean of the four detected side
lengths divided by 7 as the px/cm scale.

ArUco auto-detection is the primary source of px/cm. Manual measurement
(scale_from_two_points) is only a fallback for when the marker cannot be
auto-detected in an image.
"""

import math

import numpy as np
import cv2


ARUCO_DICT = cv2.aruco.DICT_4X4_50
MARKER_PHYSICAL_CM = 7.0


def scale_from_two_points(p1, p2, physical_cm: float) -> float | None:
    """px/cm from a manually measured segment of known physical length.

    Fallback path when ArUco auto-detection fails: the user clicks the two
    ends of a known-length reference (e.g. a marker side, default 7 cm) and
    we divide the pixel distance by the physical length.
    """
    if physical_cm is None or physical_cm <= 0:
        return None
    dist = math.hypot(float(p2[0]) - float(p1[0]), float(p2[1]) - float(p1[1]))
    if dist <= 0:
        return None
    return dist / physical_cm


def detect_aruco(bgr: np.ndarray) -> tuple[float | None, np.ndarray | None]:
    """Detect the first ArUco marker.

    Returns:
        (scale_px_per_cm, corners_4x2)  when a marker is found.
        (None, None)                    otherwise.
    corners_4x2 is a float ndarray with the four detected corner points in
    image-pixel coordinates (TL, TR, BR, BL as OpenCV returns them).
    """
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    detector = cv2.aruco.ArucoDetector(
        dictionary, cv2.aruco.DetectorParameters()
    )
    corners, ids, _ = detector.detectMarkers(bgr)
    if ids is None or len(corners) == 0:
        return None, None
    c = corners[0][0]    # (4, 2) float32
    sides = [float(np.linalg.norm(c[i] - c[(i + 1) % 4])) for i in range(4)]
    scale = float(np.mean(sides)) / MARKER_PHYSICAL_CM
    return scale, c


def detect_aruco_scale(bgr: np.ndarray) -> float | None:
    """Backwards-compatible wrapper: scale only, no corners."""
    s, _ = detect_aruco(bgr)
    return s


class ScaleTracker:
    """Session-scoped px/cm scale state with fallback to most recent success."""

    def __init__(self):
        self.last_known_scale: float | None = None

    def update_for_image(
        self, bgr: np.ndarray
    ) -> tuple[float | None, str, np.ndarray | None]:
        """
        Returns (scale, source, corners) where:
            source in {'aruco', 'fallback', 'none'}
            corners is the 4x2 marker outline ONLY when source == 'aruco'
                (a fresh detection on this image); None otherwise so callers
                don't draw stale ArUco rectangles from a previous image.
        Mutates last_known_scale only on a fresh ArUco detection.
        """
        s, corners = detect_aruco(bgr)
        if s is not None:
            self.last_known_scale = s
            return s, "aruco", corners
        if self.last_known_scale is not None:
            return self.last_known_scale, "fallback", None
        return None, "none", None
