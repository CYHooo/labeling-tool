"""Button and label icons for the dark theme.

The SVGs in labeling_tool/resources/icons are Lucide line icons drawn in
`currentColor`; Qt's SVG renderer has no notion of that, so each file is
recolored here before rasterizing. They live in the app layer, so adding or
changing an icon reaches installed users through the update zip.
"""

from __future__ import annotations

import re
from functools import lru_cache

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon, QPixmap

from labeling_tool.core.app_paths import resource_path

# Matches QPushButton's text color in core/window/styles.py.
THEME_COLOR = "#e0e0e0"
PRIMARY_COLOR = "#ffffff"
DISABLED_COLOR = "#5a5f66"
ICON_SIZE = QSize(16, 16)


def _svg(name: str, color: str, px: int) -> bytes:
    """The SVG recolored and sized to px: the files say 24x24, and drawing
    at 24 then shrinking to 16 left jagged edges. The viewBox stays 24, so
    the drawing scales exactly. Empty when the file is missing."""
    try:
        text = resource_path(f"icons/{name}.svg").read_text(encoding="utf-8")
    except OSError:
        return b""
    text = re.sub(r'\b(width|height)="24"', lambda m: f'{m.group(1)}="{px}"', text)
    return text.replace("currentColor", color).encode("utf-8")


def _render(name: str, color: str, px: int) -> QPixmap:
    """Null when the file is missing or the SVG plugin is absent: a blank
    icon, never a crash (the selftest catches the plugin case)."""
    pm = QPixmap()
    data = _svg(name, color, px)
    if data:
        pm.loadFromData(data, "SVG")
    return pm


@lru_cache(maxsize=None)
def icon(name: str, primary: bool = False) -> QIcon:
    """`name` is a file in resources/icons without .svg. Primary icons are
    white, for the blue primaryAction buttons."""
    result = QIcon()
    color = PRIMARY_COLOR if primary else THEME_COLOR
    for px in (16, 18, 24, 32, 48):
        result.addPixmap(_render(name, color, px), QIcon.Normal)
        result.addPixmap(_render(name, DISABLED_COLOR, px), QIcon.Disabled)
    return result


def pixmap(name: str, px: int = 16) -> QPixmap:
    """For QLabel decorations (section titles, status lines)."""
    return icon(name).pixmap(px, px)
