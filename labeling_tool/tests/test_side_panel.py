"""Labeling window side columns. Left, collapsible (button / L) and
resizable: one-line job info with a help button, image list with a header,
one navigation row with a single save. Right: a 2x2 tool picker where the
selected tool IS the editing mode (its how-to and options below it), a
display/scale group, and the upload button pinned to the bottom."""
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QLabel, QMessageBox, QPushButton, QScrollArea, QWidget,
)

from labeling_tool.core import i18n
from labeling_tool.core.window import ui_builder
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session.workspace import Workspace
from labeling_tool.ui.main_window import ViewerMainWindow

_app = QApplication.instance() or QApplication([])

_FILES = ("stitched_100.jpg", "stitched_200.jpg")
VIEW, BRUSH, SAM, BBOX = range(4)


def _make_window(tmp_path, monkeypatch, *, inspection_name: str | None = "교량 정기점검",
                 sam_available=True, second_photo_scale=2.0, synced=(), files=_FILES,
                 focus=None, settings_home=None):
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    home = settings_home if settings_home is not None else tmp_path / "settings"
    monkeypatch.setattr(i18n, "_settings_home", lambda: home)
    i18n.set_language("ko")
    from labeling_tool.core.sam import predictor as sam_predictor
    monkeypatch.setattr(sam_predictor.MobileSamPredictor, "try_load",
                        classmethod(lambda cls: object() if sam_available else None))
    ws = Workspace(root=tmp_path, session_id=45)
    ws.origin_dir.mkdir(parents=True)
    manifest = Manifest(session_id=45, base="", inspection_name=inspection_name)
    for num, name in enumerate(files, start=1):
        cv2.imwrite(str(ws.origin_dir / name), np.zeros((8, 8, 3), np.uint8))
        manifest.add(PhotoEntry(filename=name, timestamp=num, photo_id=num,
                                report_photo_num=num,
                                px_per_cm=2.0 if num == 1 else second_photo_scale,
                                synced=name in synced))
    win = ViewerMainWindow(ws, manifest, None, focus=focus)
    win.resize(1400, 900)
    win.show()
    QApplication.processEvents()
    return win


# ---------------------------------------------------------------- job info
def test_job_info_is_two_lines_with_a_help_button(tmp_path, monkeypatch):
    # line 1: job id and photo count (collapse button left, "?" right);
    # line 2: the inspection name, elided at the right, full text as tooltip
    win = _make_window(tmp_path, monkeypatch)
    try:
        head = i18n.tr("job_info_head", job=45, count=i18n.tr("photo_count", n=2))
        assert win._lbl_job_info.full_text() == head
        assert win._lbl_job_name.full_text() == "교량 정기점검"
        assert win._lbl_job_name.toolTip() == "교량 정기점검"
        assert not win._btn_help.icon().isNull()

        def top(w):
            return w.mapTo(win, w.rect().topLeft())
        assert top(win._lbl_job_name).y() > top(win._lbl_job_info).y()
        assert abs(top(win._btn_help).y() - top(win._lbl_job_info).y()) <= 8
        assert top(win._btn_list_collapse).x() < top(win._lbl_job_info).x() < top(win._btn_help).x()
    finally:
        win.close()


def test_a_long_inspection_name_is_elided_at_the_right(tmp_path, monkeypatch):
    name = "아주 긴 점검 이름 " * 12
    win = _make_window(tmp_path, monkeypatch, inspection_name=name)
    try:
        _settle()
        shown = win._lbl_job_name.text()
        assert shown.endswith("…") and name.startswith(shown[:-1])
        assert win._lbl_job_name.toolTip() == name
    finally:
        win.close()


def test_job_info_without_a_name_shows_a_dash(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, inspection_name=None)
    try:
        assert win._lbl_job_name.full_text() == "—"
    finally:
        win.close()


def test_help_button_opens_the_shortcut_help(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._btn_help.click()
        dialogs = [w for w in QApplication.topLevelWidgets()
                   if isinstance(w, QDialog) and w.isVisible()]
        assert len(dialogs) == 1
        assert dialogs[0].windowTitle() == i18n.tr("group_hint")
        assert i18n.tr("hint_text") in [lbl.text() for lbl in dialogs[0].findChildren(QLabel)]
        dialogs[0].close()
    finally:
        win.close()


def test_the_old_title_and_help_block_are_gone(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert not hasattr(win, "_lbl_app_title")
        assert not hasattr(win, "_grp_hint")
        assert not hasattr(win, "_grp_job_info")
    finally:
        win.close()


# ---------------------------------------------------------------- list
def test_the_image_list_has_a_header(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        header = win._list_header
        assert header.labels() == (i18n.tr("list_col_number"), i18n.tr("list_col_file"))
        assert header.isVisible()
    finally:
        win.close()


def test_the_header_columns_line_up_with_the_rows(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        header = win._list_header
        delegate = win.file_list.itemDelegate()
        from PyQt5.QtCore import QPoint
        number_x, surface_x, file_x = header.column_offsets()
        viewport = win.file_list.viewport()

        def in_viewport(x):                  # header x -> list viewport x
            return header.mapTo(win, QPoint(x, 0)).x() - viewport.mapTo(win, QPoint(0, 0)).x()

        text_left = delegate.text_left(win.file_list) + delegate.mark_width   # after ✓ / ●
        assert delegate.mark_width > 0
        assert in_viewport(number_x) == text_left
        gap = ui_builder._PART_GAP
        assert in_viewport(surface_x) == text_left + delegate.primary_column_width() + gap
        assert in_viewport(file_x) == in_viewport(surface_x) + delegate.surface_width + gap
        # the id column is at least as wide as its header, so titles never overlap
        from PyQt5.QtGui import QFontMetrics
        assert delegate.primary_column_width() >= QFontMetrics(win.file_list.font()).horizontalAdvance(
            header.labels()[0])
    finally:
        win.close()


def test_the_surface_row_is_built_but_hidden_in_the_base_window(tmp_path, monkeypatch):
    from labeling_tool.core.window.main_window import MainWindow
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    try:
        assert win._surface_row.parent() is not None
        assert not win._surface_row.isVisible()
        assert win.file_list.itemDelegate().surface_width == 0
        assert win.file_list.itemDelegate().delete_width == 0
        assert win._list_header.surface_label() == ""
    finally:
        win.close()


def test_the_viewer_window_shows_the_surface_column_and_row_but_no_trash(tmp_path, monkeypatch):
    # Deleting photos was taken out (2026-10-15): no trash column, nothing
    # listens for a trash click.
    win = _make_window(tmp_path, monkeypatch)
    try:
        delegate = win.file_list.itemDelegate()
        assert win._surface_row.isVisible()
        assert delegate.delete_width == 0
        assert delegate.receivers(delegate.delete_clicked) == 0
        assert delegate.surface_width > 0
        assert win._list_header.surface_label() == i18n.tr("list_col_surface")
        number, file = win._list_header.labels()
        assert (number, file) == (i18n.tr("list_col_number"), i18n.tr("list_col_file"))
        assert not hasattr(win, "_on_delete_clicked")
    finally:
        win.close()


# ---------------------------------------------------------------- navigation
def test_one_navigation_row_with_a_single_save(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        # previous / next are icon-only; their tooltips name them and the key
        assert win.btn_prev.text() == "" and win.btn_next.text() == ""
        assert win.btn_prev.toolTip() == "이전 사진 (A)"
        assert win.btn_next.toolTip() == "다음 사진 (D)"
        assert win.btn_save.text() == i18n.tr("btn_save")
        assert not hasattr(win, "_btn_brush_save")
        saves = [b for b in win.findChildren(QPushButton)
                 if b.isVisible() and b.text() == i18n.tr("btn_save")]
        assert saves == [win.btn_save]
        y = {b.mapTo(win, b.rect().topLeft()).y() for b in (win.btn_prev, win.btn_next, win.btn_save)}
        assert len(y) == 1                                   # same row
        assert "S" in win.btn_save.toolTip()
    finally:
        win.close()


# ---------------------------------------------------------------- tool modes
def test_tools_are_view_brush_sam_and_repair_area(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        picker = win._tool_picker
        assert [picker.toolText(i) for i in range(picker.count())] == [
            i18n.tr("tool_view"), i18n.tr("tool_brush"), i18n.tr("tool_sam"), i18n.tr("tool_bbox")]
        assert picker.currentIndex() == VIEW
        assert not (win.canvas.brush_mode or win.canvas.sam_mode or win.canvas.bbox_mode)
    finally:
        win.close()


def test_choosing_a_tool_switches_the_mode(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        picker = win._tool_picker
        picker.setCurrentIndex(BRUSH)
        assert win.canvas.brush_mode and not win.canvas.sam_mode
        picker.setCurrentIndex(SAM)
        assert win.canvas.sam_mode and not win.canvas.brush_mode
        picker.setCurrentIndex(BBOX)
        assert win.canvas.bbox_mode and not win.canvas.sam_mode
        picker.setCurrentIndex(VIEW)
        assert not (win.canvas.brush_mode or win.canvas.sam_mode or win.canvas.bbox_mode)
    finally:
        win.close()


def test_shortcuts_and_measuring_move_the_selection(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        picker = win._tool_picker
        win._btn_brush_toggle.toggle()                       # what B does
        assert picker.currentIndex() == BRUSH
        win._btn_bbox_toggle.toggle()                        # what X does
        assert picker.currentIndex() == BBOX and not win.canvas.brush_mode
        win._btn_measure.setChecked(True)                    # 수동 측정 leaves every tool
        assert picker.currentIndex() == VIEW and not win.canvas.bbox_mode
        win._btn_measure.setChecked(False)
        win._btn_brush_toggle.toggle()
        win._btn_brush_toggle.toggle()                       # B again: brush off
        assert picker.currentIndex() == VIEW
    finally:
        win.close()


def test_choosing_a_tool_leaves_measuring(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._btn_measure.setChecked(True)
        win._tool_picker.setCurrentIndex(BRUSH)
        assert win.canvas.brush_mode and not win._btn_measure.isChecked()
    finally:
        win.close()


def test_sam_is_disabled_without_the_model(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, sam_available=False)
    try:
        assert not win._tool_picker.isToolEnabled(SAM)
    finally:
        win.close()


def test_repair_area_follows_whether_a_scale_is_known(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win._tool_picker.isToolEnabled(BBOX)             # server scale present
        win._btn_bbox_toggle.setEnabled(False)
        win._refresh_tools()
        assert not win._tool_picker.isToolEnabled(BBOX)
    finally:
        win.close()


def test_mode_toggle_buttons_are_not_shown(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for btn in (win._btn_brush_toggle, win._btn_sam_toggle, win._btn_bbox_toggle):
            assert not btn.isVisible()
    finally:
        win.close()


def test_display_toggles_stay_visible_for_every_tool(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for idx in (VIEW, BRUSH, SAM, BBOX):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            assert win._chk_show_highlight.isVisible()
            assert win._chk_show_repair15.isVisible()
    finally:
        win.close()


# ---------------------------------------------------------------- upload
def test_upload_is_pinned_below_the_scrolling_panel(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        scroll = win.findChild(QScrollArea)
        assert not scroll.widget().isAncestorOf(win.btn_upload)
        assert win.btn_upload.isVisible()
        upload_y = win.btn_upload.mapTo(win, win.btn_upload.rect().topLeft()).y()
        scroll_bottom = scroll.mapTo(win, scroll.rect().bottomLeft()).y()
        assert upload_y > scroll_bottom
    finally:
        win.close()


# ---------------------------------------------------------------- i18n
def test_panel_text_follows_the_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for code in ("en", "zh", "ko"):
            i18n.set_language(code)
            assert win._grp_list.title() == i18n.tr("group_list")
            assert win._grp_tools.title() == i18n.tr("group_tools")
            assert win._grp_display.title() == i18n.tr("group_display")
            assert win._tool_picker.toolText(BRUSH) == i18n.tr("tool_brush")
            assert win._list_header.labels()[1] == i18n.tr("list_col_file")
            assert win.btn_prev.toolTip() == i18n.tr(
                "tip_named_shortcut", name=i18n.tr("btn_prev"), shortcut="A")
            assert win._lbl_job_info.full_text() == i18n.tr(
                "job_info_head", job=45, count=i18n.tr("photo_count", n=2))
    finally:
        win.close()


def test_panel_content_fits_the_panel_width_in_every_language(tmp_path, monkeypatch):
    # Nothing may be clipped at the panel's narrowest width (horizontal
    # scrolling is off), with any tool selected.
    win = _make_window(tmp_path, monkeypatch)
    try:
        scroll = win.findChild(QScrollArea)
        content = scroll.widget()
        narrowest = scroll.parentWidget().minimumWidth()
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                QApplication.processEvents()
                assert content.minimumSizeHint().width() <= narrowest, (code, idx)
                for btn in content.findChildren(QPushButton):
                    if btn.isVisible():
                        assert btn.width() >= btn.minimumSizeHint().width(), (code, btn.text())
    finally:
        i18n.set_language("ko")
        win.close()


def test_the_image_list_takes_the_spare_height(tmp_path, monkeypatch):
    # The list has its own column: a taller window goes to the list (nearly
    # all of it); the tool groups on the right are never stretched.
    win = _make_window(tmp_path, monkeypatch)
    try:
        tools = win._grp_tools
        assert tools.height() <= tools.sizeHint().height()      # not stretched
        list_before, tools_before = win.file_list.height(), tools.height()
        win.resize(1400, 1100)
        _settle()
        assert tools.height() == tools_before
        assert win.file_list.height() - list_before >= 180      # nearly all of the 200 px
        assert win.file_list.minimumHeight() == 120             # no squeeze for the tools
    finally:
        win.close()


def test_moving_to_a_photo_without_scale_leaves_repair_area_mode_safely(tmp_path, monkeypatch):
    # (Regression from the tab version.) Disabling the current tab made Qt
    # jump to a neighbouring tab, and that
    # switched the user into SAM (or brush) mode without a word.
    for sam in (True, False):
        win = _make_window(tmp_path / str(sam), monkeypatch, sam_available=sam,
                           second_photo_scale=0.0)
        try:
            win._tool_picker.setCurrentIndex(BBOX)
            assert win.canvas.bbox_mode
            win.go_next()                                    # photo 2: no scale
            assert not (win.canvas.brush_mode or win.canvas.sam_mode or win.canvas.bbox_mode)
            assert win._tool_picker.currentIndex() == VIEW
            assert not win._tool_picker.isToolEnabled(BBOX)
        finally:
            win.close()


def test_mode_shortcuts_do_nothing_while_the_tool_is_unavailable(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch, second_photo_scale=0.0)
    try:
        win.go_next()                                        # no scale: no repair area
        win.activateWindow()
        win.canvas.setFocus()
        QTest.keyClick(win, Qt.Key_X)
        assert not win.canvas.bbox_mode
        assert win._tool_picker.currentIndex() == VIEW
    finally:
        win.close()


def test_help_button_has_a_tooltip_from_the_start(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win._btn_help.toolTip() == i18n.tr("group_hint")
    finally:
        win.close()


def test_sam_unavailable_tooltip_follows_the_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, sam_available=False)
    try:
        i18n.set_language("en")
        assert win._tool_picker.toolToolTip(SAM) == i18n.tr("sam_unavailable")
    finally:
        i18n.set_language("ko")
        win.close()


def test_help_text_uses_the_glossary_term_for_repair_areas():
    for code, term in (("ko", "보수 구역"), ("zh", "修补区域"), ("en", "Repair")):
        import importlib
        text = importlib.import_module(f"labeling_tool.core.i18n.strings_{code}").STRINGS["hint_text"]
        assert term in text, code


# ---------------------------------------------------------------- tool picker
def test_tools_are_a_two_by_two_grid_of_icon_buttons(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        buttons = [win._tool_picker.button(i) for i in range(4)]
        xs = {b.mapTo(win, b.rect().topLeft()).x() for b in buttons}
        ys = {b.mapTo(win, b.rect().topLeft()).y() for b in buttons}
        assert len(xs) == 2 and len(ys) == 2
        assert all(not b.icon().isNull() for b in buttons)
        assert [b.isChecked() for b in buttons] == [True, False, False, False]
    finally:
        win.close()


def test_clicking_a_tool_button_selects_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.button(BRUSH).click()
        assert win.canvas.brush_mode
        assert win._tool_picker.currentIndex() == BRUSH
        assert [win._tool_picker.button(i).isChecked() for i in range(4)] == [False, True, False, False]
    finally:
        win.close()


def test_each_tool_shows_its_name_and_how_to(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for idx, key in ((VIEW, "tool_view"), (BRUSH, "tool_brush"), (SAM, "tool_sam"), (BBOX, "tool_bbox")):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            page = win._tool_picker.current_page()
            texts = [lbl.text() for lbl in page.findChildren(QLabel) if lbl.isVisible()]
            assert i18n.tr(key) in texts
            assert i18n.tr(key + "_hint") in texts
    finally:
        win.close()


def test_the_class_picker_shows_with_the_brush_and_sam_only(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for idx in (VIEW, BRUSH, SAM, BBOX):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            assert win._class_picker_brush.isVisible() == (idx == BRUSH)
            assert win._class_picker_sam.isVisible() == (idx == SAM)
    finally:
        win.close()


def test_display_options_are_checkboxes_in_their_own_group(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert isinstance(win._chk_show_highlight, QCheckBox)
        assert win._chk_show_repair15.isChecked()                # on by default
        assert win._grp_display.isAncestorOf(win._chk_show_highlight)
        assert win._grp_display.isAncestorOf(win._btn_measure)
        win._chk_show_highlight.setChecked(True)
        assert win.canvas.show_highlight
    finally:
        win.close()


def test_the_tools_area_height_follows_the_selected_tool(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        heights = {}
        for idx in (VIEW, BRUSH):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            heights[idx] = (win._grp_tools.height(), win.file_list.height(),
                            win._grp_display.y())
        assert heights[VIEW][0] < heights[BRUSH][0]              # tools shrink
        assert heights[VIEW][2] < heights[BRUSH][2]              # display follows them up
        assert heights[VIEW][1] == heights[BRUSH][1]             # the list (own column) keeps its height
    finally:
        win.close()


def test_no_tool_makes_the_panel_scroll_in_a_900px_window(tmp_path, monkeypatch):
    # With the tallest tool page the display group must still be on screen
    # without scrolling (the list is in its own column now).
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        scroll = win.findChild(QScrollArea)
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                QApplication.processEvents()
                assert not scroll.verticalScrollBar().isVisible(), (code, idx)
    finally:
        i18n.set_language("ko")
        win.close()


def test_a_disabled_tool_cannot_be_picked_and_reclicking_emits_nothing():
    picker = ui_builder.ToolPicker()
    for _ in range(4):
        picker.add_tool("x", QLabel("page"))
    emitted = []
    picker.currentChanged.connect(emitted.append)
    picker.setToolEnabled(SAM, False)
    picker.setCurrentIndex(SAM)
    assert picker.currentIndex() == VIEW
    picker.button(VIEW).click()                     # the current tool again
    assert emitted == []
    picker.button(BRUSH).click()
    assert emitted == [BRUSH]


def test_number_keys_pick_classes_while_the_brush_page_is_hidden(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(
            C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]), "ok")
        assert not win._class_picker_brush.isVisible()           # 보기 selected
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_class_id == 2
        QTest.keyClick(win, Qt.Key_3)
        assert win.canvas.current_class_id == 3
        assert win._class_picker_brush.current_class() == 3
        QTest.keyClick(win, Qt.Key_9)                             # no 9th class: no change
        assert win.canvas.current_class_id == 3
    finally:
        win.close()


def test_both_pickers_follow_the_current_class(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(
            C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]), "ok")
        combo = win._class_picker_brush.combo
        combo.setCurrentIndex(combo.findData(3))
        assert win.canvas.current_class_id == 3
        assert win._class_picker_sam.current_class() == 3
        assert [combo.itemData(i) for i in range(combo.count())] == [1, 2, 3]
        assert "백태" in combo.itemText(2) and "3" in combo.itemText(2)
    finally:
        win.close()


def test_sam_cannot_use_the_crack_line(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._set_current_class(1)
        win._tool_picker.setCurrentIndex(SAM)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 2                   # moved to 박리
        model = win._class_picker_sam.combo.model()
        assert not model.item(win._class_picker_sam.combo.findData(1)).isEnabled()
        win._set_current_class(1)                                 # e.g. key 1 in SAM
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


def test_leaving_sam_gives_back_the_crack_line(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._set_current_class(1)
        win._tool_picker.setCurrentIndex(SAM)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 2                   # SAM chose 박리
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 1
        assert win._class_picker_brush.current_class() == 1
    finally:
        win.close()


def test_leaving_sam_keeps_a_category_picked_there(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._apply_class_registry(
            C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]), "ok")
        win._set_current_class(1)
        win._tool_picker.setCurrentIndex(SAM)
        QApplication.processEvents()
        win._set_current_class(3)                                 # the user's choice
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 3
        # Spalling chosen before SAM stays spalling after it.
        win._set_current_class(2)
        win._tool_picker.setCurrentIndex(SAM)
        QApplication.processEvents()
        win._tool_picker.setCurrentIndex(VIEW)
        QApplication.processEvents()
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


def test_the_class_does_not_change_in_the_middle_of_a_brush_stroke(tmp_path, monkeypatch):
    # A layer created after the stroke's undo snapshot would make part of
    # the stroke impossible to undo, so a switch waits for the release.
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        centre = win.canvas.rect().center()
        QTest.mousePress(win.canvas, Qt.LeftButton, Qt.NoModifier, centre)
        assert win.canvas._brushing
        win._set_current_class(2)
        assert win.canvas.current_class_id == 1
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_class_id == 1
        assert win._class_picker_brush.current_class() == 1
        QTest.mouseRelease(win.canvas, Qt.LeftButton, Qt.NoModifier, centre)
        assert not win.canvas._brushing
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


def test_leaving_the_brush_mid_stroke_ends_the_stroke(tmp_path, monkeypatch):
    # The release may never reach the brush (tool switched by key while the
    # button is held): the stroke must not stay open and lock the class.
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        centre = win.canvas.rect().center()
        QTest.mousePress(win.canvas, Qt.LeftButton, Qt.NoModifier, centre)
        assert win.canvas._brushing
        win._tool_picker.setCurrentIndex(VIEW)
        QApplication.processEvents()
        assert not win.canvas.brush_mode
        QTest.mouseRelease(win.canvas, Qt.LeftButton, Qt.NoModifier, centre)
        assert not win.canvas._brushing
        assert win.canvas.can_undo()                 # the stroke was recorded
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_class_id == 2
    finally:
        win.close()


def test_the_add_button_needs_the_server(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)                     # client=None
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        btn = win._class_picker_brush.add_button
        assert not btn.isEnabled() and btn.toolTip()
    finally:
        win.close()


def test_many_classes_keep_the_panel_unscrolled(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        win._apply_class_registry(C.ClassRegistry(
            [C.LabelClass(3 + i, f"아주 긴 카테고리 이름 {i}", "area", "#3C8CFF")
             for i in range(20)]), "ok")
        scroll = win.findChild(QScrollArea)
        content = scroll.widget()
        narrowest = scroll.parentWidget().minimumWidth()
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            for idx in (BRUSH, SAM):
                win._tool_picker.setCurrentIndex(idx)
                for _ in range(10):
                    QApplication.processEvents()
                assert not scroll.verticalScrollBar().isVisible(), (code, idx)
                assert content.minimumSizeHint().width() <= narrowest, (code, idx)
    finally:
        i18n.set_language("ko")
        win.close()


def test_the_sam_and_repair_area_how_tos_name_the_shared_keys():
    import importlib
    for code in ("ko", "zh", "en"):
        strings = importlib.import_module(f"labeling_tool.core.i18n.strings_{code}").STRINGS
        for key in ("tool_sam_hint", "sam_hint", "tool_bbox_hint"):
            for shortcut in ("Ctrl+Z", "Enter", "Esc"):
                assert shortcut in strings[key], (code, key, shortcut)


def test_help_dialog_opens_the_log_folder(tmp_path, monkeypatch):
    from labeling_tool import logging_setup
    from labeling_tool.core.window import main_window as core_main
    logs = tmp_path / "logs-here"
    monkeypatch.setattr(logging_setup, "log_dir", lambda: logs)
    opened = []
    monkeypatch.setattr(core_main.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url.toLocalFile()) or True))
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._btn_help.click()
        assert win._btn_open_logs.text() == i18n.tr("btn_open_logs")
        win._btn_open_logs.click()
        assert opened == [str(logs)]
        assert logs.is_dir()                       # created if it was missing
        win._help_dialog.close()
    finally:
        win.close()


# ---------------------------------------------------------------- shortcuts
def _focus_brush_size(win):
    win._tool_picker.setCurrentIndex(BRUSH)
    win.activateWindow()
    win._spn_brush_size.setFocus()
    QApplication.processEvents()
    assert QApplication.focusWidget() in (win._spn_brush_size, win._spn_brush_size.lineEdit())


def test_shortcuts_still_work_after_adjusting_the_brush_size(tmp_path, monkeypatch):
    # The size box swallowed letters (and sent them to a pinyin/hangul input
    # method), so after touching it A / D / S did nothing.
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    saves = []
    monkeypatch.setattr(win, "_save_all_artifacts", lambda *a, **k: saves.append(k))
    try:
        _focus_brush_size(win)
        target = QApplication.focusWidget()
        QTest.keyClick(target, Qt.Key_D)
        assert win.current_idx == 1
        QTest.keyClick(target, Qt.Key_A)
        assert win.current_idx == 0
        QTest.keyClick(target, Qt.Key_S)
        assert saves                                            # S saved
    finally:
        win.close()


def test_the_brush_size_box_still_takes_digits(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        _focus_brush_size(win)
        win._spn_brush_size.lineEdit().selectAll()
        QTest.keyClicks(QApplication.focusWidget(), "25")
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Return)
        assert win._spn_brush_size.value() == 25
        assert not win._spn_brush_size.lineEdit().testAttribute(Qt.WA_InputMethodEnabled)
        assert not win._spn_brush_size.testAttribute(Qt.WA_InputMethodEnabled)
    finally:
        win.close()


def test_ctrl_s_saves_too(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    saves = []
    monkeypatch.setattr(win, "_save_all_artifacts", lambda *a, **k: saves.append(k))
    try:
        win.activateWindow()
        win.canvas.setFocus()
        QTest.keyClick(win.canvas, Qt.Key_S, Qt.ControlModifier)
        assert saves
        assert "Ctrl+S" in win.btn_save.toolTip()
    finally:
        win.close()


def test_bracket_keys_resize_the_brush_from_the_size_box(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        _focus_brush_size(win)
        before = win._spn_brush_size.value()
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_BracketRight)
        assert win._spn_brush_size.value() == before + 2
    finally:
        win.close()


# ---------------------------------------------------------------- scale label
def test_scale_label_shows_only_the_value(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)          # photo 1: server scale 2.0 px/cm
    try:
        assert win._lbl_scale.text() == i18n.tr("lbl_scale", scale="5.0000")
        for word in ("PPM", "서버", "ArUco"):
            assert word not in win._lbl_scale.text()
        assert not win._lbl_scale.wordWrap()           # one line beside 수동 측정
    finally:
        win.close()


def test_a_manual_scale_is_marked_by_colour_and_tooltip(tmp_path, monkeypatch):
    # A text marker ("· 수동") did not fit the narrowest panel; the value
    # keeps its length and turns amber instead, with a tooltip saying why.
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert not win._lbl_scale.property("manual")
        win.current_scale, win.current_scale_source = 4.0, "manual"
        win._refresh_scale_label()
        assert win._lbl_scale.text() == i18n.tr("lbl_scale", scale="2.5000")
        assert win._lbl_scale.property("manual") is True
        assert win._lbl_scale.toolTip() == i18n.tr("scale_manual_tip")
        win.current_scale_source = "server"
        win._refresh_scale_label()
        assert not win._lbl_scale.property("manual") and win._lbl_scale.toolTip() == ""
    finally:
        win.close()


def test_no_scale_shows_a_dash(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, second_photo_scale=0.0)
    try:
        win.go_next()
        assert win._lbl_scale.text() == i18n.tr("lbl_scale", scale="--")
    finally:
        win.close()


def test_scale_row_fits_on_one_line_in_every_language(tmp_path, monkeypatch):
    # At the panel's narrowest width, manual or not: no clipping, the row
    # stays one line and the panel does not widen.
    win = _make_window(tmp_path, monkeypatch)
    try:
        side = win._splitter.widget(2)
        win._splitter.setSizes([280, 10_000, 0])             # panel at its minimum
        for code in ("ko", "zh", "en"):
            i18n.set_language(code)
            for scale, source in ((2.0, "server"), (28.49, "manual")):
                win.current_scale, win.current_scale_source = scale, source
                win._refresh_scale_label()
                QApplication.processEvents()
                lbl, btn = win._lbl_scale, win._btn_measure
                assert side.width() == side.minimumWidth(), (code, source)
                assert lbl.width() >= lbl.sizeHint().width(), (code, source)
                assert abs(lbl.mapTo(win, lbl.rect().center()).y()
                           - btn.mapTo(win, btn.rect().center()).y()) <= 2, (code, source)
    finally:
        i18n.set_language("ko")
        win.close()





# ---------------------------------------------------------------- undo / redo
def _stroke(win):
    """One real left-drag brush stroke across the middle of the canvas."""
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    win._tool_picker.setCurrentIndex(BRUSH)
    QApplication.processEvents()
    c = win.canvas
    mid = QPoint(c.width() // 2, c.height() // 2)
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, mid)
    QTest.mouseMove(c, mid + QPoint(5, 0))
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, mid + QPoint(5, 0))
    QApplication.processEvents()


def _ctrl(win, key, shift=False):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    mods = Qt.ControlModifier | (Qt.ShiftModifier if shift else Qt.NoModifier)
    win.activateWindow()
    QTest.keyClick(win.canvas, key, mods)
    QApplication.processEvents()


def test_ctrl_z_undoes_a_brush_stroke_and_ctrl_y_redoes_it(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        blank = c.brush_mask_crack.copy()
        assert not win._btn_undo.isEnabled() and not win._btn_redo.isEnabled()
        _stroke(win)
        drawn = c.brush_mask_crack.copy()
        assert (drawn != blank).any()
        assert win._btn_undo.isEnabled()
        _ctrl(win, Qt.Key_Z)
        assert (c.brush_mask_crack == blank).all()
        assert win._btn_redo.isEnabled()
        _ctrl(win, Qt.Key_Y)
        assert (c.brush_mask_crack == drawn).all()
        _ctrl(win, Qt.Key_Z)
        _ctrl(win, Qt.Key_Z, shift=True)                      # Ctrl+Shift+Z redoes too
        assert (c.brush_mask_crack == drawn).all()
    finally:
        win.close()


def test_undo_buttons_sit_on_their_own_row_in_the_brush_options(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        assert win._btn_undo.isVisible() and win._btn_redo.isVisible()
        assert win._btn_undo.text() == i18n.tr("btn_undo")
        assert "Ctrl+Z" in win._btn_undo.toolTip() and "Ctrl+Y" in win._btn_redo.toolTip()
        y = lambda b: b.mapTo(win, b.rect().topLeft()).y()
        assert y(win._btn_undo) == y(win._btn_redo) > y(win._btn_brush_reset)
        _stroke(win)
        win._btn_undo.click()
        assert not win._btn_undo.isEnabled() and win._btn_redo.isEnabled()
    finally:
        win.close()


def test_a_sam_commit_can_be_undone(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        blank = c.brush_mask_spalling.copy()
        c._sam_preview = np.full_like(blank, 0)
        c._sam_preview[2:5, 2:5] = 255
        assert c.commit_sam()
        assert (c.brush_mask_spalling != blank).any()
        _ctrl(win, Qt.Key_Z)
        assert (c.brush_mask_spalling == blank).all()
    finally:
        win.close()


def test_reset_to_loaded_mask_can_be_undone(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _stroke(win)
        drawn = c.brush_mask_crack.copy()
        win._btn_brush_reset.click()
        assert not c.brush_mask_crack.any()
        _ctrl(win, Qt.Key_Z)
        assert (c.brush_mask_crack == drawn).all()
        assert win._edited.get(win.image_files[win.current_idx])   # needs saving again
    finally:
        win.close()


def test_switching_photos_clears_the_history(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        _stroke(win)
        assert win._btn_undo.isEnabled()
        win.go_next()
        assert not win._btn_undo.isEnabled() and not win._btn_redo.isEnabled()
    finally:
        win.close()


def test_undo_marks_the_photo_edited(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        _stroke(win)
        name = win.image_files[win.current_idx]
        win._save_all_artifacts(silent=True)
        win._edited.pop(name, None)
        _ctrl(win, Qt.Key_Z)
        assert win._edited.get(name)
    finally:
        win.close()


# ---------------------------------------------------------------- upload marks
def _mark(win, row):
    return win.file_list.item(row).data(ui_builder.MARK_ROLE)


def test_uploaded_photos_are_marked(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, synced=(_FILES[0],))
    try:
        assert _mark(win, 0) == "uploaded"
        assert _mark(win, 1) is None
    finally:
        win.close()


def test_an_edited_photo_is_pending_until_uploaded(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _make_window(tmp_path, monkeypatch)
    try:
        _stroke(win)
        win._save_all_artifacts(silent=True)
        win._refresh_list_colors()
        assert _mark(win, 0) == "pending"
        win._finish_upload({"timestamps": [1], "failed": [], "uploaded": 1,
                            "anomalies": [], "verify_failures": [], "batch_id": "b"})
        assert _mark(win, 0) == "uploaded"
    finally:
        win.close()


def test_editing_an_uploaded_photo_again_makes_it_pending(tmp_path, monkeypatch):
    # The manifest kept "synced" after a later edit, so a re-edited photo
    # would have shown as uploaded.
    from labeling_tool.session.manifest import Manifest
    win = _make_window(tmp_path, monkeypatch, synced=(_FILES[0],))
    try:
        _stroke(win)
        win._save_all_artifacts(silent=True)
        win._refresh_list_colors()
        assert _mark(win, 0) == "pending"
        saved = Manifest.load(win._ws.manifest_path)
        assert not saved.get(_FILES[0]).synced
    finally:
        win.close()


def test_the_list_header_explains_the_marks(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win._list_header.toolTip() == i18n.tr("list_marks_tip")
    finally:
        win.close()


def test_a_new_manual_scale_on_an_uploaded_photo_makes_it_pending(tmp_path, monkeypatch):
    # The upload sends px_per_cm; a re-measured photo kept ✓ while the server
    # still had the old scale.
    from PyQt5.QtWidgets import QInputDialog
    win = _make_window(tmp_path, monkeypatch, synced=(_FILES[0],))
    try:
        assert _mark(win, 0) == "uploaded"
        monkeypatch.setattr(QInputDialog, "getDouble", staticmethod(lambda *a, **k: (7.0, True)))
        win._on_measure_completed(10.0)
        assert _mark(win, 0) == "pending"
        from labeling_tool.session.manifest import Manifest
        assert not Manifest.load(win._ws.manifest_path).get(_FILES[0]).synced
    finally:
        win.close()


def test_ctrl_z_undoes_a_stroke_from_the_brush_size_box(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        blank = win.canvas.brush_mask_crack.copy()
        _stroke(win)
        _focus_brush_size(win)
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Z, Qt.ControlModifier)
        assert (win.canvas.brush_mask_crack == blank).all()
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Y, Qt.ControlModifier)
        assert (win.canvas.brush_mask_crack != blank).any()
    finally:
        win.close()


def test_a_second_button_during_a_stroke_keeps_the_undo_point(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        blank = c.brush_mask_crack.copy()
        win._tool_picker.setCurrentIndex(BRUSH)
        QApplication.processEvents()
        mid = QPoint(c.width() // 2, c.height() // 2)
        QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, mid)
        QTest.mouseMove(c, mid + QPoint(5, 0))
        QTest.mousePress(c, Qt.RightButton, Qt.NoModifier, mid + QPoint(5, 0))
        QTest.mouseRelease(c, Qt.RightButton, Qt.NoModifier, mid + QPoint(5, 0))
        QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, mid + QPoint(5, 0))
        while c.undo():
            pass
        assert (c.brush_mask_crack == blank).all()
    finally:
        win.close()


def test_right_button_erase_can_be_undone(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _stroke(win)
        drawn = c.brush_mask_crack.copy()
        mid = QPoint(c.width() // 2, c.height() // 2)
        QTest.mousePress(c, Qt.RightButton, Qt.NoModifier, mid)
        QTest.mouseRelease(c, Qt.RightButton, Qt.NoModifier, mid)
        assert (c.brush_mask_crack != drawn).any()
        c.undo()
        assert (c.brush_mask_crack == drawn).all()
    finally:
        win.close()


def test_a_photo_saved_during_an_upload_stays_pending(tmp_path, monkeypatch):
    # The upload sent the old version; marking it ✓ afterwards would hide
    # the newer edit.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _make_window(tmp_path, monkeypatch)
    try:
        _stroke(win)
        win._save_all_artifacts(silent=True)
        win._begin_upload_tracking()
        _stroke(win)                                    # edited again while uploading
        win._save_all_artifacts(silent=True)
        win._finish_upload({"timestamps": [1], "failed": [], "uploaded": 1,
                            "anomalies": [], "verify_failures": [], "batch_id": "b"})
        assert _mark(win, 0) == "pending"
        assert not win._manifest.get(_FILES[0]).synced
    finally:
        win.close()


def test_tool_how_to_lines_are_never_clipped(tmp_path, monkeypatch):
    # The wrapped how-to label got its one-width size hint, so SAM's three
    # lines were squeezed into the height of two and overlapped.
    win = _make_window(tmp_path, monkeypatch)
    try:
        for code in ("ko", "zh", "en"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                QApplication.processEvents()
                QApplication.processEvents()
                for lbl in win._tool_picker.current_page().findChildren(QLabel):
                    if lbl.isVisible() and lbl.wordWrap():
                        assert lbl.height() >= lbl.heightForWidth(lbl.width()), (code, idx, lbl.text())
    finally:
        i18n.set_language("ko")
        win.close()



# ---------------------------------------------------------------- range view
_SIX = tuple(f"stitched_{n:03d}.jpg" for n in range(1, 7))


def _range_window(tmp_path, monkeypatch):
    from labeling_tool.session.focus import PhotoFocus
    return _make_window(tmp_path, monkeypatch, files=_SIX,
                        focus=PhotoFocus(2, 4, _SIX[1:4]))


def _rows(win):
    return [win.file_list.item(i).toolTip() for i in range(win.file_list.count())]


def test_a_range_fetch_shows_only_those_photos(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        assert _rows(win) == list(_SIX[1:4])
        assert win._range_bar.isVisible()
        assert win._lbl_range.text() == i18n.tr("list_range_label", a=2, b=4, n=3)
        assert win._btn_range_toggle.text() == i18n.tr("btn_show_all")
        assert win._lbl_job_info.full_text().endswith(i18n.tr("photo_count_part", shown=3, total=6))
    finally:
        win.close()


def test_show_all_and_back_keeps_the_current_photo(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(1)                         # stitched_003
        current = win.image_files[win.current_idx]
        win._btn_range_toggle.click()
        assert _rows(win) == list(_SIX)
        assert win.image_files[win.current_idx] == current
        assert win._btn_range_toggle.text() == i18n.tr("btn_show_range")
        win._btn_range_toggle.click()
        assert _rows(win) == list(_SIX[1:4])
        assert win.image_files[win.current_idx] == current
    finally:
        win.close()


def test_an_unsaved_edit_is_saved_before_switching_the_view(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        _stroke(win)
        name = win.image_files[win.current_idx]
        win._btn_range_toggle.click()
        assert win._has_labeling_file(name)
    finally:
        win.close()


def test_upload_covers_only_the_photos_shown(tmp_path, monkeypatch):
    from labeling_tool.session import mask_store
    win = _range_window(tmp_path, monkeypatch)
    try:
        win.output_dir.mkdir(parents=True, exist_ok=True)
        for name in (_SIX[0], _SIX[2]):                       # one outside, one inside
            (win.output_dir / mask_store.mask_name(name)).write_bytes(b"x")
        assert win._edited_filenames() == [_SIX[2]]
        win._btn_range_toggle.click()                          # 전체 보기
        assert win._edited_filenames() == [_SIX[0], _SIX[2]]
    finally:
        win.close()


def test_without_a_range_there_is_no_range_bar(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert not win._range_bar.isVisible()
        assert win._lbl_job_info.full_text().endswith(i18n.tr("photo_count", n=2))
    finally:
        win.close()


def test_range_view_never_makes_the_panel_scroll_in_a_900px_window(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        scroll = win.findChild(QScrollArea)
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                for _ in range(6):
                    QApplication.processEvents()
                assert not scroll.verticalScrollBar().isVisible(), (code, idx)
    finally:
        i18n.set_language("ko")
        win.close()


def test_a_range_with_nothing_on_disk_opens_normally(tmp_path, monkeypatch):
    from labeling_tool.session.focus import PhotoFocus
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    win = _make_window(tmp_path, monkeypatch, files=_SIX,
                       focus=PhotoFocus(7, 8, ("missing_7.jpg", "missing_8.jpg")))
    try:
        assert _rows(win) == list(_SIX)
        assert not win._range_bar.isVisible() and warned == []
    finally:
        win.close()


def test_a_range_covering_every_local_photo_needs_no_bar(tmp_path, monkeypatch):
    from labeling_tool.session.focus import PhotoFocus
    win = _make_window(tmp_path, monkeypatch, files=_SIX, focus=PhotoFocus(1, 0, _SIX))
    try:
        assert _rows(win) == list(_SIX)
        assert not win._range_bar.isVisible()
        assert win._lbl_job_info.full_text().endswith(i18n.tr("photo_count", n=6))
    finally:
        win.close()


def test_switching_the_view_does_not_load_the_first_photo_on_the_way(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(2)                         # stitched_004
        shown = []
        orig = win._show_image
        monkeypatch.setattr(win, "_show_image", lambda i, *a, **k: (shown.append(win.image_files[i]), orig(i, *a, **k))[1])
        win._btn_range_toggle.click()
        assert shown == [_SIX[3]]
    finally:
        win.close()


# ---------------------------------------------------------------- one key, one meaning
class _BlockPredictor:
    """Marks a fixed block of whatever crop it is given."""
    def set_image(self, bgr):
        self._hw = bgr.shape[:2]

    def predict(self, points, labels):
        m = np.zeros(self._hw, np.uint8)
        m[1:4, 1:4] = 255
        return m


def _key(win, key):
    from PyQt5.QtTest import QTest
    win.activateWindow()
    QTest.keyClick(win.canvas, key)
    QApplication.processEvents()


def _sam_with_points(win, *points):
    win._tool_picker.setCurrentIndex(SAM)
    QApplication.processEvents()
    win.canvas.set_sam_predictor(_BlockPredictor())
    for x, y, label in points:
        win.canvas._sam_add_point(x, y, label)


def test_ctrl_z_in_sam_drops_the_last_point_before_touching_the_mask(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _stroke(win)
        drawn = c.brush_mask_crack.copy()
        _sam_with_points(win, (2, 2, 1), (5, 5, 0))
        _ctrl(win, Qt.Key_Z)
        assert c._sam_points == [(2, 2)]
        assert (c.brush_mask_crack == drawn).all()           # the stroke is untouched
        _ctrl(win, Qt.Key_Y)
        assert c._sam_points == [(2, 2), (5, 5)]
        _ctrl(win, Qt.Key_Z); _ctrl(win, Qt.Key_Z)
        assert c._sam_points == [] and not c.has_sam_preview()
        _ctrl(win, Qt.Key_Z)                                  # no points left: undo the stroke
        assert not c.brush_mask_crack.any()
        _ctrl(win, Qt.Key_Y)                                  # redo follows the same order back
        assert (c.brush_mask_crack == drawn).all()
        assert c._sam_points == []
    finally:
        win.close()


def test_enter_confirms_sam_into_spalling(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _sam_with_points(win, (2, 2, 1))
        _key(win, Qt.Key_Return)
        assert c.brush_mask_spalling.any() and not c.has_sam_preview()
        _ctrl(win, Qt.Key_Z)                                  # the confirm is one undo step
        assert not c.brush_mask_spalling.any()
        _sam_with_points(win, (2, 2, 1))
        _key(win, Qt.Key_Enter)                               # keypad Enter too
        assert c.brush_mask_spalling.any()
    finally:
        win.close()


def test_esc_in_sam_clears_every_point(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _sam_with_points(win, (2, 2, 1), (5, 5, 0))
        _key(win, Qt.Key_Escape)
        assert c._sam_points == [] and not c.has_sam_preview()
        assert not c.brush_mask_spalling.any()
        _ctrl(win, Qt.Key_Y)                                  # a cancel is not undone point by point
        assert c._sam_points == []
    finally:
        win.close()


def test_ctrl_z_in_repair_area_drops_the_last_point(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _stroke(win)
        drawn = c.brush_mask_crack.copy()
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        c.bbox_interaction.on_left_press(1, 1)
        c.bbox_interaction.on_left_press(6, 6)
        _ctrl(win, Qt.Key_Z)
        assert c.bbox_interaction.in_progress_clicks == [(1.0, 1.0)]
        assert (c.brush_mask_crack == drawn).all()
        _key(win, Qt.Key_Escape)
        assert c.bbox_interaction.in_progress_clicks == []
    finally:
        win.close()


def test_tool_pages_are_never_squeezed_in_a_900px_window(tmp_path, monkeypatch):
    # A how-to line can be tall enough by itself and still be painted over:
    # when the panel runs out of height the page is laid out below its
    # minimum and the buttons under the text overlap it.
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        for code in ("ko", "zh", "en"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                for _ in range(10):                  # let the size requests settle
                    QApplication.processEvents()
                page = win._tool_picker.current_page()
                assert page.height() >= page.minimumSizeHint().height(), (code, idx)
                widgets = [w for w in page.findChildren(QWidget)
                           if w.isVisible() and w.parentWidget() is page]
                for a in widgets:
                    ra = a.geometry()
                    for b in widgets:
                        if a is not b and ra.intersects(b.geometry()):
                            raise AssertionError((code, idx, a.objectName() or a.text(),
                                                  b.objectName() or getattr(b, "text", str)()))
    finally:
        i18n.set_language("ko")
        win.close()


def test_ctrl_z_with_nothing_left_keeps_the_sam_redo_steps(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        c = win.canvas
        _sam_with_points(win, (2, 2, 1), (5, 5, 0))
        both = list(c._sam_points)
        _ctrl(win, Qt.Key_Z); _ctrl(win, Qt.Key_Z)
        _ctrl(win, Qt.Key_Z)                                  # no mask edit to undo either
        assert c.can_redo_sam_point()
        _ctrl(win, Qt.Key_Z, shift=True); _ctrl(win, Qt.Key_Z, shift=True)   # Ctrl+Shift+Z
        assert c._sam_points == both
    finally:
        win.close()


# ---------------------------------------------------------------- unconfirmed edits on switch
def _saves_seen(win, monkeypatch):
    """Record what the canvas held each time the photo was saved."""
    seen = []
    real = win._save_all_artifacts

    def spy(*a, **k):
        seen.append({"spalling": bool(win.canvas.brush_mask_spalling.any()),
                     "boxes": len(win.canvas.bbox_interaction.boxes),
                     "clicks": len(win.canvas.bbox_interaction.in_progress_clicks),
                     "edited": bool(win._edited.get(_FILES[0])),
                     "bbox_edited": bool(win._bbox_edited.get(_FILES[0])),
                     "saved": None})
        seen[-1]["saved"] = real(*a, **k)
        return seen[-1]["saved"]
    monkeypatch.setattr(win, "_save_all_artifacts", spy)
    return seen


def test_moving_on_confirms_an_unconfirmed_sam_selection(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        seen = _saves_seen(win, monkeypatch)
        _sam_with_points(win, (2, 2, 1))
        assert win.canvas.has_sam_preview()
        win.go_next()
        assert seen and seen[0]["spalling"]                  # written before the save
        assert seen[0]["edited"] and seen[0]["saved"]
        assert win.status.currentMessage() == i18n.tr("sam_auto_committed")
    finally:
        win.close()


def test_moving_on_confirms_unconfirmed_repair_area_points(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        seen = _saves_seen(win, monkeypatch)
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        c = win.canvas
        c.bbox_interaction.on_left_press(1, 1)
        c.bbox_interaction.on_left_press(6, 6)
        win.go_next()
        assert seen[0]["boxes"] == 1 and seen[0]["clicks"] == 0
        assert seen[0]["bbox_edited"] and seen[0]["saved"]
        assert win.status.currentMessage() == i18n.tr("bbox_auto_committed")
    finally:
        win.close()


def test_a_single_repair_area_point_is_dropped_on_moving_on(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        seen = _saves_seen(win, monkeypatch)
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        win.canvas.bbox_interaction.on_left_press(1, 1)
        win.go_next()
        assert seen[0]["boxes"] == 0 and seen[0]["clicks"] == 0
        assert not seen[0]["bbox_edited"]
    finally:
        win.close()


def test_closing_confirms_an_unconfirmed_sam_selection(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    seen = _saves_seen(win, monkeypatch)
    _sam_with_points(win, (2, 2, 1))
    win.close()
    assert seen and seen[-1]["spalling"]


def test_switching_the_range_view_confirms_an_unconfirmed_sam_selection(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        seen = []
        real = win._save_all_artifacts
        monkeypatch.setattr(win, "_save_all_artifacts", lambda *a, **k: (
            seen.append(bool(win.canvas.brush_mask_spalling.any())), real(*a, **k))[1])
        _sam_with_points(win, (2, 2, 1))
        win._btn_range_toggle.click()
        QApplication.processEvents()
        assert seen and seen[0]
        assert win.status.currentMessage() == i18n.tr("sam_auto_committed")
    finally:
        win.close()


def test_upload_confirms_an_unconfirmed_sam_selection_first(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        monkeypatch.setattr(win, "_edited_filenames", lambda: [])
        _sam_with_points(win, (2, 2, 1))
        win._on_upload()
        assert win.canvas.brush_mask_spalling.any() and not win.canvas.has_sam_preview()
    finally:
        win.close()


def test_repair_area_points_without_a_scale_are_dropped_with_a_message(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        c = win.canvas
        c.bbox_interaction.on_left_press(1, 1)
        c.bbox_interaction.on_left_press(6, 6)
        c.set_bbox_padding_px(0)
        win.go_next()
        assert win.status.currentMessage() == i18n.tr("bbox_auto_dropped")
    finally:
        win.close()


# ---------------------------------------------------------------- user classes
def _with_user_class_mask(tmp_path, monkeypatch, value=3):
    """A window whose first photo already has class `value` pixels saved."""
    win = _make_window(tmp_path, monkeypatch)
    label = np.zeros((8, 8), np.uint8)
    label[1:3, 1:3] = value
    win.output_dir.mkdir(parents=True, exist_ok=True)
    from labeling_tool.session import mask_store
    cv2.imwrite(str(win.output_dir / mask_store.mask_name(_FILES[0])), label)
    win._show_image(0, force_reload=True)
    return win


def test_a_saved_user_class_survives_load_and_save(tmp_path, monkeypatch):
    from labeling_tool.session import mask_store
    win = _with_user_class_mask(tmp_path, monkeypatch, value=3)
    try:
        assert sorted(win.canvas.layers) == [1, 2, 3]
        win._edited[_FILES[0]] = True
        assert win._save_all_artifacts(silent=True, async_derived=False)
        back = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                          cv2.IMREAD_UNCHANGED)
        assert back[1, 1] == 3 and back[5, 5] == 0
        hi = cv2.imread(str(win.highlight_dir / mask_store.mask_name(_FILES[0])),
                        cv2.IMREAD_UNCHANGED)
        assert hi[1, 1] == 3
    finally:
        win.close()


def test_an_unknown_class_is_kept_through_a_save(tmp_path, monkeypatch):
    from labeling_tool.session import mask_store
    win = _with_user_class_mask(tmp_path, monkeypatch, value=9)
    try:
        assert 9 not in win.class_registry
        win._edited[_FILES[0]] = True
        assert win._save_all_artifacts(silent=True, async_derived=False)
        back = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                          cv2.IMREAD_UNCHANGED)
        assert back[1, 1] == 9
    finally:
        win.close()


def test_the_window_starts_from_the_cached_class_list(tmp_path, monkeypatch):
    from labeling_tool.core import classes as C
    C.save_cached("", C.ClassRegistry([C.LabelClass(3, "백태", "area", "#3C8CFF")]))
    win = _make_window(tmp_path, monkeypatch)            # client=None -> offline
    try:
        assert win.class_registry.ids() == [1, 2, 3]
        assert win._class_sync_status == "offline"
        assert win.canvas.class_registry is win.class_registry
    finally:
        win.close()


def test_unknown_classes_are_announced_after_an_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._finish_upload({"failed": [], "uploaded": 1, "timestamps": [],
                            "unknown_classes": [7, 9]})
        assert "#7, #9" in win.status.currentMessage()
    finally:
        win.close()


def test_s_saves_an_unconfirmed_sam_selection(tmp_path, monkeypatch):
    import cv2
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from labeling_tool.session import mask_store
    win = _make_window(tmp_path, monkeypatch)
    try:
        _sam_with_points(win, (2, 2, 1))
        win.activateWindow()
        QTest.keyClick(win.canvas, Qt.Key_S)
        QApplication.processEvents()
        assert not win.canvas.has_sam_preview()
        saved = cv2.imread(str(win.output_dir / mask_store.mask_name(_FILES[0])),
                           cv2.IMREAD_UNCHANGED)
        assert saved is not None and (saved == 2).any()
        assert win.status.currentMessage() == i18n.tr("sam_auto_committed")
    finally:
        win.close()


def test_failed_save_does_not_claim_the_selection_was_saved(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        _sam_with_points(win, (2, 2, 1))
        monkeypatch.setattr(win, "_save_all_artifacts", lambda **k: False)
        win.status.clearMessage()
        win._on_brush_save()
        assert win.status.currentMessage() != i18n.tr("sam_auto_committed")
    finally:
        win.close()


def test_ctrl_s_confirms_repair_area_points(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._tool_picker.setCurrentIndex(BBOX)
        QApplication.processEvents()
        c = win.canvas
        c.bbox_interaction.on_left_press(1, 1)
        c.bbox_interaction.on_left_press(6, 6)
        _ctrl(win, Qt.Key_S)
        assert len(c.bbox_interaction.boxes) == 1 and not c.bbox_interaction.in_progress_clicks
    finally:
        win.close()


# ---------------------------------------------------------------- surface / delete
def _settle(rounds=10):
    for _ in range(rounds):
        QApplication.processEvents()


def _surface(win, row):
    return win.file_list.item(row).data(ui_builder.SURFACE_ROLE)


def test_each_row_shows_its_surface(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert _surface(win, 0) == i18n.tr("surface_unknown_short")
        win._manifest.get(_FILES[0]).surface = "wall"
        win._reload_data()
        _settle()
        assert _surface(win, 0) == i18n.tr("surface_wall")
        assert not win.file_list.item(0).data(ui_builder.SURFACE_EDITED_ROLE)
    finally:
        win.close()


def test_the_surface_column_fits_every_language(tmp_path, monkeypatch):
    from PyQt5.QtGui import QFontMetrics
    win = _make_window(tmp_path, monkeypatch)
    try:
        metrics = QFontMetrics(win.file_list.font())
        width = win.file_list.itemDelegate().surface_width
        for code in ("ko", "zh", "en"):
            for key in ("surface_floor", "surface_wall", "surface_ceiling",
                        "surface_unknown_short", "list_col_surface"):
                text = i18n.TRANSLATIONS[code][key]
                assert metrics.horizontalAdvance(text) <= width, (code, key)
    finally:
        win.close()


def test_a_leftover_delete_mark_shows_nothing(tmp_path, monkeypatch):
    # A manifest marked during development testing: no "삭제 예정", no ●.
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._manifest.get(_FILES[0]).delete_pending = True
        win._refresh_list_colors()
        assert not win.file_list.item(0).data(ui_builder.DELETE_PENDING_ROLE)
        assert _mark(win, 0) is None
    finally:
        win.close()


def test_choosing_a_surface_edits_the_current_photo_and_back(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        entry = win._manifest.get(_FILES[0])
        entry.surface = "wall"
        win._reload_data()
        _settle()
        win._surface_row.buttons["floor"].click()
        assert entry.surface_edit == "floor"
        assert Manifest.load(win._ws.manifest_path).get(_FILES[0]).surface_edit == "floor"
        assert win._surface_row.buttons["floor"].isChecked()
        assert win._surface_row.buttons["floor"].property("edited")
        assert _surface(win, 0) == i18n.tr("surface_floor")
        assert win.file_list.item(0).data(ui_builder.SURFACE_EDITED_ROLE)
        assert _mark(win, 0) == "pending"
        win._on_surface_chosen("wall")                     # the server's value: undo
        assert entry.surface_edit is None
        assert win._surface_row.buttons["wall"].isChecked()
        assert not win._surface_row.buttons["wall"].property("edited")
        assert _surface(win, 0) == i18n.tr("surface_wall")
        assert not win.file_list.item(0).data(ui_builder.SURFACE_EDITED_ROLE)
        assert _mark(win, 0) is None
    finally:
        win.close()


def test_clicking_the_edited_surface_again_undoes_a_misclick(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        entry = win._manifest.get(_FILES[0])
        assert entry.surface is None                       # what the server sends today
        row = win._surface_row
        row.buttons["wall"].click()
        assert entry.surface_edit == "wall"
        assert row.buttons["wall"].isChecked() and row.buttons["wall"].property("edited")
        assert _mark(win, 0) == "pending"
        row.buttons["wall"].click()                        # the misclick, taken back
        assert entry.surface_edit is None
        assert Manifest.load(win._ws.manifest_path).get(_FILES[0]).surface_edit is None
        assert not any(b.isChecked() for b in row.buttons.values())
        assert not row.buttons["wall"].property("edited")
        assert row.unknown.isVisibleTo(row)
        assert _surface(win, 0) == i18n.tr("surface_unknown_short")
        assert not win.file_list.item(0).data(ui_builder.SURFACE_EDITED_ROLE)
        assert _mark(win, 0) is None
    finally:
        win.close()


def test_the_surface_row_follows_the_current_photo(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        second = win._manifest.get(_FILES[1])
        second.surface, second.tilt_deg, second.tilt_source = "ceiling", 12.6, "manual"
        win.file_list.setCurrentRow(1)
        _settle()
        row = win._surface_row
        assert row.isEnabled()
        assert row.buttons["ceiling"].isChecked()
        assert row.tilt.text() == i18n.tr("tilt_deg", deg=13)
        assert row.tilt.toolTip() == i18n.tr("tilt_manual_tip")
        win.file_list.setCurrentRow(0)
        _settle()
        assert not any(b.isChecked() for b in row.buttons.values())
        assert row.tilt.text() == i18n.tr("tilt_none")
    finally:
        win.close()


def test_a_failed_manifest_write_is_reported_not_raised(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        def broken(_path):
            raise OSError("disk full")
        monkeypatch.setattr(win._manifest, "save", broken)
        win._on_surface_chosen("floor")
        assert win._manifest.get(_FILES[0]).surface_edit == "floor"
        assert "disk full" in win.status.currentMessage()
    finally:
        win.close()


def test_surface_texts_follow_the_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._manifest.get(_FILES[0]).surface = "ceiling"
        win._reload_data()
        _settle()
        for code in ("en", "zh", "ko"):
            i18n.set_language(code)
            assert _surface(win, 0) == i18n.tr("surface_ceiling")
            assert win._surface_row.label.text() == i18n.tr("surface_label")
            assert win._list_header.surface_label() == i18n.tr("list_col_surface")
    finally:
        i18n.set_language("ko")
        win.close()


class _FakeSignal:
    def connect(self, *_a):
        pass


def _fake_worker(monkeypatch):
    """Record each UploadWorker the window builds instead of running one."""
    from labeling_tool.ui import main_window as viewer_module
    made = []

    class FakeWorker:
        def __init__(self, client, **kwargs):
            self.kwargs = kwargs
            self.progress = self.done = self.error = _FakeSignal()
            made.append(self)

        def start(self):
            pass
    monkeypatch.setattr(viewer_module, "UploadWorker", FakeWorker)
    return made


def _no_dialog(monkeypatch):
    """Fail on any message box that would ask the user something."""
    monkeypatch.setattr(QMessageBox, "exec_",
                        lambda *a, **k: _unexpected("no dialog expected"))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: _unexpected("no question expected"))


def test_a_leftover_delete_mark_alone_sends_nothing_and_asks_nothing(tmp_path, monkeypatch):
    shown = []
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _no_dialog(monkeypatch)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a))
        win._manifest.get(_FILES[1]).delete_pending = True
        win._on_upload()
        assert made == []
        assert win.status.currentMessage() == i18n.tr("vmw_status_no_edits")
        assert len(shown) == 1
        assert win._manifest.get(_FILES[1]).delete_pending   # left as it was
    finally:
        win.close()


def test_upload_with_only_a_surface_change_sends_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _no_dialog(monkeypatch)
        win._on_surface_chosen("floor")
        win._on_upload()
        assert len(made) == 1
        assert made[0].kwargs["specs"] == []
        assert made[0].kwargs["surface_updates"] == [{"timestamp": 1, "surface": "floor"}]
        assert list(made[0].kwargs["deletes"]) == []
    finally:
        win.close()


def _unexpected(msg):
    raise AssertionError(msg)


def test_a_leftover_delete_mark_still_uploads_the_photos_edits(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _no_dialog(monkeypatch)
        _stroke(win)                                       # photo 1 edited ...
        win._save_all_artifacts(silent=True)
        win._on_surface_chosen("floor")                    # ... and its surface
        win.file_list.setCurrentRow(1)
        _settle()
        _stroke(win)                                       # photo 2 edited
        win._save_all_artifacts(silent=True)
        win._manifest.get(_FILES[0]).delete_pending = True
        win._refresh_list_colors()
        assert _mark(win, 0) == "pending"                  # for its edits
        win._on_upload()
        assert [s["filename"] for s in made[0].kwargs["specs"]] == list(_FILES)
        assert made[0].kwargs["surface_updates"] == [{"timestamp": 1, "surface": "floor"}]
        assert list(made[0].kwargs["deletes"]) == []
    finally:
        win.close()


def test_upload_without_any_edit_still_says_so(tmp_path, monkeypatch):
    shown = []
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a))
        win._on_upload()
        assert made == [] and len(shown) == 1
        assert win.status.currentMessage() == i18n.tr("vmw_status_no_edits")
    finally:
        win.close()


def test_a_range_view_uploads_only_the_listed_photos_edits(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        outside = win._manifest.get(_SIX[0])               # not listed
        outside.surface_edit = "wall"
        listed = win._manifest.get(_SIX[1])                # ts 2, listed
        listed.surface_edit = "floor"
        listed.delete_pending = True                       # leftover: ignored
        win._on_upload()
        assert made[0].kwargs["surface_updates"] == [{"timestamp": 2, "surface": "floor"}]
        assert list(made[0].kwargs["deletes"]) == []
    finally:
        win.close()


def test_the_window_has_no_delete_confirmation(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert not hasattr(win, "_confirm_deletes")
        assert not hasattr(win, "_build_delete_confirm")
    finally:
        win.close()


def test_the_surface_row_never_makes_the_panel_scroll_in_a_900px_window(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.resize(1400, 900)
        scroll = win.findChild(QScrollArea)
        content = scroll.widget()
        narrowest = scroll.parentWidget().minimumWidth()
        assert narrowest <= 340
        for code in ("ko", "zh", "en"):
            i18n.set_language(code)
            for idx in (VIEW, BRUSH, SAM, BBOX):
                win._tool_picker.setCurrentIndex(idx)
                _settle()
                assert win._surface_row.isVisible()
                assert not scroll.verticalScrollBar().isVisible(), (code, idx)
                assert content.minimumSizeHint().width() <= narrowest, (code, idx)
    finally:
        i18n.set_language("ko")
        win.close()


# ---------------------------------------------------------------- after an upload
_THREE = ("stitched_100.jpg", "stitched_200.jpg", "stitched_300.jpg")


def _result(**kw):
    out = {"timestamps": [], "failed": [], "uploaded": 0, "anomalies": [],
           "verify_failures": [], "batch_id": "b", "surface_timestamps": []}
    out.update(kw)
    return out


def _three(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return _make_window(tmp_path, monkeypatch, files=_THREE)


def _current(win):
    return win.image_files[win.current_idx] if win.current_idx >= 0 else None


def test_deleted_timestamps_in_a_result_remove_nothing(tmp_path, monkeypatch):
    # Nothing sends deletes any more; even if a result listed one, the photo,
    # its files and its row stay.
    win = _three(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(1)
        _settle()
        win._finish_upload(_result(timestamps=[1], uploaded=1, deleted_timestamps=[2]))
        assert (win._ws.origin_dir / _THREE[1]).exists()
        assert sorted(win._manifest.photos) == list(_THREE)
        assert win.image_files == list(_THREE)
        assert _current(win) == _THREE[1]
        assert win.status.currentMessage() == i18n.tr("vmw_status_done", count=1)
    finally:
        win.close()


def _capture_info(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda _parent, title, text, *a, **k: shown.append((title, text)))
    return shown


def test_an_edits_only_upload_reports_the_edits_not_zero_photos(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        shown = _capture_info(monkeypatch)
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
        win._manifest.get(_THREE[1]).surface_edit = "wall"
        win._finish_upload(_result(surface_timestamps=[2]))
        summary = i18n.tr("upload_surface_summary", n=1)
        expected = i18n.tr("vmw_status_done_edits", summary=summary)
        assert win.status.currentMessage() == expected
        assert shown == [(i18n.tr("vmw_done_title"), expected)]
    finally:
        win.close()


def test_a_mixed_upload_keeps_the_photo_count_and_adds_the_edits(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        shown = _capture_info(monkeypatch)
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
        win._manifest.get(_THREE[2]).surface_edit = "wall"
        win._finish_upload(_result(timestamps=[1], uploaded=1, surface_timestamps=[3]))
        summary = i18n.tr("upload_surface_summary", n=1)
        assert win.status.currentMessage() == (
            i18n.tr("vmw_status_done", count=1) + " · " + summary)
        assert shown == [(i18n.tr("vmw_done_title"),
                          i18n.tr("vmw_done_msg", count=1, report_line="") + "\n" + summary)]
    finally:
        win.close()


def test_a_sent_surface_change_becomes_the_photo_surface(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        win._on_surface_chosen("floor")
        win._on_upload()
        assert made[0].kwargs["surface_updates"] == [{"timestamp": 1, "surface": "floor"}]
        win._finish_upload(_result(surface_timestamps=[1]))
        entry = win._manifest.get(_THREE[0])
        assert (entry.surface, entry.surface_edit, entry.tilt_source) == (
            "floor", None, "manual")
        assert Manifest.load(win._ws.manifest_path).get(_THREE[0]).surface_edit is None
        assert _mark(win, 0) != "pending"
        assert not win.file_list.item(0).data(ui_builder.SURFACE_EDITED_ROLE)
        assert i18n.tr("upload_surface_summary", n=1) in win.status.currentMessage()
    finally:
        win.close()


def test_a_surface_changed_during_the_upload_stays_pending(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        win._on_surface_chosen("floor")
        win._on_upload()
        win._on_surface_chosen("wall")                     # while uploading
        win._finish_upload(_result(surface_timestamps=[1]))
        entry = win._manifest.get(_THREE[0])
        assert entry.surface == "floor"                    # what the server has now
        assert entry.surface_edit == "wall"
        assert _mark(win, 0) == "pending"
    finally:
        win.close()


def test_a_surface_taken_back_during_the_upload_stays_pending(tmp_path, monkeypatch):
    # The server had "wall"; "floor" was sent, then the user chose "wall"
    # again: the server now has "floor", so "wall" still has to be sent.
    win = _three(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        entry = win._manifest.get(_THREE[0])
        entry.surface = "wall"
        win._on_surface_chosen("floor")
        win._on_upload()
        win._on_surface_chosen("wall")
        assert entry.surface_edit is None
        win._finish_upload(_result(surface_timestamps=[1]))
        assert (entry.surface, entry.surface_edit) == ("floor", "wall")
    finally:
        win.close()


def test_refreshed_numbers_show_and_the_current_photo_stays(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(2)
        _settle()
        assert win.file_list.item(1).text() == "45-2"
        win._on_photo_refresh_done([{"timestamp": 1, "reportPhotoNum": 1},
                                    {"timestamp": 2, "reportPhotoNum": 5},
                                    {"timestamp": 3, "reportPhotoNum": 2,
                                     "surface": "wall"}])
        assert win.file_list.item(1).text() == "45-5"
        assert win.file_list.item(2).text() == "45-2"
        assert _surface(win, 2) == i18n.tr("surface_wall")
        assert Manifest.load(win._ws.manifest_path).get(_THREE[2]).report_photo_num == 2
        assert _current(win) == _THREE[2]
    finally:
        win.close()


def test_a_failed_refresh_is_reported(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._on_photo_refresh_done(None)
        assert win.status.currentMessage() == i18n.tr("photo_refresh_failed")
        assert win.file_list.count() == 3
    finally:
        win.close()


def test_a_surface_change_starts_the_refresh_in_the_background(tmp_path, monkeypatch):
    from PyQt5.QtCore import QThreadPool
    win = _three(tmp_path, monkeypatch)
    try:
        class Client:
            base_url = ""

            def list_photos(self, session_id, *, offset=0, limit=100, **_kw):
                photos = [{"timestamp": 1, "reportPhotoNum": 1},
                          {"timestamp": 2, "reportPhotoNum": 7},
                          {"timestamp": 3, "reportPhotoNum": 3}]
                return {"photos": photos[offset:offset + limit], "total": 3}
        win._client = Client()
        win._manifest.get(_THREE[1]).surface_edit = "wall"
        win._finish_upload(_result(surface_timestamps=[2]))
        QThreadPool.globalInstance().waitForDone(5000)
        _settle()
        assert win.file_list.item(1).text() == "45-7"
    finally:
        win.close()


def test_an_upload_with_nothing_applied_starts_no_refresh(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        started = []
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: started.append(1))
        win._finish_upload(_result(timestamps=[1], uploaded=1))
        assert started == []
        win._finish_upload(_result(deleted_timestamps=[2]))   # never sent: ignored
        assert started == []
        win._manifest.get(_THREE[1]).surface_edit = "wall"
        win._finish_upload(_result(surface_timestamps=[2]))
        assert started == [1]
    finally:
        win.close()


def test_a_refresh_without_surface_fields_keeps_the_uploaded_surface(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
        win._on_surface_chosen("floor")
        win._on_upload()
        win._finish_upload(_result(surface_timestamps=[1]))
        win._on_photo_refresh_done([{"timestamp": n, "reportPhotoNum": n}
                                    for n in (1, 2, 3)])
        entry = win._manifest.get(_THREE[0])
        assert (entry.surface, entry.surface_edit, entry.tilt_source) == (
            "floor", None, "manual")
        assert _surface(win, 0) == i18n.tr("surface_floor")
    finally:
        win.close()


def test_an_older_refresh_result_is_ignored(tmp_path, monkeypatch):
    from PyQt5.QtCore import QThreadPool
    win = _three(tmp_path, monkeypatch)
    try:
        class Client:
            def __init__(self, num):
                self.num = num

            def list_photos(self, session_id, *, offset=0, limit=100, **_kw):
                return {"photos": [{"timestamp": 3, "reportPhotoNum": self.num}],
                        "total": 1}
        started = []
        monkeypatch.setattr(QThreadPool.globalInstance().__class__, "start",
                            lambda pool, runnable, *a: started.append(runnable))
        win._client = Client(8)
        win._start_photo_refresh()                         # older
        win._client = Client(9)
        win._start_photo_refresh()                         # newer
        started[1].run()
        _settle()
        assert win.file_list.item(2).text() == "45-9"
        started[0].run()                                   # arrives late
        _settle()
        assert win.file_list.item(2).text() == "45-9"
        assert win._manifest.get(_THREE[2]).report_photo_num == 9
    finally:
        win.close()


# ---------------------------------------------------------------- left image-list column
def _list_width(win):
    return win._splitter.sizes()[0]


def test_the_list_has_its_own_column_left_of_the_canvas(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        splitter = win._splitter
        assert splitter.count() == 3
        assert splitter.widget(0) is win._list_column
        assert splitter.widget(1) is win.canvas
        tools_panel = splitter.widget(2)
        for w in (win._lbl_job_info, win._btn_help, win._list_header, win.file_list,
                  win.btn_prev, win.btn_next, win.btn_save, win._range_bar):
            assert win._list_column.isAncestorOf(w), w
            assert not tools_panel.isAncestorOf(w), w
        for w in (win._grp_tools, win._grp_display, win._surface_row, win.btn_upload):
            assert tools_panel.isAncestorOf(w), w
        assert _list_width(win) == 280
    finally:
        win.close()


def test_the_range_bar_sits_above_the_list(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    try:
        _settle()
        assert win._range_bar.isVisible()
        bar_y = win._range_bar.mapTo(win, win._range_bar.rect().bottomLeft()).y()
        list_y = win.file_list.mapTo(win, win.file_list.rect().topLeft()).y()
        assert bar_y < list_y
        assert win._list_column.isAncestorOf(win._range_bar)
    finally:
        win.close()


def test_the_list_column_fits_its_narrowest_width_in_every_language(tmp_path, monkeypatch):
    # Job line, header and the navigation row are never clipped at the
    # column's minimum width (it cannot be dragged narrower).
    win = _make_window(tmp_path, monkeypatch)
    try:
        column = win._list_column
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            win._splitter.setSizes([0, 10_000, 360])     # as narrow as it goes
            _settle()
            assert column.width() == ui_builder.LIST_COLUMN_MIN_WIDTH == 200, code
            assert win._list_column_body.minimumSizeHint().width() <= column.width(), code
            assert win._lbl_job_info.width() > 0, code
            for btn in (win.btn_prev, win.btn_next, win.btn_save):
                assert btn.width() >= btn.minimumSizeHint().width(), (code, btn.text())
    finally:
        i18n.set_language("ko")
        win.close()


def test_the_tool_groups_are_packed_at_the_top(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        spacing = win._panel_layout.spacing()
        for idx in (VIEW, BRUSH, SAM, BBOX):
            win._tool_picker.setCurrentIndex(idx)
            _settle()
            tools, display = win._grp_tools, win._grp_display
            assert tools.height() <= tools.sizeHint().height(), idx
            assert display.height() <= display.sizeHint().height(), idx
            assert display.y() - (tools.y() + tools.height()) == spacing, idx
            assert tools.y() <= win._panel_layout.contentsMargins().top() + 1, idx
    finally:
        win.close()


def test_the_collapse_button_folds_the_list_into_a_strip_and_back(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._splitter.moveSplitter(330, 1)
        _settle()
        assert abs(_list_width(win) - 330) <= 2
        assert win._btn_list_collapse.isVisible()
        assert not win._btn_list_expand.isVisible()
        win._btn_list_collapse.click()
        _settle()
        assert _list_width(win) <= 24
        assert not win.file_list.isVisible()
        assert win._btn_list_expand.isVisible()
        win._btn_list_expand.click()
        _settle()
        assert abs(_list_width(win) - 330) <= 2
        assert win.file_list.isVisible()
        assert not win._btn_list_expand.isVisible()
    finally:
        win.close()


def test_l_toggles_the_list_and_a_d_still_work_while_collapsed(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    win = _make_window(tmp_path, monkeypatch)
    try:
        width = _list_width(win)
        _key(win, Qt.Key_L)
        _settle()
        assert _list_width(win) <= 24
        assert win.current_idx == 0
        _key(win, Qt.Key_D)
        assert win.current_idx == 1
        _key(win, Qt.Key_A)
        assert win.current_idx == 0
        _key(win, Qt.Key_L)
        _settle()
        assert _list_width(win) == width
    finally:
        win.close()


def test_l_reaches_the_window_from_the_brush_size_box(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        _focus_brush_size(win)
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_L)
        _settle()
        assert _list_width(win) <= 24
    finally:
        win.close()


def test_the_list_width_and_collapse_are_restored_in_a_new_window(tmp_path, monkeypatch):
    from labeling_tool.core import settings
    home = tmp_path / "settings"
    win = _make_window(tmp_path / "first", monkeypatch, settings_home=home)
    try:
        win._splitter.moveSplitter(350, 1)
        _settle()
    finally:
        win.close()
    assert settings.get_list_column_width(home) == 350
    assert settings.get_list_column_collapsed(home) is False

    win = _make_window(tmp_path / "second", monkeypatch, settings_home=home)
    try:
        _settle()
        assert abs(_list_width(win) - 350) <= 2
        win._btn_list_collapse.click()
        _settle()
    finally:
        win.close()
    assert settings.get_list_column_collapsed(home) is True

    win = _make_window(tmp_path / "third", monkeypatch, settings_home=home)
    try:
        _settle()
        assert _list_width(win) <= 24
        assert win._btn_list_expand.isVisible()
        win._btn_list_expand.click()
        _settle()
        assert abs(_list_width(win) - 350) <= 2
    finally:
        win.close()


def test_the_collapse_tooltips_follow_the_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for code in ("en", "zh", "ko"):
            i18n.set_language(code)
            assert win._btn_list_collapse.toolTip() == i18n.tr("list_collapse_tip", shortcut="L")
            assert win._btn_list_expand.toolTip() == i18n.tr("list_expand_tip", shortcut="L")
            assert "L" in win._btn_list_collapse.toolTip()
    finally:
        i18n.set_language("ko")
        win.close()


def test_the_nav_row_fits_the_default_width_in_every_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for code in ("ko", "en", "zh"):
            i18n.set_language(code)
            _settle()
            assert _list_width(win) == 280, code
            for btn in (win.btn_prev, win.btn_next, win.btn_save):
                assert btn.width() >= btn.minimumSizeHint().width(), (code, btn.toolTip())
    finally:
        i18n.set_language("ko")
        win.close()


def test_clicking_anywhere_on_the_strip_expands_the_list(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._collapse_list_column()
        _settle()
        strip = win._list_column_strip
        assert strip.cursor().shape() == Qt.PointingHandCursor
        assert strip.toolTip() == i18n.tr("list_expand_tip", shortcut="L")
        assert not win._lbl_list_strip_icon.pixmap().isNull()      # a visible list icon
        QTest.mouseClick(strip, Qt.LeftButton, pos=QPoint(strip.width() // 2,
                                                          strip.height() - 20))
        _settle()
        assert _list_width(win) == 280
        assert win.file_list.isVisible()
    finally:
        win.close()


def test_the_list_handle_is_disabled_while_collapsed(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        handle = win._splitter.handle(1)
        assert handle.isEnabled()
        win._collapse_list_column()
        _settle()
        assert not handle.isEnabled()
        win._expand_list_column()
        _settle()
        assert handle.isEnabled()
    finally:
        win.close()


def test_only_a_drag_of_the_list_handle_changes_the_saved_width(tmp_path, monkeypatch):
    from labeling_tool.core import settings
    home = tmp_path / "settings"
    win = _make_window(tmp_path, monkeypatch, settings_home=home)
    try:
        win._splitter.moveSplitter(330, 1)
        _settle()
        assert win._list_width == 330
        sizes = win._splitter.sizes()
        win._splitter.moveSplitter(sizes[0] + sizes[1] - 40, 2)    # the tool-panel handle
        _settle()
        assert win._list_width == 330
        win._collapse_list_column()
        _settle()
        assert win._list_width == 330
        win._expand_list_column()
        _settle()
        assert _list_width(win) == 330
    finally:
        win.close()
    assert settings.get_list_column_width(home) == 330


def test_a_restored_width_is_capped_to_a_third_of_the_window(tmp_path, monkeypatch):
    from labeling_tool.core import settings
    home = tmp_path / "settings"
    settings.set_list_column_state(600, False, home)
    win = _make_window(tmp_path, monkeypatch, settings_home=home)
    try:
        _settle()
        assert win._list_width == 1400 // 3
        # (the canvas's 600 px minimum and the tool panel may leave a bit less)
        assert 400 <= _list_width(win) <= 1400 // 3
    finally:
        win.close()


def test_photos_skipped_by_the_server_are_reported_and_kept(tmp_path, monkeypatch):
    # v1.0.16: someone else deleted photo 2; our edit for it was skipped. The
    # photo stays on this PC (nothing deleted locally) and the user is told.
    win = _three(tmp_path, monkeypatch)
    try:
        shown = _capture_info(monkeypatch)
        win._finish_upload(_result(timestamps=[1], uploaded=1, skipped_timestamps=[2]))
        skipped = i18n.tr("upload_skipped_summary", n=1)
        assert skipped in win.status.currentMessage()
        for code in ("ko", "zh", "en"):       # no promise that a re-fetch fixes it
            text = i18n.TRANSLATIONS[code]["upload_skipped_summary"]
            assert "가져오" not in text and "获取" not in text and "fetch" not in text
        assert _THREE[1] in win.image_files and _THREE[1] in win._manifest.photos
    finally:
        win.close()


def test_the_worker_does_not_verify_photos_the_server_skipped(tmp_path, monkeypatch):
    from labeling_tool.ui import upload_worker as UW
    seen = []
    monkeypatch.setattr("labeling_tool.api.verify.verify_registered",
                        lambda client, sid, items: seen.extend(i["timestamp"] for i in items) or [])
    w = UW.UploadWorker.__new__(UW.UploadWorker)
    w._client, w._session_id = object(), 1
    w._labeling_dir = str(tmp_path / "Labeling")
    w._verify_upload([{"timestamp": 1}, {"timestamp": 2}],
                     {"skipped_timestamps": [2]})
    assert seen == [1]


# ---------------------------------------------------------------- photos gone from the server
def test_a_skipped_photo_is_marked_not_on_the_server(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        _capture_info(monkeypatch)
        win._manifest.get(_THREE[1]).surface_edit = "wall"
        win._finish_upload(_result(timestamps=[1], uploaded=1, skipped_timestamps=[2]))
        assert win._manifest.get(_THREE[1]).server_missing is True
        assert Manifest.load(win._ws.manifest_path).get(_THREE[1]).server_missing
        item = win.file_list.item(1)
        assert item.data(ui_builder.SERVER_MISSING_ROLE) is True
        assert _mark(win, 1) is None                       # not pending
        assert i18n.tr("server_missing_tip") in item.toolTip()
        assert _THREE[1] in item.toolTip()
        assert not win.file_list.item(0).data(ui_builder.SERVER_MISSING_ROLE)
        assert (win._ws.origin_dir / _THREE[1]).exists()    # local files stay
    finally:
        win.close()


def test_a_missing_photo_with_a_leftover_delete_mark_shows_only_missing(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        entry = win._manifest.get(_THREE[1])
        entry.delete_pending = True
        entry.server_missing = True
        win._refresh_list_row(1)
        assert not win.file_list.item(1).data(ui_builder.DELETE_PENDING_ROLE)
        assert win.file_list.item(1).data(ui_builder.SERVER_MISSING_ROLE) is True
    finally:
        win.close()


def test_a_failed_save_of_the_missing_flag_is_reported(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        _capture_info(monkeypatch)

        def broken(_path):
            raise OSError("disk full")
        monkeypatch.setattr(win._manifest, "save", broken)
        win._finish_upload(_result(skipped_timestamps=[2]))
        assert win._manifest.get(_THREE[1]).server_missing is True
    finally:
        win.close()


def test_missing_photos_are_left_out_of_the_next_upload(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _stroke(win)                                       # photo 1 edited
        win._save_all_artifacts(silent=True)
        win.file_list.setCurrentRow(1)
        _settle()
        _stroke(win)                                       # photo 2 edited
        win._save_all_artifacts(silent=True)
        win._on_surface_chosen("floor")                    # photo 2 surface
        for fn in _FILES[:2]:
            win._manifest.get(fn).server_missing = True
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        win._on_upload()
        assert made == []                                  # nothing left to send
        assert win.status.currentMessage() == i18n.tr("vmw_status_no_edits")
    finally:
        win.close()


def test_a_missing_photo_does_not_block_the_others(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _stroke(win)
        win._save_all_artifacts(silent=True)
        win.file_list.setCurrentRow(1)
        _settle()
        _stroke(win)
        win._save_all_artifacts(silent=True)
        win._manifest.get(_FILES[0]).server_missing = True
        win._on_upload()
        assert [s["filename"] for s in made[0].kwargs["specs"]] == [_FILES[1]]
    finally:
        win.close()


def test_the_refresh_clears_the_missing_mark(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._manifest.get(_THREE[1]).server_missing = True
        win._refresh_list_row(1)
        win._on_photo_refresh_done([{"timestamp": 2, "reportPhotoNum": 2}])
        assert win._manifest.get(_THREE[1]).server_missing is False
        assert not win.file_list.item(1).data(ui_builder.SERVER_MISSING_ROLE)
        assert win.file_list.item(1).toolTip() == _THREE[1]
    finally:
        win.close()
