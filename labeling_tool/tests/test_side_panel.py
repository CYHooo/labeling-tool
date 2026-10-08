"""Labeling window side panel: one-line job info with a help button, image
list with a header, one navigation row with a single save, a 2x2 tool
picker where the selected tool IS the editing mode (its how-to and options
below it), a display/scale group, and the upload button pinned to the
bottom."""
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QLabel, QMessageBox, QPushButton, QScrollArea,
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
                 sam_available=True, second_photo_scale=2.0):
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
    for num, name in enumerate(_FILES, start=1):
        cv2.imwrite(str(ws.origin_dir / name), np.zeros((8, 8, 3), np.uint8))
        manifest.add(PhotoEntry(filename=name, timestamp=num, photo_id=num,
                                report_photo_num=num,
                                px_per_cm=2.0 if num == 1 else second_photo_scale))
    win = ViewerMainWindow(ws, manifest, None)
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
        number_x, file_x = header.column_offsets()
        viewport = win.file_list.viewport()

        def in_viewport(x):                  # header x -> list viewport x
            return header.mapTo(win, QPoint(x, 0)).x() - viewport.mapTo(win, QPoint(0, 0)).x()

        text_left = delegate.text_left(win.file_list)
        assert in_viewport(number_x) == text_left
        assert in_viewport(file_x) == text_left + delegate.primary_column_width() + ui_builder._PART_GAP
        # the id column is at least as wide as its header, so titles never overlap
        from PyQt5.QtGui import QFontMetrics
        assert delegate.primary_column_width() >= QFontMetrics(win.file_list.font()).horizontalAdvance(
            header.labels()[0])
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


def test_crack_and_spalling_are_only_shown_with_the_brush(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for idx in (VIEW, BRUSH, SAM, BBOX):
            win._tool_picker.setCurrentIndex(idx)
            QApplication.processEvents()
            assert win._btn_cat_crack.isVisible() == (idx == BRUSH)
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


def test_category_shortcuts_work_while_the_brush_page_is_hidden(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert not win._btn_cat_spalling.isVisible()                # 보기 selected
        win.activateWindow()
        QTest.keyClick(win, Qt.Key_2)
        assert win.canvas.current_category == "spalling"
        assert win._btn_cat_spalling.isChecked()
    finally:
        win.close()


def test_the_sam_how_to_mentions_esc():
    import importlib
    for code in ("ko", "zh", "en"):
        strings = importlib.import_module(f"labeling_tool.core.i18n.strings_{code}").STRINGS
        assert "Esc" in strings["tool_sam_hint"], code


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
