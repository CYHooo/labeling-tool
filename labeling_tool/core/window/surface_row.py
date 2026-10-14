"""The shooting-surface row of the display / scale group.

    Surface [Unknown] [Floor][Wall][Ceiling]      87°

Three checkable buttons show the photo's current surface; none is checked
when the surface is unknown (None or any value other than floor / wall /
ceiling), and the "unknown" text is shown in front of them instead. The
tilt angle is grey text: the server's tiltDeg rounded, or a dash without one.

The row decides nothing itself: set_value() shows a value without emitting
anything, and a click only reports the chosen surface (surfaceChosen); the
window keeps the record and calls set_value() back.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from labeling_tool.core import i18n

SURFACES = ("floor", "wall", "ceiling")
_TEXT_KEYS = {"floor": "surface_floor", "wall": "surface_wall",
              "ceiling": "surface_ceiling"}


class SurfaceRow(QWidget):
    """label, unknown, buttons[floor / wall / ceiling], tilt."""

    surfaceChosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._surface: str | None = None
        self._edited = False
        self._tilt_deg: float | None = None
        self._tilt_source: str | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.label = QLabel()
        self.label.setObjectName("surfaceLabel")
        self.unknown = QLabel()
        self.unknown.setObjectName("surfaceUnknown")
        lay.addWidget(self.label)
        lay.addSpacing(4)
        lay.addWidget(self.unknown)
        self.buttons: dict[str, QPushButton] = {}
        for key in SURFACES:
            button = QPushButton()
            button.setObjectName("surfaceButton")
            button.setCheckable(True)
            button.setProperty("edited", False)
            # As narrow as their text: the row must fit the 340 px panel.
            button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            # Bind the key now; `clicked` passes `checked` as the first arg.
            button.clicked.connect(lambda _checked=False, k=key: self._on_clicked(k))
            self.buttons[key] = button
            lay.addWidget(button)
        lay.addStretch(1)
        self.tilt = QLabel()
        self.tilt.setObjectName("tiltLabel")
        lay.addWidget(self.tilt)

        self.retranslate(i18n.tr)
        self._show()

    # ------------------------------------------------------------ public
    def set_value(self, surface: str | None, edited: bool,
                  tilt_deg: float | None, tilt_source: str | None) -> None:
        """Show a photo's surface and tilt. Emits nothing."""
        self._surface = surface if surface in SURFACES else None
        self._edited = bool(edited)
        self._tilt_deg = tilt_deg
        self._tilt_source = tilt_source
        self._show()

    def retranslate(self, tr: Callable[..., str]) -> None:
        self._tr = tr
        self.label.setText(tr("surface_label"))
        self.unknown.setText(tr("surface_unknown"))
        for key, button in self.buttons.items():
            button.setText(tr(_TEXT_KEYS[key]))
        self._show_tilt()

    # ------------------------------------------------------------ internals
    def _on_clicked(self, key: str) -> None:
        # Optimistic: show the choice at once (and keep a re-clicked button
        # checked); the window answers with set_value() for the real state.
        for other, button in self.buttons.items():
            button.setChecked(other == key)
        self.surfaceChosen.emit(key)

    def _show(self) -> None:
        for key, button in self.buttons.items():
            button.setChecked(key == self._surface)
            if button.property("edited") != self._edited:
                button.setProperty("edited", self._edited)
                # dynamic property: the stylesheet only re-reads it on polish
                button.style().unpolish(button)
                button.style().polish(button)
        self.unknown.setVisible(self._surface is None)
        self._show_tilt()

    def _show_tilt(self) -> None:
        tr = self._tr
        if self._tilt_deg is None:
            self.tilt.setText(tr("tilt_none"))
        else:
            self.tilt.setText(tr("tilt_deg", deg=round(self._tilt_deg)))
        self.tilt.setToolTip(tr("tilt_manual_tip")
                             if self._tilt_source == "manual" else "")
