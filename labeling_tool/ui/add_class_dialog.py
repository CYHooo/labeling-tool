"""Ask for a new damage class: a name and a colour (pre-picked)."""

from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QPushButton,
)

MAX_NAME_LEN = 50


class AddClassDialog(QDialog):
    def __init__(self, color: str, tr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("class_add_title"))
        self._color = color
        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_NAME_LEN)
        self.name_edit.setPlaceholderText(tr("class_add_name_hint"))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        self._show_color()
        form.addRow(tr("class_add_name"), self.name_edit)
        form.addRow(tr("class_add_color"), self.color_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.name_edit.textChanged.connect(self._update_ok)
        self._update_ok()

    def name(self) -> str:
        return self.name_edit.text().strip()

    def color(self) -> str:
        return self._color

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.name()))

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self)
        if chosen.isValid():
            self._color = chosen.name().upper()
            self._show_color()

    def _show_color(self) -> None:
        self.color_button.setText(self._color)
        self.color_button.setStyleSheet(
            f"background-color: {self._color}; color: #101010;")
