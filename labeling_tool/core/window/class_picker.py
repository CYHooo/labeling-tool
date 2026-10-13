"""Class picker for the brush and SAM pages: a drop-down of the damage
classes (colour swatch, number key, name) and a "+" to add one."""

from __future__ import annotations

from PyQt5.QtCore import QSize, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget,
)

from labeling_tool.ui import icons


def _swatch(rgb: tuple[int, int, int]) -> QIcon:
    """A small solid square in the class colour."""
    pm = QPixmap(12, 12)
    pm.fill(QColor(*rgb))
    return QIcon(pm)


class ClassPicker(QWidget):
    """Label, drop-down and "+" in one row.

    classChosen(cid) fires only for a user choice in the drop-down;
    set_classes / set_current never emit, so the window can keep two
    pickers in step without loops.
    """

    classChosen = pyqtSignal(int)
    addRequested = pyqtSignal()

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label_text)
        self.combo = QComboBox()
        self.combo.setIconSize(QSize(12, 12))
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Long user names must not widen the 340 px panel.
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(8)
        self.add_button = QToolButton()
        self.add_button.setIcon(icons.icon("plus"))
        lay.addWidget(self.label)
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.add_button)
        self.combo.currentIndexChanged.connect(self._on_index)
        self.add_button.clicked.connect(self.addRequested)

    def set_classes(self, entries, current: int, disabled=frozenset()) -> None:
        """entries: (class id, shown name, rgb) in list order. The first
        nine carry their number key; ids in `disabled` are listed greyed."""
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            for i, (cid, name, rgb) in enumerate(entries):
                text = f"{i + 1}  {name}" if i < 9 else f"    {name}"
                self.combo.addItem(_swatch(rgb), text, cid)
                if cid in disabled:
                    self.combo.model().item(i).setEnabled(False)
            self.combo.setCurrentIndex(max(0, self.combo.findData(current)))
        finally:
            self.combo.blockSignals(False)

    def set_current(self, cid: int) -> None:
        idx = self.combo.findData(cid)
        if idx >= 0 and idx != self.combo.currentIndex():
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(idx)
            self.combo.blockSignals(False)

    def current_class(self) -> int:
        return int(self.combo.currentData())

    def set_add_enabled(self, enabled: bool, tip: str) -> None:
        self.add_button.setEnabled(enabled)
        self.add_button.setToolTip(tip)

    def retranslate(self, label: str) -> None:
        self.label.setText(label)

    def _on_index(self, idx: int) -> None:
        if idx >= 0:
            self.classChosen.emit(int(self.combo.itemData(idx)))
