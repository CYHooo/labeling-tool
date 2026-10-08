"""Global keyboard shortcut registration for MainWindow."""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import QShortcut, QAbstractSpinBox
from PyQt5.QtGui import QKeySequence

if TYPE_CHECKING:
    from labeling_tool.core.window.main_window import MainWindow


def register_shortcuts(window: "MainWindow") -> None:
    """Wire up A/D/S/B/[ /]/1/2 global shortcuts on the main window."""
    QShortcut(QKeySequence("A"), window, window.go_prev)
    QShortcut(QKeySequence("D"), window, window.go_next)
    QShortcut(QKeySequence("S"), window, window._on_brush_save)
    QShortcut(QKeySequence("Ctrl+S"), window, window._on_brush_save)
    QShortcut(QKeySequence("Ctrl+Z"), window, window._on_undo)
    QShortcut(QKeySequence("Ctrl+Y"), window, window._on_redo)
    QShortcut(QKeySequence("Ctrl+Shift+Z"), window, window._on_redo)
    QShortcut(QKeySequence("B"), window,
              lambda: window._toggle_mode_shortcut(window._btn_brush_toggle))
    QShortcut(QKeySequence("["), window, lambda: window._nudge_brush_size(-2))
    QShortcut(QKeySequence("]"), window, lambda: window._nudge_brush_size(+2))
    QShortcut(QKeySequence("1"), window,
              lambda: window._select_category_btn(0))
    QShortcut(QKeySequence("2"), window,
              lambda: window._select_category_btn(1))
    QShortcut(QKeySequence("X"), window,
              lambda: window._toggle_mode_shortcut(window._btn_bbox_toggle))
    QShortcut(QKeySequence(Qt.Key_Return), window, window._on_bbox_commit)
    QShortcut(QKeySequence(Qt.Key_Enter), window, window._on_bbox_commit)
    QShortcut(QKeySequence(Qt.Key_Escape), window, window._on_escape)
    QShortcut(QKeySequence(Qt.Key_Delete), window, window._on_bbox_delete)


class _LetterShortcutsPassThrough(QObject):
    """Lets a number box hand letter keys to the window's single-key
    shortcuts (A / D / S / B / X ..., [ / ] for the brush size, and Ctrl+Z /
    Ctrl+Y for undoing strokes). A focused QSpinBox otherwise claims
    every printable key -- and with an input method (pinyin, hangul) turns
    it into composition -- so after adjusting the brush size the shortcuts
    seemed gone. Digits, arrows and editing keys still reach the box."""

    def eventFilter(self, obj, event):
        if event.type() != QEvent.ShortcutOverride:
            return False
        key, mods = event.key(), event.modifiers()
        letter = (Qt.Key_A <= key <= Qt.Key_Z
                  or key in (Qt.Key_BracketLeft, Qt.Key_BracketRight))
        plain = not mods & ~Qt.ShiftModifier
        # the box's own text undo must not shadow undoing a stroke
        undo_redo = (key in (Qt.Key_Z, Qt.Key_Y)
                     and mods & Qt.ControlModifier
                     and not mods & ~(Qt.ControlModifier | Qt.ShiftModifier))
        if (letter and plain) or undo_redo:
            event.ignore()               # not ours: let the shortcut fire
            return True
        return False


def keep_shortcuts_through(box: QAbstractSpinBox) -> None:
    """Number entry only: no input method, and letters go to shortcuts."""
    keeper = _LetterShortcutsPassThrough(box)
    for widget in (box, box.lineEdit()):
        widget.setAttribute(Qt.WA_InputMethodEnabled, False)
        widget.installEventFilter(keeper)
