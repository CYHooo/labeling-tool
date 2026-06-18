"""GroupBox builder functions for the right-side control panel.

Each builder receives the MainWindow instance, creates its widgets,
attaches them as attributes on the window (keeping the exact same names
the original monolithic _build_ui used), wires signal connections, and
returns the QGroupBox so MainWindow can lay them out.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QComboBox, QButtonGroup, QListWidget, QSpinBox, QSlider, QScrollArea,
    QCheckBox, QShortcut,
)

from labeling_tool.core.constants import BRUSH_DEFAULT_SIZE, BRUSH_MAX_SIZE
from labeling_tool.core.i18n import LANG_DISPLAY_NAMES

if TYPE_CHECKING:
    from labeling_tool.core.window.main_window import MainWindow


# Uniform inner padding/spacing for every control group, so the side panel
# reads as one consistent stack instead of each group using ad-hoc margins.
_GROUP_MARGINS = (10, 14, 10, 10)
_GROUP_SPACING = 6


def _tidy_group_layout(layout) -> None:
    layout.setContentsMargins(*_GROUP_MARGINS)
    layout.setSpacing(_GROUP_SPACING)


def build_settings_group(window: "MainWindow") -> QGroupBox:
    window._grp_settings = QGroupBox(window.tr_("settings"))
    gs = QVBoxLayout(window._grp_settings)
    _tidy_group_layout(gs)

    lang_row = QHBoxLayout()
    window._lbl_lang = QLabel(window.tr_("language") + ":")
    window._cmb_lang = QComboBox()
    for code, display in LANG_DISPLAY_NAMES.items():
        window._cmb_lang.addItem(display, code)
    window._cmb_lang.setCurrentIndex(
        list(LANG_DISPLAY_NAMES.keys()).index(window.lang))
    window._cmb_lang.currentIndexChanged.connect(window._change_language)
    lang_row.addWidget(window._lbl_lang)
    lang_row.addWidget(window._cmb_lang, stretch=1)
    gs.addLayout(lang_row)

    folder_row = QHBoxLayout()
    window._btn_select_origin = QPushButton(window.tr_("btn_select_origin"))
    window._btn_select_detected = QPushButton(window.tr_("btn_select_detected"))
    window._btn_select_origin.clicked.connect(window._select_origin_folder)
    window._btn_select_detected.clicked.connect(window._select_detected_folder)
    folder_row.addWidget(window._btn_select_origin)
    folder_row.addWidget(window._btn_select_detected)
    gs.addLayout(folder_row)

    window._lbl_origin_path = QLabel()
    window._lbl_detected_path = QLabel()
    window._lbl_output_path = QLabel()
    for lbl in (window._lbl_origin_path,
                window._lbl_detected_path,
                window._lbl_output_path):
        lbl.setObjectName("pathLabel")
        lbl.setWordWrap(True)
        gs.addWidget(lbl)
    window._refresh_path_labels()
    return window._grp_settings


def build_category_group(window: "MainWindow") -> QGroupBox:
    window._grp_category = QGroupBox(window.tr_("lbl_category"))
    gc = QHBoxLayout(window._grp_category)
    _tidy_group_layout(gc)
    window._btn_cat_crack = QPushButton(window.tr_("cat_crack"))
    window._btn_cat_spalling = QPushButton(window.tr_("cat_spalling"))
    window._btn_cat_crack.setObjectName("catCrack")
    window._btn_cat_spalling.setObjectName("catSpalling")
    for btn in (window._btn_cat_crack, window._btn_cat_spalling):
        btn.setCheckable(True)
        btn.setMinimumHeight(32)
    window._cat_group = QButtonGroup(window)
    window._cat_group.setExclusive(True)
    window._cat_group.addButton(window._btn_cat_crack, 0)
    window._cat_group.addButton(window._btn_cat_spalling, 1)
    window._btn_cat_crack.setChecked(True)
    window._cat_group.idClicked.connect(window._on_category_changed)
    gc.addWidget(window._btn_cat_crack)
    gc.addWidget(window._btn_cat_spalling)
    return window._grp_category


def build_brush_group(window: "MainWindow") -> QGroupBox:
    window._grp_brush = QGroupBox(window.tr_("group_brush"))
    gbr = QVBoxLayout(window._grp_brush)
    _tidy_group_layout(gbr)

    window._btn_brush_toggle = QPushButton(window.tr_("btn_brush_on"))
    window._btn_brush_toggle.setObjectName("brushToggle")
    window._btn_brush_toggle.setCheckable(True)
    window._btn_brush_toggle.setMinimumHeight(36)
    window._btn_brush_toggle.toggled.connect(window._on_brush_toggle)
    gbr.addWidget(window._btn_brush_toggle)

    window._lbl_brush_size = QLabel(window.tr_("lbl_brush_size"))
    gbr.addWidget(window._lbl_brush_size)

    size_row = QHBoxLayout()
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
    size_row.addWidget(window._sld_brush_size, stretch=1)
    size_row.addWidget(window._spn_brush_size)
    gbr.addLayout(size_row)

    window._chk_fine_annotation = QCheckBox(window.tr_("btn_fine_annotation"))
    window._chk_fine_annotation.toggled.connect(window._on_fine_annotation_toggle)
    gbr.addWidget(window._chk_fine_annotation)

    action_row = QHBoxLayout()
    window._btn_brush_reset = QPushButton(window.tr_("btn_brush_reset"))
    window._btn_brush_save = QPushButton(window.tr_("btn_brush_save"))
    window._btn_brush_save.setObjectName("primaryAction")
    window._btn_brush_reset.clicked.connect(window._on_brush_reset)
    window._btn_brush_save.clicked.connect(window._on_brush_save)
    action_row.addWidget(window._btn_brush_reset)
    action_row.addWidget(window._btn_brush_save)
    gbr.addLayout(action_row)

    window._btn_sam_toggle = QPushButton(window.tr_("btn_sam"))
    window._btn_sam_toggle.setObjectName("samToggle")
    window._btn_sam_toggle.setCheckable(True)
    window._btn_sam_toggle.toggled.connect(window._on_sam_toggle)
    window._btn_sam_commit = QPushButton(window.tr_("btn_sam_commit"))
    window._btn_sam_commit.clicked.connect(window._on_sam_commit)
    window._btn_sam_cancel = QPushButton(window.tr_("btn_sam_cancel"))
    window._btn_sam_cancel.clicked.connect(window._on_sam_cancel)
    window._btn_sam_undo = QPushButton(window.tr_("btn_sam_undo"))
    window._btn_sam_undo.clicked.connect(window._on_sam_undo)
    window._btn_sam_commit.setEnabled(False)
    window._btn_sam_cancel.setEnabled(False)
    window._btn_sam_undo.setEnabled(False)
    gbr.addWidget(window._btn_sam_toggle)
    sam_row = QHBoxLayout()
    sam_row.addWidget(window._btn_sam_undo)
    sam_row.addWidget(window._btn_sam_commit)
    sam_row.addWidget(window._btn_sam_cancel)
    gbr.addLayout(sam_row)
    # ESC = undo the last SAM point (no-op outside SAM mode; guarded in handler)
    window._sam_undo_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), window)
    window._sam_undo_shortcut.activated.connect(window._on_sam_undo)
    return window._grp_brush


def build_scale_group(window: "MainWindow") -> QGroupBox:
    """Scale (px/cm): ArUco auto-detection readout + manual-measure fallback."""
    window._grp_scale = QGroupBox(window.tr_("group_scale"))
    gscale = QVBoxLayout(window._grp_scale)
    _tidy_group_layout(gscale)

    window._lbl_scale = QLabel(
        window.tr_("lbl_scale_template", scale="--",
                   source=window.tr_("scale_source_none")))
    window._lbl_scale.setObjectName("scaleLabel")
    window._lbl_scale.setWordWrap(True)
    window._lbl_scale.setAlignment(Qt.AlignCenter)
    gscale.addWidget(window._lbl_scale)

    window._btn_measure = QPushButton(window.tr_("btn_measure"))
    window._btn_measure.setObjectName("measureToggle")
    window._btn_measure.setCheckable(True)
    window._btn_measure.toggled.connect(window._on_measure_toggle)
    gscale.addWidget(window._btn_measure)
    return window._grp_scale


def build_bbox_group(window: "MainWindow") -> QGroupBox:
    window._grp_bbox = QGroupBox(window.tr_("group_bbox"))
    gb = QVBoxLayout(window._grp_bbox)
    _tidy_group_layout(gb)

    window._btn_bbox_toggle = QPushButton(window.tr_("btn_bbox_on"))
    window._btn_bbox_toggle.setObjectName("bboxToggle")
    window._btn_bbox_toggle.setCheckable(True)
    window._btn_bbox_toggle.setMinimumHeight(36)
    window._btn_bbox_toggle.toggled.connect(window._on_bbox_toggle)
    gb.addWidget(window._btn_bbox_toggle)

    window._btn_show_highlight = QPushButton(window.tr_("btn_show_highlight"))
    window._btn_show_highlight.setObjectName("showHighlightToggle")
    window._btn_show_highlight.setCheckable(True)
    window._btn_show_highlight.setMinimumHeight(32)
    window._btn_show_highlight.toggled.connect(window._on_toggle_highlight)
    gb.addWidget(window._btn_show_highlight)

    window._btn_show_repair15 = QPushButton(window.tr_("btn_show_repair15"))
    window._btn_show_repair15.setObjectName("showRepair15Toggle")
    window._btn_show_repair15.setCheckable(True)
    window._btn_show_repair15.setMinimumHeight(32)
    window._btn_show_repair15.toggled.connect(window._on_toggle_repair15)
    gb.addWidget(window._btn_show_repair15)

    return window._grp_bbox


def build_list_group(window: "MainWindow") -> QGroupBox:
    window._grp_list = QGroupBox(window.tr_("group_list"))
    gl = QVBoxLayout(window._grp_list)
    _tidy_group_layout(gl)
    window.file_list = QListWidget()
    window.file_list.currentRowChanged.connect(window._on_list_row_changed)
    gl.addWidget(window.file_list)
    return window._grp_list


def build_nav_group(window: "MainWindow") -> QGroupBox:
    window._grp_nav = QGroupBox(window.tr_("group_nav"))
    gn = QVBoxLayout(window._grp_nav)
    _tidy_group_layout(gn)
    nav_row = QHBoxLayout()
    window.btn_prev = QPushButton(window.tr_("btn_prev"))
    window.btn_next = QPushButton(window.tr_("btn_next"))
    window.btn_prev.clicked.connect(window.go_prev)
    window.btn_next.clicked.connect(window.go_next)
    nav_row.addWidget(window.btn_prev)
    nav_row.addWidget(window.btn_next)
    gn.addLayout(nav_row)
    window.btn_save = QPushButton(window.tr_("btn_save"))
    window.btn_save.setObjectName("primaryAction")
    window.btn_save.clicked.connect(window._on_brush_save)
    gn.addWidget(window.btn_save)
    return window._grp_nav


def build_hint_group(window: "MainWindow") -> QGroupBox:
    window._grp_hint = QGroupBox(window.tr_("group_hint"))
    gh = QVBoxLayout(window._grp_hint)
    _tidy_group_layout(gh)
    window._lbl_hint = QLabel(window.tr_("hint_text"))
    window._lbl_hint.setObjectName("hintText")
    window._lbl_hint.setWordWrap(True)
    gh.addWidget(window._lbl_hint)
    return window._grp_hint


def build_side_panel(window: "MainWindow") -> QScrollArea:
    """Compose the entire right-side panel and wrap it in a QScrollArea."""
    panel = QWidget()
    panel.setObjectName("sidePanel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setSpacing(10)
    panel_layout.setContentsMargins(10, 10, 10, 10)

    title = QLabel(window.tr_("window_title"))
    title.setObjectName("appTitle")
    title.setAlignment(Qt.AlignCenter)
    panel_layout.addWidget(title)
    window._lbl_app_title = title

    # Rationalized order: connection/folders, then the image list + navigation
    # (the things used most), then scale (incl. manual-measure fallback), then
    # the editing tools, and finally one consolidated help block at the bottom.
    panel_layout.addWidget(build_settings_group(window))
    panel_layout.addWidget(build_list_group(window), stretch=3)
    panel_layout.addWidget(build_nav_group(window))
    panel_layout.addWidget(build_scale_group(window))
    panel_layout.addWidget(build_category_group(window))
    panel_layout.addWidget(build_brush_group(window))
    panel_layout.addWidget(build_bbox_group(window))
    panel_layout.addWidget(build_hint_group(window))   # consolidated, bottom
    window._panel_layout = panel_layout
    panel_layout.addStretch()

    panel_scroll = QScrollArea()
    panel_scroll.setWidget(panel)
    panel_scroll.setWidgetResizable(True)
    panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    # Resizable instead of a hard-locked 320px: a min keeps controls legible,
    # a max stops the panel from eating the canvas, and the splitter handle
    # lets the user drag it. Fixes long-button text clipping and the layout
    # jumping around when the window is resized.
    panel_scroll.setMinimumWidth(330)
    panel_scroll.setMaximumWidth(480)
    panel_scroll.setFrameShape(QScrollArea.NoFrame)
    return panel_scroll
