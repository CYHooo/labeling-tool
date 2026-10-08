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

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QButtonGroup, QListWidget, QSpinBox, QSlider, QScrollArea, QCheckBox,
    QStyle, QStyledItemDelegate, QToolButton, QDialog, QSizePolicy, QGridLayout,
    QFrame,
)

from labeling_tool.ui import icons
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
_SECONDARY_COLOR = QColor(140, 140, 140)
_SECONDARY_SELECTED_COLOR = QColor(215, 225, 245)   # readable on the blue highlight
_SELECTED_TEXT_COLOR = QColor(255, 255, 255)        # QListWidget::item:selected
_PART_GAP = 10


class TwoPartItemDelegate(QStyledItemDelegate):
    """Paints a list row as its text (in the item's own foreground, so the
    edited/labeled status colours still apply) followed by a smaller, grey
    SECONDARY_TEXT_ROLE part elided to the remaining width. The second parts
    start in one column: fit_primary_column() sizes it to the widest id."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._primary_width = 0

    def fit_primary_column(self, texts, font) -> None:
        metrics = QFontMetrics(font)
        self._primary_width = max(
            (metrics.horizontalAdvance(t) for t in texts), default=0)

    def primary_column_width(self) -> int:
        return self._primary_width

    def text_left(self, view) -> int:
        """x where a row's text starts, in the view's viewport coordinates."""
        option = view.viewOptions()
        option.rect = QRect(0, 0, view.viewport().width(), 20)
        option.text = "x"
        option.features |= option.HasDisplay
        style = view.style()
        return style.subElementRect(QStyle.SE_ItemViewItemText, option, view).left()

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
        # initStyleOption copied the item's status colour into palette Text;
        # a selected row is white on the highlight, as the stylesheet had it.
        painter.setPen(_SELECTED_TEXT_COLOR if selected
                       else option.palette.color(QPalette.Text))
        primary_width = max(option.fontMetrics.horizontalAdvance(primary),
                            self._primary_width)
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, primary)

        # Copy: option.font is shared with the view's other rows, so shrinking
        # it in place made every later row smaller still.
        small = QFont(option.font)
        if option.font.pointSizeF() > 0:
            small.setPointSizeF(max(option.font.pointSizeF() - 1.5, 6.0))
        else:                                   # pixel-sized font
            small.setPixelSize(max(option.font.pixelSize() - 2, 8))
        painter.setFont(small)
        painter.setPen(_SECONDARY_SELECTED_COLOR if selected
                       else _SECONDARY_COLOR)
        rest = rect.adjusted(primary_width + _PART_GAP, 0, 0, 0)
        elided = painter.fontMetrics().elidedText(
            secondary, Qt.ElideMiddle, max(rest.width(), 0))
        painter.drawText(rest, Qt.AlignLeft | Qt.AlignVCenter, elided)
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
    TwoPartItemDelegate uses for the id and the file name."""

    def __init__(self, view: QListWidget, parent=None):
        super().__init__(parent)
        self._view = view
        self._labels = ("", "")
        self.setObjectName("listHeader")
        self.setFixedHeight(QFontMetrics(view.font()).height() + 8)

    def labels(self) -> tuple[str, str]:
        return self._labels

    def set_labels(self, number: str, file: str) -> None:
        self._labels = (number, file)
        self.update()

    def column_offsets(self) -> tuple[int, int]:
        """x of the id and file-name columns, in this widget's coordinates."""
        delegate = self._view.itemDelegate()
        viewport_x = self._view.viewport().mapTo(self.window(), QPoint(0, 0)).x()
        own_x = self.mapTo(self.window(), QPoint(0, 0)).x()
        number_x = viewport_x - own_x + delegate.text_left(self._view)
        return number_x, number_x + delegate.primary_column_width() + _PART_GAP

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self._view.font())
        painter.setPen(_SECONDARY_COLOR)
        number_x, file_x = self.column_offsets()
        rect = self.rect()
        painter.drawText(rect.adjusted(number_x, 0, 0, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, self._labels[0])
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
    hint = QLabel(window.tr_(hint_key))
    hint.setObjectName("toolHint")
    hint.setWordWrap(True)
    lay.addWidget(hint)
    window._tool_texts.append((title, title_key, hint, hint_key))
    return page, lay


def _build_brush_options(window: "MainWindow", lay: QVBoxLayout) -> None:
    cat_row = QHBoxLayout()
    window._btn_cat_crack = _checkable(QPushButton(window.tr_("cat_crack")))
    window._btn_cat_crack.setObjectName("catCrack")
    window._btn_cat_spalling = _checkable(QPushButton(window.tr_("cat_spalling")))
    window._btn_cat_spalling.setObjectName("catSpalling")
    window._cat_group = QButtonGroup(window)
    window._cat_group.setExclusive(True)
    window._cat_group.addButton(window._btn_cat_crack, 0)
    window._cat_group.addButton(window._btn_cat_spalling, 1)
    window._btn_cat_crack.setChecked(True)
    window._cat_group.idClicked.connect(window._on_category_changed)
    cat_row.addWidget(window._btn_cat_crack)
    cat_row.addWidget(window._btn_cat_spalling)
    lay.addLayout(cat_row)

    size_row = QHBoxLayout()
    window._lbl_brush_size = QLabel(window.tr_("lbl_brush_size"))
    window._sld_brush_size = QSlider(Qt.Horizontal)
    window._sld_brush_size.setRange(1, BRUSH_MAX_SIZE)
    window._sld_brush_size.setValue(BRUSH_DEFAULT_SIZE)
    window._spn_brush_size = QSpinBox()
    window._spn_brush_size.setRange(1, BRUSH_MAX_SIZE)
    window._spn_brush_size.setValue(BRUSH_DEFAULT_SIZE)
    window._spn_brush_size.setFixedWidth(60)
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


def _build_sam_options(window: "MainWindow", lay: QVBoxLayout) -> None:
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
    window._lbl_scale = QLabel(
        window.tr_("lbl_scale_template", scale="--",
                   source=window.tr_("scale_source_none")))
    window._lbl_scale.setObjectName("scaleLabel")
    window._lbl_scale.setWordWrap(True)
    window._btn_measure = QPushButton(window.tr_("btn_measure"))
    window._btn_measure.setIcon(icons.icon("ruler"))
    window._btn_measure.setObjectName("measureToggle")
    window._btn_measure.setCheckable(True)
    window._btn_measure.toggled.connect(window._on_measure_toggle)
    window._btn_measure.toggled.connect(window._sync_tool)
    scale_row.addWidget(window._lbl_scale, 1)
    scale_row.addWidget(window._btn_measure)
    gd.addLayout(scale_row)
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
    return dlg
