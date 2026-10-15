"""Builders for the labeling window's right-side panel.

Each builder receives the MainWindow instance, creates its widgets,
attaches them as attributes on the window, wires signal connections, and
returns the widget so build_side_panel can lay them out:

    job line (job id, inspection name, photo count; a "?" help button)
    image list with a column header, then previous / next photo / save
    edit tools: 2x2 tool picker (the selected tool = the mode), its how-to
    and options; then display toggles and the scale
    pinned bottom: the Viewer window's upload button
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QButtonGroup, QListWidget, QSpinBox, QSlider, QScrollArea, QCheckBox,
    QStyle, QStyledItemDelegate, QToolButton, QDialog, QSizePolicy, QGridLayout,
    QFrame, QToolTip,
)

from labeling_tool.core import i18n
from labeling_tool.ui import icons
from labeling_tool.core.window.shortcuts import keep_shortcuts_through
from labeling_tool.core.window.class_picker import ClassPicker
from labeling_tool.core.window.surface_row import SurfaceRow
from labeling_tool.core.constants import BRUSH_DEFAULT_SIZE, BRUSH_MAX_SIZE

if TYPE_CHECKING:
    from labeling_tool.core.window.main_window import MainWindow


# Uniform inner padding/spacing for every control group, so the side panel
# reads as one consistent stack instead of each group using ad-hoc margins.
_GROUP_MARGINS = (10, 14, 10, 10)
_GROUP_SPACING = 6

# Item data role holding the dim second part of an image-list row (the file
# name behind the "<job>-<photo>" id). Empty/None -> the row is one part only.
SECONDARY_TEXT_ROLE = Qt.UserRole + 1
# Item data role holding a row's upload mark: "uploaded" (✓), "pending" (●)
# or None. Drawn in its own narrow column before the id when the delegate's
# mark_width is set.
MARK_ROLE = Qt.UserRole + 2
_MARKS = {"uploaded": ("✓", QColor(92, 200, 122)),
          "pending": ("●", QColor(240, 181, 74))}
# Item data roles for the Viewer window's surface column and delete button
# (drawn only when the delegate's surface_width / delete_width are set):
# the surface text shown in the "면" column (e.g. "벽"), whether that value
# was changed here (amber), and whether the photo is marked for deletion
# (struck-through red file name + "삭제 예정", red trash icon).
SURFACE_ROLE = Qt.UserRole + 3
SURFACE_EDITED_ROLE = Qt.UserRole + 4
DELETE_PENDING_ROLE = Qt.UserRole + 5
_SURFACE_EDITED_COLOR = QColor("#e0a040")
_DELETE_COLOR = QColor("#e05a5a")
_SECONDARY_COLOR = QColor(140, 140, 140)
_SECONDARY_SELECTED_COLOR = QColor(215, 225, 245)   # readable on the blue highlight
_SELECTED_TEXT_COLOR = QColor(255, 255, 255)        # QListWidget::item:selected
_PART_GAP = 10


def _tinted(pixmap: QPixmap, colour: QColor) -> QPixmap:
    """The pixmap's shape filled with one colour (for the red trash icon)."""
    result = QPixmap(pixmap)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), colour)
    painter.end()
    return result


class TwoPartItemDelegate(QStyledItemDelegate):
    """Paints a list row as its text (in the item's own foreground, so the
    edited/labeled status colours still apply) followed by a smaller, grey
    SECONDARY_TEXT_ROLE part elided to the remaining width. The second parts
    start in one column: fit_primary_column() sizes it to the widest id.

    Optional columns, each off while its width is 0 (the default):
      mark_width     MARK_ROLE (✓ / ●) before the id
      surface_width  SURFACE_ROLE after the id (amber when SURFACE_EDITED_ROLE)
      delete_width   a trash button at the row's right end; a left press on
                     it emits delete_clicked(row) and is swallowed, so the
                     current row does not change. Every press counts, the
                     second press of a double-click too (it arrives as
                     MouseButtonDblClick), so two fast clicks toggle twice.
                     Until that button is released, mouse moves and the
                     release are swallowed as well: otherwise a shaky click
                     starts a drag-selection that switches the photo.
                     DELETE_PENDING_ROLE rows are drawn red with the file
                     name struck through."""

    delete_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._primary_width = 0
        self.mark_width = 0          # > 0: a column for MARK_ROLE before the id
        self.surface_width = 0       # > 0: a "면" column after the id
        self.delete_width = 0        # > 0: a delete button at the row's end
        self._held_viewport = None   # viewport where a delete press is held

    def fit_primary_column(self, texts, font) -> None:
        metrics = QFontMetrics(font)
        self._primary_width = max(
            (metrics.horizontalAdvance(t) for t in texts), default=0)

    def primary_column_width(self) -> int:
        return self._primary_width

    def fit_surface_column(self, texts, font) -> None:
        """Turn the surface column on, as wide as the widest of `texts` (the
        surface names and the column title)."""
        metrics = QFontMetrics(font)
        self.surface_width = max(
            (metrics.horizontalAdvance(t) for t in texts), default=0)

    def text_left(self, view) -> int:
        """x where a row's text starts, in the view's viewport coordinates."""
        option = view.viewOptions()
        option.rect = QRect(0, 0, view.viewport().width(), 20)
        option.text = "x"
        option.features |= option.HasDisplay
        style = view.style()
        return style.subElementRect(QStyle.SE_ItemViewItemText, option, view).left()

    def _delete_rect(self, row_rect: QRect) -> QRect:
        return QRect(row_rect.right() - self.delete_width + 1, row_rect.top(),
                     self.delete_width, row_rect.height())

    def editorEvent(self, event, model, option, index):
        if (self.delete_width > 0 and index.isValid()
                and event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick)
                and event.button() == Qt.LeftButton
                and self._delete_rect(option.rect).contains(event.pos())):
            self._hold_press(option.widget)
            self.delete_clicked.emit(index.row())
            return True      # swallowed: the selection stays where it was
        return super().editorEvent(event, model, option, index)

    def _hold_press(self, view) -> None:
        """Swallow the view's mouse moves and the release that follow a
        press on the delete button (see eventFilter)."""
        viewport = view.viewport() if view is not None else None
        if viewport is None:
            return
        if self._held_viewport is not viewport:
            viewport.installEventFilter(self)   # once per viewport; idempotent
        self._held_viewport = viewport

    def eventFilter(self, obj, event):
        if obj is self._held_viewport:
            if event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
                return True
            if (event.type() == QEvent.MouseButtonRelease
                    and event.button() == Qt.LeftButton):
                self._held_viewport = None
                obj.removeEventFilter(self)
                return True
        return super().eventFilter(obj, event)

    def helpEvent(self, event, view, option, index):
        if (self.delete_width > 0 and index.isValid()
                and event.type() == QEvent.ToolTip
                and self._delete_rect(option.rect).contains(event.pos())):
            QToolTip.showText(event.globalPos(), i18n.tr("delete_toggle_tip"), view)
            return True
        return super().helpEvent(event, view, option, index)

    def paint(self, painter, option, index):
        secondary = index.data(SECONDARY_TEXT_ROLE)
        if not secondary:
            super().paint(painter, option, index)
            return
        self.initStyleOption(option, index)
        primary = option.text
        option.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is None:
            super().paint(painter, option, index)
            return
        style.drawControl(QStyle.CE_ItemViewItem, option, painter, widget)

        rect = style.subElementRect(QStyle.SE_ItemViewItemText, option, widget)
        painter.save()
        painter.setFont(option.font)
        selected = bool(option.state & QStyle.State_Selected)
        pending = self.delete_width > 0 and bool(index.data(DELETE_PENDING_ROLE))
        if self.mark_width:
            kind = index.data(MARK_ROLE)
            mark = _MARKS.get(kind)
            if mark is not None:
                colour = _SELECTED_TEXT_COLOR if selected else mark[1]
                if kind == "pending":
                    # drawn, not a glyph: fonts fall back to a large emoji dot
                    d = max(6, option.fontMetrics.height() // 3)
                    cy = rect.center().y()
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(colour)
                    painter.drawEllipse(rect.left() + 2, cy - d // 2, d, d)
                else:
                    painter.setPen(colour)
                    painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, mark[0])
            rect = rect.adjusted(self.mark_width, 0, 0, 0)
        if self.delete_width:
            rect.setRight(min(rect.right(), self._delete_rect(option.rect).left() - 2))
        # initStyleOption copied the item's status colour into palette Text;
        # a selected row is white on the highlight, as the stylesheet had it.
        if selected:
            text_colour = _SELECTED_TEXT_COLOR
        elif pending:
            text_colour = _DELETE_COLOR
        else:
            text_colour = option.palette.color(QPalette.Text)
        painter.setPen(text_colour)
        primary_width = max(option.fontMetrics.horizontalAdvance(primary),
                            self._primary_width)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, primary)
        rest = rect.adjusted(primary_width + _PART_GAP, 0, 0, 0)

        if self.surface_width:
            surface = index.data(SURFACE_ROLE) or ""
            if selected or pending:
                painter.setPen(text_colour)
            elif index.data(SURFACE_EDITED_ROLE):
                painter.setPen(_SURFACE_EDITED_COLOR)
            else:
                painter.setPen(text_colour)
            # Elide only what is really too wide: elidedText() compares in
            # fractional widths, so a text exactly as wide as the column (as
            # fit_surface_column() makes it) would lose its last letters.
            metrics = painter.fontMetrics()
            if metrics.horizontalAdvance(surface) > self.surface_width:
                surface = metrics.elidedText(surface, Qt.ElideRight, self.surface_width)
            cell = QRect(rest.left(), rest.top(), self.surface_width + 2, rest.height())
            painter.drawText(cell, Qt.AlignLeft | Qt.AlignVCenter, surface)
            rest = rest.adjusted(self.surface_width + _PART_GAP, 0, 0, 0)

        # Copy: option.font is shared with the view's other rows, so shrinking
        # it in place made every later row smaller still.
        small = QFont(option.font)
        if option.font.pointSizeF() > 0:
            small.setPointSizeF(max(option.font.pointSizeF() - 1.5, 6.0))
        else:                                   # pixel-sized font
            small.setPixelSize(max(option.font.pixelSize() - 2, 8))
        if pending:
            label = i18n.tr("delete_pending_label")
            label_width = QFontMetrics(small).horizontalAdvance(label)
            name_font = QFont(small)
            name_font.setStrikeOut(True)
            painter.setFont(name_font)
            painter.setPen(text_colour)
            name_room = max(rest.width() - label_width - _PART_GAP, 0)
            elided = painter.fontMetrics().elidedText(secondary, Qt.ElideMiddle, name_room)
            painter.drawText(rest, Qt.AlignLeft | Qt.AlignVCenter, elided)
            painter.setFont(small)
            label_x = rest.left() + painter.fontMetrics().horizontalAdvance(elided) + _PART_GAP
            painter.drawText(QRect(label_x, rest.top(), max(rest.right() - label_x + 1, 0),
                                   rest.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, label)
        else:
            painter.setFont(small)
            painter.setPen(_SECONDARY_SELECTED_COLOR if selected
                           else _SECONDARY_COLOR)
            elided = painter.fontMetrics().elidedText(
                secondary, Qt.ElideMiddle, max(rest.width(), 0))
            painter.drawText(rest, Qt.AlignLeft | Qt.AlignVCenter, elided)

        if self.delete_width:
            box = self._delete_rect(option.rect)
            side = min(16, box.width(), box.height())
            pixmap = icons.icon("trash-2").pixmap(side, side)
            if pending:
                pixmap = _tinted(pixmap, _SELECTED_TEXT_COLOR if selected
                                 else _DELETE_COLOR)
            elif not selected:
                pixmap = _tinted(pixmap, _SECONDARY_COLOR)
            painter.drawPixmap(box.center().x() - side // 2 + 1,
                               box.center().y() - side // 2 + 1, pixmap)
        painter.restore()


def _tidy_group_layout(layout) -> None:
    layout.setContentsMargins(*_GROUP_MARGINS)
    layout.setSpacing(_GROUP_SPACING)


class ElidedLabel(QLabel):
    """One-line label that ends in "…" when its text does not fit; the full
    text stays in full_text() and the tooltip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(40)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(
            self._full, Qt.ElideRight, max(self.width(), 0)))


class ListHeader(QWidget):
    """Column titles over the image list, drawn at the x positions the
    TwoPartItemDelegate uses for the id, the surface column (when the
    delegate has one and a title was given) and the file name."""

    def __init__(self, view: QListWidget, parent=None):
        super().__init__(parent)
        self._view = view
        self._labels = ("", "")
        self._surface_label = ""
        self.setObjectName("listHeader")
        self.setFixedHeight(QFontMetrics(view.font()).height() + 8)

    def labels(self) -> tuple[str, str]:
        return self._labels

    def surface_label(self) -> str:
        return self._surface_label

    def set_labels(self, number: str, file: str, surface: str = "") -> None:
        """The surface title is drawn only when given and the delegate has a
        surface column; labels() stays (number, file)."""
        self._labels = (number, file)
        self._surface_label = surface
        self.update()

    def column_offsets(self) -> tuple[int, int, int]:
        """x of the id, surface and file-name columns, in this widget's
        coordinates. Without a surface column, surface x == file-name x."""
        delegate = self._view.itemDelegate()
        viewport_x = self._view.viewport().mapTo(self.window(), QPoint(0, 0)).x()
        own_x = self.mapTo(self.window(), QPoint(0, 0)).x()
        number_x = viewport_x - own_x + delegate.text_left(self._view) + delegate.mark_width
        surface_x = number_x + delegate.primary_column_width() + _PART_GAP
        surface_width = getattr(delegate, "surface_width", 0)
        file_x = surface_x + (surface_width + _PART_GAP if surface_width else 0)
        return number_x, surface_x, file_x

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self._view.font())
        painter.setPen(_SECONDARY_COLOR)
        number_x, surface_x, file_x = self.column_offsets()
        rect = self.rect()
        painter.drawText(rect.adjusted(number_x, 0, 0, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, self._labels[0])
        if self._surface_label and file_x > surface_x:
            painter.drawText(rect.adjusted(surface_x, 0, 0, 0),
                             Qt.AlignLeft | Qt.AlignVCenter, self._surface_label)
        painter.drawText(rect.adjusted(file_x, 0, 0, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, self._labels[1])
        painter.setPen(QColor(58, 64, 72))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())


def _checkable(button: QPushButton, height: int = 32) -> QPushButton:
    button.setCheckable(True)
    button.setMinimumHeight(height)
    return button


def build_job_info_row(window: "MainWindow") -> QWidget:
    """Job id, inspection name and photo count on one line, and the
    shortcut-help button.
    The text comes from window._refresh_job_info()."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(4, 0, 0, 0)
    window._lbl_job_info = ElidedLabel()
    window._lbl_job_info.setObjectName("jobInfoLine")
    window._btn_help = QToolButton()
    window._btn_help.setIcon(icons.icon("circle-help"))
    window._btn_help.setAutoRaise(True)
    window._btn_help.setToolTip(window.tr_("group_hint"))
    window._btn_help.clicked.connect(window._show_help)
    lay.addWidget(window._lbl_job_info, 1)
    lay.addWidget(window._btn_help)
    window._refresh_job_info()
    return row


def build_list_group(window: "MainWindow") -> QGroupBox:
    """Image list (with a column header) and, under it, the navigation row."""
    window._grp_list = QGroupBox(window.tr_("group_list"))
    gl = QVBoxLayout(window._grp_list)
    _tidy_group_layout(gl)
    gl.setSpacing(0)
    window.file_list = QListWidget()
    window.file_list.setItemDelegate(TwoPartItemDelegate(window.file_list))
    window.file_list.currentRowChanged.connect(window._on_list_row_changed)
    # About four rows: on a short screen the list gives way to the tools
    # instead of pushing the panel into scrolling.
    window.file_list.setMinimumHeight(120)
    # and no preferred height of its own: it takes whatever is left
    window.file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
    window._list_header = ListHeader(window.file_list)
    gl.addWidget(window._list_header)
    gl.addWidget(window.file_list, 1)
    gl.addSpacing(_GROUP_SPACING + 2)

    nav_row = QHBoxLayout()
    window.btn_prev = QPushButton(window.tr_("btn_prev"))
    window.btn_prev.setIcon(icons.icon("chevron-left"))
    window.btn_next = QPushButton(window.tr_("btn_next"))
    window.btn_next.setIcon(icons.icon("chevron-right"))
    window.btn_next.setLayoutDirection(Qt.RightToLeft)   # chevron after the text
    window.btn_save = QPushButton(window.tr_("btn_save"))
    window.btn_save.setIcon(icons.icon("save", primary=True))
    window.btn_save.setObjectName("primaryAction")
    window.btn_prev.clicked.connect(window.go_prev)
    window.btn_next.clicked.connect(window.go_next)
    window.btn_save.clicked.connect(window._on_brush_save)
    nav_row.addWidget(window.btn_prev)
    nav_row.addWidget(window.btn_next)
    nav_row.addWidget(window.btn_save)
    gl.addLayout(nav_row)
    window._refresh_list_header()
    return window._grp_list


def _build_mode_toggles(window: "MainWindow", parent: QWidget) -> None:
    """The brush / SAM / repair-area mode switches. Never shown: the tool
    picker drives them, and they stay the single record of the active mode
    (their handlers keep the modes exclusive; B and X toggle them)."""
    window._btn_brush_toggle = QPushButton(window.tr_("btn_brush_on"), parent)
    window._btn_brush_toggle.setIcon(icons.icon("brush"))
    window._btn_brush_toggle.setCheckable(True)
    window._btn_brush_toggle.toggled.connect(window._on_brush_toggle)
    window._btn_sam_toggle = QPushButton(window.tr_("btn_sam"), parent)
    window._btn_sam_toggle.setIcon(icons.icon("wand-sparkles"))
    window._btn_sam_toggle.setCheckable(True)
    window._btn_sam_toggle.toggled.connect(window._on_sam_toggle)
    window._btn_bbox_toggle = QPushButton(window.tr_("btn_bbox_on"), parent)
    window._btn_bbox_toggle.setIcon(icons.icon("scan"))
    window._btn_bbox_toggle.setCheckable(True)
    window._btn_bbox_toggle.toggled.connect(window._on_bbox_toggle)
    for btn in (window._btn_brush_toggle, window._btn_sam_toggle, window._btn_bbox_toggle):
        btn.hide()
        btn.toggled.connect(window._sync_tool)


TOOL_VIEW, TOOL_BRUSH, TOOL_SAM, TOOL_BBOX = range(4)
_TOOL_ICONS = ("eye", "brush", "wand-sparkles", "scan")


class ToolPicker(QWidget):
    """Four large tool buttons in a 2x2 grid (one checked at a time) and,
    under them, the selected tool's page: its name, how to use it, and its
    options. Only the current page takes space, so the picker's height
    follows the selected tool.

    currentChanged(int) fires when the user picks a tool; a disabled tool
    cannot be picked."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._pages: list[QWidget] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_clicked)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_GROUP_SPACING)
        self._grid = QGridLayout()
        self._grid.setSpacing(_GROUP_SPACING)
        lay.addLayout(self._grid)
        self._pages_layout = QVBoxLayout()
        self._pages_layout.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._pages_layout)
        self._current = 0

    def add_tool(self, text: str, page: QWidget) -> None:
        idx = len(self._buttons)
        btn = QPushButton(text)
        btn.setObjectName("toolButton")
        btn.setCheckable(True)
        btn.setIconSize(QSize(18, 18))
        btn.setFixedHeight(38)
        self._group.addButton(btn, idx)
        self._grid.addWidget(btn, idx // 2, idx % 2)
        self._buttons.append(btn)
        self._pages.append(page)
        self._pages_layout.addWidget(page)
        if idx == 0:
            btn.setChecked(True)
        self._show(self._current)

    # -- the QTabWidget-like surface MainWindow uses
    def count(self) -> int:
        return len(self._buttons)

    def button(self, idx: int) -> QPushButton:
        return self._buttons[idx]

    def current_page(self) -> QWidget:
        return self._pages[self._current]

    def currentIndex(self) -> int:
        return self._current

    def setCurrentIndex(self, idx: int) -> None:
        if not (0 <= idx < self.count()) or idx == self._current:
            return
        if not self._buttons[idx].isEnabled():
            return
        self._show(idx)
        if not self.signalsBlocked():
            self.currentChanged.emit(idx)

    def toolText(self, idx: int) -> str:
        return self._buttons[idx].text()

    def setToolText(self, idx: int, text: str) -> None:
        self._buttons[idx].setText(text)

    def isToolEnabled(self, idx: int) -> bool:
        return self._buttons[idx].isEnabled()

    def setToolEnabled(self, idx: int, enabled: bool) -> None:
        """Disabling the current tool does not move the selection: the
        caller ends that tool's mode and re-selects (see
        MainWindow._refresh_tools)."""
        self._buttons[idx].setEnabled(enabled)

    def toolToolTip(self, idx: int) -> str:
        return self._buttons[idx].toolTip()

    def setToolToolTip(self, idx: int, tip: str) -> None:
        self._buttons[idx].setToolTip(tip)

    def _on_clicked(self, idx: int) -> None:
        # A user click always reports (the picker is only blocked while the
        # window syncs it, which no click can interrupt).
        if idx != self._current:
            self._show(idx)
            self.currentChanged.emit(idx)

    def _show(self, idx: int) -> None:
        self._current = idx
        self._buttons[idx].setChecked(True)
        for i, (btn, page) in enumerate(zip(self._buttons, self._pages)):
            btn.setIcon(icons.icon(_TOOL_ICONS[i], primary=(i == idx)))
            # hidden pages take no space: the picker is as tall as this page
            page.setVisible(i == idx)


class WrappedLabel(QLabel):
    """Word-wrapped label that asks its layout for the height its text
    really needs at the current width. A plain wrapped QLabel inside a box
    whose height follows its size hint got the one-width estimate, so a
    three-line hint was squeezed into two and overlapped."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def _fit_height(self) -> None:
        need = self.heightForWidth(self.width()) if self.width() > 0 else -1
        if need > 0 and need != self.minimumHeight():
            self.setMinimumHeight(need)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def setText(self, text: str) -> None:
        super().setText(text)
        self._fit_height()


def _tool_page(window: "MainWindow", title_key: str, hint_key: str) -> tuple[QWidget, QVBoxLayout]:
    """A tool page: "── name ───" heading and a how-to line; the caller
    adds the options to the returned layout."""
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(_GROUP_SPACING)
    head = QHBoxLayout()
    title = QLabel(window.tr_(title_key))
    title.setObjectName("toolTitle")
    rule = QFrame()
    rule.setFrameShape(QFrame.HLine)
    rule.setObjectName("toolRule")
    head.addWidget(title)
    head.addWidget(rule, 1)
    lay.addLayout(head)
    hint = WrappedLabel(window.tr_(hint_key))
    hint.setObjectName("toolHint")
    lay.addWidget(hint)
    window._tool_texts.append((title, title_key, hint, hint_key))
    return page, lay


def _build_brush_options(window: "MainWindow", lay: QVBoxLayout) -> None:
    window._class_picker_brush = ClassPicker(window.tr_("lbl_class"))
    window._class_picker_brush.classChosen.connect(window._set_current_class)
    window._class_picker_brush.addRequested.connect(window._on_add_class)
    lay.addWidget(window._class_picker_brush)

    size_row = QHBoxLayout()
    window._lbl_brush_size = QLabel(window.tr_("lbl_brush_size"))
    window._sld_brush_size = QSlider(Qt.Horizontal)
    window._sld_brush_size.setRange(1, BRUSH_MAX_SIZE)
    window._sld_brush_size.setValue(BRUSH_DEFAULT_SIZE)
    window._spn_brush_size = QSpinBox()
    window._spn_brush_size.setRange(1, BRUSH_MAX_SIZE)
    window._spn_brush_size.setValue(BRUSH_DEFAULT_SIZE)
    window._spn_brush_size.setFixedWidth(60)
    keep_shortcuts_through(window._spn_brush_size)
    window._sld_brush_size.valueChanged.connect(window._spn_brush_size.setValue)
    window._spn_brush_size.valueChanged.connect(window._sld_brush_size.setValue)
    window._spn_brush_size.valueChanged.connect(window._on_brush_size_changed)
    size_row.addWidget(window._lbl_brush_size)
    size_row.addWidget(window._sld_brush_size, stretch=1)
    size_row.addWidget(window._spn_brush_size)
    lay.addLayout(size_row)

    action_row = QHBoxLayout()
    window._chk_fine_annotation = QCheckBox(window.tr_("btn_fine_annotation"))
    window._chk_fine_annotation.toggled.connect(window._on_fine_annotation_toggle)
    window._btn_brush_reset = QPushButton(window.tr_("btn_brush_reset"))
    window._btn_brush_reset.setIcon(icons.icon("rotate-ccw"))
    window._btn_brush_reset.clicked.connect(window._on_brush_reset)
    action_row.addWidget(window._chk_fine_annotation, 1)
    action_row.addWidget(window._btn_brush_reset)
    lay.addLayout(action_row)

    undo_row = QHBoxLayout()
    window._btn_undo = QPushButton(window.tr_("btn_undo"))
    window._btn_undo.setIcon(icons.icon("undo-2"))
    window._btn_undo.clicked.connect(window._on_undo)
    window._btn_redo = QPushButton(window.tr_("btn_redo"))
    window._btn_redo.setIcon(icons.icon("redo-2"))
    window._btn_redo.clicked.connect(window._on_redo)
    for btn in (window._btn_undo, window._btn_redo):
        btn.setEnabled(False)
        undo_row.addWidget(btn)
    lay.addLayout(undo_row)


def _build_sam_options(window: "MainWindow", lay: QVBoxLayout) -> None:
    window._class_picker_sam = ClassPicker(window.tr_("lbl_class"))
    window._class_picker_sam.classChosen.connect(window._set_current_class)
    window._class_picker_sam.addRequested.connect(window._on_add_class)
    lay.addWidget(window._class_picker_sam)
    window._btn_sam_commit = QPushButton(window.tr_("btn_sam_commit"))
    window._btn_sam_commit.setIcon(icons.icon("check"))
    window._btn_sam_commit.clicked.connect(window._on_sam_commit)
    window._btn_sam_cancel = QPushButton(window.tr_("btn_sam_cancel"))
    window._btn_sam_cancel.setIcon(icons.icon("x"))
    window._btn_sam_cancel.clicked.connect(window._on_sam_cancel)
    window._btn_sam_undo = QPushButton(window.tr_("btn_sam_undo"))
    window._btn_sam_undo.setIcon(icons.icon("undo-2"))
    window._btn_sam_undo.clicked.connect(window._on_sam_undo)
    for btn in (window._btn_sam_commit, window._btn_sam_cancel, window._btn_sam_undo):
        btn.setEnabled(False)
    # Confirm on its own row: the three did not fit side by side in English.
    lay.addWidget(window._btn_sam_commit)
    row = QHBoxLayout()
    row.addWidget(window._btn_sam_cancel)
    row.addWidget(window._btn_sam_undo)
    lay.addLayout(row)


def build_tools_group(window: "MainWindow") -> QGroupBox:
    """Edit tools: the tool picker. The selected tool is the editing mode
    (the view tool = none); its page shows how to use it and its options."""
    window._grp_tools = QGroupBox(window.tr_("group_tools"))
    gt = QVBoxLayout(window._grp_tools)
    _tidy_group_layout(gt)
    _build_mode_toggles(window, window._grp_tools)

    window._tool_texts = []
    window._tool_picker = ToolPicker()
    for key, build_options in (("tool_view", None), ("tool_brush", _build_brush_options),
                               ("tool_sam", _build_sam_options), ("tool_bbox", None)):
        page, lay = _tool_page(window, key, key + "_hint")
        if build_options is not None:
            build_options(window, lay)
        window._tool_picker.add_tool(window.tr_(key), page)
    window._tool_picker.currentChanged.connect(window._on_tool_changed)
    gt.addWidget(window._tool_picker)
    # Only as tall as its contents: the image list takes the spare height.
    window._grp_tools.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    return window._grp_tools


def build_display_group(window: "MainWindow") -> QGroupBox:
    """Display and scale: what is drawn over the photo, and its scale."""
    window._grp_display = QGroupBox(window.tr_("group_display"))
    gd = QVBoxLayout(window._grp_display)
    _tidy_group_layout(gd)

    show_row = QHBoxLayout()
    window._chk_show_highlight = QCheckBox(window.tr_("btn_show_highlight"))
    window._chk_show_highlight.toggled.connect(window._on_toggle_highlight)
    window._chk_show_repair15 = QCheckBox(window.tr_("btn_show_repair15"))
    window._chk_show_repair15.toggled.connect(window._on_toggle_repair15)
    show_row.addWidget(window._chk_show_highlight)
    show_row.addWidget(window._chk_show_repair15)
    show_row.addStretch()
    gd.addLayout(show_row)

    scale_row = QHBoxLayout()
    window._lbl_scale = QLabel(window.tr_("lbl_scale", scale="--"))
    window._lbl_scale.setObjectName("scaleLabel")
    window._btn_measure = QPushButton(window.tr_("btn_measure"))
    window._btn_measure.setIcon(icons.icon("ruler"))
    window._btn_measure.setObjectName("measureToggle")
    window._btn_measure.setCheckable(True)
    window._btn_measure.toggled.connect(window._on_measure_toggle)
    window._btn_measure.toggled.connect(window._sync_tool)
    scale_row.addWidget(window._lbl_scale, 1)
    scale_row.addWidget(window._btn_measure)
    gd.addLayout(scale_row)

    # The Viewer window shows it (it has the photos' surfaces); hidden here.
    window._surface_row = SurfaceRow()
    window._surface_row.setVisible(False)
    gd.addWidget(window._surface_row)
    window._grp_display.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    return window._grp_display


def build_side_panel(window: "MainWindow") -> QWidget:
    """The right-side panel: job line, image list + navigation and the tools
    scroll together; window._panel_bottom_layout (for the upload button)
    stays pinned underneath."""
    panel = QWidget()
    panel.setObjectName("sidePanel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setSpacing(8)
    panel_layout.setContentsMargins(10, 8, 10, 6)
    panel_layout.addWidget(build_job_info_row(window))
    panel_layout.addWidget(build_list_group(window), stretch=1)
    panel_layout.addWidget(build_tools_group(window))
    panel_layout.addWidget(build_display_group(window))
    window._panel_layout = panel_layout

    panel_scroll = QScrollArea()
    panel_scroll.setWidget(panel)
    panel_scroll.setWidgetResizable(True)
    panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    panel_scroll.setFrameShape(QScrollArea.NoFrame)

    container = QWidget()
    container.setObjectName("sidePanel")
    outer = QVBoxLayout(container)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(panel_scroll, 1)
    bottom = QVBoxLayout()
    bottom.setContentsMargins(10, 4, 10, 10)
    bottom.setSpacing(4)
    outer.addLayout(bottom)
    window._panel_bottom_layout = bottom
    # Resizable instead of a hard-locked width: a min keeps controls legible,
    # a max stops the panel from eating the canvas, and the splitter handle
    # lets the user drag it.
    container.setMinimumWidth(340)
    container.setMaximumWidth(480)
    return container


def build_help_dialog(window: "MainWindow") -> QDialog:
    """Shortcut and mouse help, opened from the "?" button (non-modal)."""
    dlg = QDialog(window)
    dlg.setWindowTitle(window.tr_("group_hint"))
    lay = QVBoxLayout(dlg)
    window._lbl_hint = QLabel(window.tr_("hint_text"))
    window._lbl_hint.setObjectName("hintText")
    window._lbl_hint.setWordWrap(True)
    lay.addWidget(window._lbl_hint)
    row = QHBoxLayout()
    row.addStretch()
    window._btn_open_logs = QPushButton(window.tr_("btn_open_logs"))
    window._btn_open_logs.setIcon(icons.icon("folder-open"))
    window._btn_open_logs.setAutoDefault(False)
    window._btn_open_logs.clicked.connect(window._open_log_folder)
    row.addWidget(window._btn_open_logs)
    lay.addLayout(row)
    return dlg
