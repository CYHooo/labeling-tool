"""Labeling window side panel: one-line job info with a help button, image
list with a header, one navigation row with a single save, a 2x2 tool
picker where the selected tool IS the editing mode (its how-to and options
below it), a display/scale group, and the upload button pinned to the
bottom."""
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
                 focus=None):
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
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
def test_job_info_is_one_line_with_a_help_button(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        expected = i18n.tr("job_info_line", job=45, name="교량 정기점검",
                           count=i18n.tr("photo_count", n=2))
        assert win._lbl_job_info.full_text() == expected
        assert win._lbl_job_info.toolTip() == expected
        assert not win._btn_help.icon().isNull()
    finally:
        win.close()


def test_job_info_without_a_name_shows_a_dash(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, inspection_name=None)
    try:
        assert " · — · " in win._lbl_job_info.full_text()
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


def test_the_viewer_window_shows_the_surface_column_trash_and_row(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        delegate = win.file_list.itemDelegate()
        assert win._surface_row.isVisible()
        assert delegate.delete_width == 22
        assert delegate.surface_width > 0
        assert win._list_header.surface_label() == i18n.tr("list_col_surface")
    finally:
        win.close()


# ---------------------------------------------------------------- navigation
def test_one_navigation_row_with_a_single_save(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win.btn_prev.text() == i18n.tr("btn_prev") == "이전 사진"
        assert win.btn_next.text() == i18n.tr("btn_next") == "다음 사진"
        assert not hasattr(win, "_btn_brush_save")
        saves = [b for b in win.findChildren(QPushButton)
                 if b.isVisible() and b.text() == i18n.tr("btn_save")]
        assert saves == [win.btn_save]
        y = {b.mapTo(win, b.rect().topLeft()).y() for b in (win.btn_prev, win.btn_next, win.btn_save)}
        assert len(y) == 1                                   # same row
        assert "A" in win.btn_prev.toolTip() and "D" in win.btn_next.toolTip()
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
            assert win.btn_prev.text() == i18n.tr("btn_prev")
            assert win._lbl_job_info.full_text() == i18n.tr(
                "job_info_line", job=45, name="교량 정기점검",
                count=i18n.tr("photo_count", n=2))
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
    win = _make_window(tmp_path, monkeypatch)
    try:
        tools = win._grp_tools
        assert tools.height() <= tools.sizeHint().height()      # not stretched
        list_before, tools_before = win.file_list.height(), tools.height()
        win.resize(1400, 1100)
        QApplication.processEvents()
        assert tools.height() == tools_before
        assert win.file_list.height() - list_before >= 150      # most of the 200 px
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
            heights[idx] = (win._grp_tools.height(), win.file_list.height())
        assert heights[VIEW][0] < heights[BRUSH][0]              # tools shrink
        assert heights[VIEW][1] > heights[BRUSH][1]              # the list gets it
    finally:
        win.close()


def test_no_tool_makes_the_panel_scroll_in_a_900px_window(tmp_path, monkeypatch):
    # The list gives way instead: with the tallest tool page the display
    # group must still be on screen without scrolling.
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
        side = win._splitter.widget(1)
        win._splitter.setSizes([10_000, 0])                  # panel at its minimum
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


def test_the_trash_button_marks_a_photo_for_deletion_and_back(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(1)
        _settle()
        assert win.current_idx == 1
        win.file_list.itemDelegate().delete_clicked.emit(0)
        entry = win._manifest.get(_FILES[0])
        assert entry.delete_pending
        assert Manifest.load(win._ws.manifest_path).get(_FILES[0]).delete_pending
        assert win.file_list.item(0).data(ui_builder.DELETE_PENDING_ROLE)
        assert _mark(win, 0) == "pending"
        assert win.current_idx == 1
        win.file_list.itemDelegate().delete_clicked.emit(0)
        assert not entry.delete_pending
        assert not Manifest.load(win._ws.manifest_path).get(_FILES[0]).delete_pending
        assert not win.file_list.item(0).data(ui_builder.DELETE_PENDING_ROLE)
        assert _mark(win, 0) is None
        assert win.current_idx == 1
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
        win._on_delete_clicked(0)
        assert win._manifest.get(_FILES[0]).delete_pending
        assert "disk full" in win.status.currentMessage()
        win._on_surface_chosen("floor")
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


def test_upload_with_only_deletes_asks_first(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        asked = []
        monkeypatch.setattr(win, "_confirm_deletes", lambda d: asked.append(d) or False)
        win._on_delete_clicked(1)
        win._on_upload()
        assert asked == [[{"timestamp": 2}]]
        assert made == []                                  # cancelled: nothing sent
        monkeypatch.setattr(win, "_confirm_deletes", lambda d: True)
        win._on_upload()
        assert len(made) == 1
        assert made[0].kwargs["specs"] == []
        assert made[0].kwargs["deletes"] == [{"timestamp": 2}]
        assert list(made[0].kwargs["surface_updates"]) == []
    finally:
        win.close()


def test_upload_with_only_a_surface_change_sends_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        monkeypatch.setattr(win, "_confirm_deletes",
                            lambda d: _unexpected("no delete to confirm"))
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


def test_a_photo_marked_for_deletion_is_not_uploaded_as_an_edit(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        monkeypatch.setattr(win, "_confirm_deletes", lambda d: True)
        _stroke(win)                                       # photo 1 edited ...
        win._save_all_artifacts(silent=True)
        win.file_list.setCurrentRow(1)
        _settle()
        _stroke(win)                                       # ... and photo 2
        win._save_all_artifacts(silent=True)
        win._on_delete_clicked(0)                          # photo 1 goes
        win._on_upload()
        assert [s["filename"] for s in made[0].kwargs["specs"]] == [_FILES[1]]
        assert made[0].kwargs["deletes"] == [{"timestamp": 1}]
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
        monkeypatch.setattr(win, "_confirm_deletes", lambda d: True)
        outside = win._manifest.get(_SIX[0])               # not listed
        outside.delete_pending = True
        outside.surface_edit = "wall"
        win._on_delete_clicked(0)                          # _SIX[1], ts 2
        win._on_upload()
        assert made[0].kwargs["deletes"] == [{"timestamp": 2}]
        assert made[0].kwargs["surface_updates"] == []
    finally:
        win.close()


def test_the_delete_confirmation_lists_numbers_and_has_two_buttons(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, files=tuple(f"p{n:02d}.jpg" for n in range(1, 24)))
    try:
        dels = [{"timestamp": n} for n in range(1, 24)]
        box, ok = win._build_delete_confirm(dels)
        try:
            text = box.text()
            assert text.startswith(i18n.tr("delete_confirm_msg", count=23, numbers="")
                                   .split("\n")[0])
            assert "45-1, 45-2" in text and "45-20" in text and "45-21" not in text
            assert i18n.tr("delete_confirm_more", n=3) in text
            assert box.windowTitle() == i18n.tr("delete_confirm_title")
            texts = sorted(b.text() for b in box.buttons())
            assert texts == sorted([i18n.tr("delete_confirm_ok"),
                                    i18n.tr("delete_confirm_cancel")])
            assert ok.text() == i18n.tr("delete_confirm_ok")
            assert box.defaultButton() is not ok           # Enter does not delete
        finally:
            box.deleteLater()
    finally:
        win.close()


def test_confirm_deletes_returns_the_choice(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for choose_ok in (True, False):
            def fake_exec(box, _choose=choose_ok):
                target = next(b for b in box.buttons()
                              if (b.text() == i18n.tr("delete_confirm_ok")) == _choose)
                target.click()
                return 0
            monkeypatch.setattr(QMessageBox, "exec_", fake_exec)
            assert win._confirm_deletes([{"timestamp": 1}]) is choose_ok
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
           "verify_failures": [], "batch_id": "b", "deleted_timestamps": [],
           "surface_timestamps": []}
    out.update(kw)
    return out


def _three(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    return _make_window(tmp_path, monkeypatch, files=_THREE)


def _current(win):
    return win.image_files[win.current_idx] if win.current_idx >= 0 else None


def test_a_deleted_current_photo_gives_way_to_the_next(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(1)
        _settle()
        win._manifest.get(_THREE[1]).delete_pending = True
        win._finish_upload(_result(deleted_timestamps=[2]))
        assert not (win._ws.origin_dir / _THREE[1]).exists()
        assert sorted(win._manifest.photos) == [_THREE[0], _THREE[2]]
        assert sorted(Manifest.load(win._ws.manifest_path).photos) == [_THREE[0], _THREE[2]]
        assert win.file_list.count() == 2 and win.image_files == [_THREE[0], _THREE[2]]
        assert _current(win) == _THREE[2]
        assert win.file_list.currentRow() == 1
        assert win.status.currentMessage() != i18n.tr("vmw_status_no_items")
        assert i18n.tr("upload_deleted_summary", n=1) in win.status.currentMessage()
    finally:
        win.close()


def test_a_deleted_last_photo_gives_way_to_the_previous(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(2)
        _settle()
        win._finish_upload(_result(deleted_timestamps=[3]))
        assert _current(win) == _THREE[1]
    finally:
        win.close()


def test_deleting_another_photo_keeps_the_current_one_and_its_edit(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        _stroke(win)                                       # unsaved, on photo 1
        win._finish_upload(_result(deleted_timestamps=[3]))
        assert _current(win) == _THREE[0]
        assert win._edited.get(_THREE[0])                  # the canvas was not reloaded
        assert win.image_files == [_THREE[0], _THREE[1]]
    finally:
        win.close()


def test_a_failed_delete_stays_marked(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._manifest.get(_THREE[1]).delete_pending = True
        win._finish_upload(_result(failed=[{"timestamps": [], "error": "boom",
                                            "surface_timestamps": [],
                                            "delete_timestamps": [2]}]))
        assert win._manifest.get(_THREE[1]).delete_pending
        assert (win._ws.origin_dir / _THREE[1]).exists()
        assert win.file_list.count() == 3
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


def test_a_delete_confirmed_by_the_server_goes_even_if_unmarked_meanwhile(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._on_delete_clicked(1)
        win._on_delete_clicked(1)                          # unmarked during the upload
        win._finish_upload(_result(deleted_timestamps=[2]))
        assert _THREE[1] not in win._manifest.photos
        assert not (win._ws.origin_dir / _THREE[1]).exists()
    finally:
        win.close()


def test_a_range_view_keeps_the_rest_of_its_photos_after_a_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _range_window(tmp_path, monkeypatch)
    try:
        win._finish_upload(_result(deleted_timestamps=[3]))
        assert _rows(win) == [_SIX[1], _SIX[3]]
        assert _SIX[2] not in win._focus.filenames
        assert win._lbl_range.text() == i18n.tr("list_range_label", a=2, b=4, n=2)
        win._toggle_range_view()                           # show all
        assert len(_rows(win)) == 5
        win._toggle_range_view()                           # back to the range
        assert _rows(win) == [_SIX[1], _SIX[3]]
    finally:
        win.close()


def test_a_range_emptied_by_deletes_shows_every_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win = _range_window(tmp_path, monkeypatch)
    try:
        win._finish_upload(_result(deleted_timestamps=[2, 3, 4]))
        assert _rows(win) == [_SIX[0], _SIX[4], _SIX[5]]
        assert win._focus is None and not win._range_bar.isVisibleTo(win)
        assert _current(win) == _SIX[0]
    finally:
        win.close()


def test_deleting_every_photo_clears_the_canvas(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win._finish_upload(_result(deleted_timestamps=[1, 2, 3]))
        _settle()
        assert win.image_files == [] and win.file_list.count() == 0
        assert win.current_idx == -1
        assert win.canvas._pixmap is None
        assert not win.btn_upload.isEnabled()
        assert win._manifest.photos == {}
        win.go_next()
        win.go_prev()                                      # nothing to show, no error
    finally:
        win.close()


def test_refreshed_numbers_show_and_the_current_photo_stays(tmp_path, monkeypatch):
    win = _three(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(2)
        _settle()
        win._finish_upload(_result(deleted_timestamps=[2]))
        assert win.file_list.item(1).text() == "45-3"
        win._on_photo_refresh_done([{"timestamp": 1, "reportPhotoNum": 1},
                                    {"timestamp": 3, "reportPhotoNum": 2,
                                     "surface": "wall"}])
        assert win.file_list.item(1).text() == "45-2"
        assert _surface(win, 1) == i18n.tr("surface_wall")
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


def test_a_delete_starts_the_refresh_in_the_background(tmp_path, monkeypatch):
    from PyQt5.QtCore import QThreadPool
    win = _three(tmp_path, monkeypatch)
    try:
        class Client:
            base_url = ""

            def list_photos(self, session_id, *, offset=0, limit=100, **_kw):
                photos = [{"timestamp": 1, "reportPhotoNum": 1},
                          {"timestamp": 3, "reportPhotoNum": 7}]
                return {"photos": photos[offset:offset + limit], "total": 2}
        win._client = Client()
        win._finish_upload(_result(deleted_timestamps=[2]))
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
        win._finish_upload(_result(deleted_timestamps=[2]))
        assert started == [1]
    finally:
        win.close()
