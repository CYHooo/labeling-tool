"""Global keyboard shortcut registration for MainWindow."""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence

if TYPE_CHECKING:
    from labeling_tool.core.window.main_window import MainWindow


def register_shortcuts(window: "MainWindow") -> None:
    """Wire up A/D/S/B/[ /]/1/2 global shortcuts on the main window."""
    QShortcut(QKeySequence("A"), window, window.go_prev)
    QShortcut(QKeySequence("D"), window, window.go_next)
    QShortcut(QKeySequence("S"), window, window._on_brush_save)
    QShortcut(QKeySequence("B"), window,
              lambda: window._btn_brush_toggle.toggle())
    QShortcut(QKeySequence("["), window, lambda: window._nudge_brush_size(-2))
    QShortcut(QKeySequence("]"), window, lambda: window._nudge_brush_size(+2))
    QShortcut(QKeySequence("1"), window,
              lambda: window._select_category_btn(0))
    QShortcut(QKeySequence("2"), window,
              lambda: window._select_category_btn(1))
    QShortcut(QKeySequence("X"), window,
              lambda: window._btn_bbox_toggle.toggle())
    QShortcut(QKeySequence(Qt.Key_Return), window, window._on_bbox_commit)
    QShortcut(QKeySequence(Qt.Key_Enter), window, window._on_bbox_commit)
    QShortcut(QKeySequence(Qt.Key_Escape), window, window._on_bbox_cancel)
    QShortcut(QKeySequence(Qt.Key_Delete), window, window._on_bbox_delete)
