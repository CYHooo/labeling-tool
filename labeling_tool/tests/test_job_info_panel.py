"""The labeling window shows the job it is working on instead of folder and
language controls: the photos come from the server, so there is nothing to
pick, and the language is switched on the sign-in / jobs screens."""
import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton

from labeling_tool.core import i18n
from labeling_tool.core.window import ui_builder
from labeling_tool.session.manifest import Manifest, PhotoEntry
from labeling_tool.session.workspace import Workspace
from labeling_tool.ui.main_window import ViewerMainWindow

_app = QApplication.instance() or QApplication([])

_FILES = ("stitched_100.jpg", "stitched_200.jpg", "stitched_300.jpg")


def _make_window(tmp_path, monkeypatch, *, inspection_name: str | None = "교량 정기점검",
                 files=_FILES, manifest_files=_FILES):
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    i18n.set_language("ko")
    ws = Workspace(root=tmp_path, session_id=45)
    ws.origin_dir.mkdir(parents=True)
    for name in files:
        cv2.imwrite(str(ws.origin_dir / name), np.zeros((8, 8, 3), np.uint8))
    manifest = Manifest(session_id=45, base="", inspection_name=inspection_name)
    for num, name in enumerate(manifest_files, start=1):
        manifest.add(PhotoEntry(filename=name, timestamp=num, photo_id=500 + num,
                                report_photo_num=num, px_per_cm=1.0))
    return ViewerMainWindow(ws, manifest, None)


def test_no_folder_pickers_or_language_selector(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win.findChildren(QComboBox) == []
        assert not hasattr(win, "_cmb_lang")
        assert not hasattr(win, "_btn_select_origin")
        assert not hasattr(win, "_btn_select_detected")
        texts = [b.text() for b in win.findChildren(QPushButton)]
        assert not any("Origin" in t or "Detected" in t for t in texts)
    finally:
        win.close()


def test_job_info_shows_id_inspection_name_and_photo_count(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        assert win._grp_job_info.title() == i18n.tr("group_job_info")
        assert win._lbl_job_id_value.text() == "45"
        assert win._lbl_inspection_value.text() == "교량 정기점검"
        assert win._lbl_photo_count_value.text() == i18n.tr("photo_count", n=3)
    finally:
        win.close()


def test_missing_inspection_name_shows_a_dash(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, inspection_name=None)
    try:
        assert win._lbl_inspection_value.text() == "—"
    finally:
        win.close()


def test_job_info_follows_language(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        for code in ("en", "zh", "ko"):
            i18n.set_language(code)
            assert win._grp_job_info.title() == i18n.tr("group_job_info")
            assert win._lbl_job_id_key.text() == i18n.tr("lbl_job_id")
            assert win._lbl_inspection_key.text() == i18n.tr("lbl_inspection_name")
            assert win._lbl_photo_count_key.text() == i18n.tr("lbl_photo_count")
            assert win._lbl_photo_count_value.text() == i18n.tr("photo_count", n=3)
    finally:
        win.close()


def test_list_items_show_job_and_photo_number_then_file_name(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        rows = [win.file_list.item(i) for i in range(win.file_list.count())]
        assert [r.text() for r in rows] == ["45-1", "45-2", "45-3"]
        assert [r.data(ui_builder.SECONDARY_TEXT_ROLE) for r in rows] == list(_FILES)
        assert [r.toolTip() for r in rows] == list(_FILES)
    finally:
        win.close()


def test_a_file_missing_from_the_manifest_is_listed_by_name(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, manifest_files=_FILES[:2])
    try:
        last = win.file_list.item(2)
        assert last.text() == "stitched_300.jpg"
        assert not last.data(ui_builder.SECONDARY_TEXT_ROLE)
    finally:
        win.close()


def test_selecting_a_row_still_opens_that_file(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win.file_list.setCurrentRow(2)
        assert win.image_files[win.current_idx] == "stitched_300.jpg"
        win.go_prev()
        assert win.file_list.currentItem().text() == "45-2"
        assert win.image_files[win.current_idx] == "stitched_200.jpg"
    finally:
        win.close()


def _paint_row(view, row, selected):
    """Paint one row through the list's delegate and return the image."""
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtWidgets import QStyle
    index = view.model().index(row, 0)
    option = view.viewOptions()
    option.rect = view.visualRect(index).translated(0, -view.visualRect(index).top())
    if selected:
        option.state |= QStyle.State_Selected
    image = QImage(option.rect.width(), option.rect.height(), QImage.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        view.itemDelegate().paint(painter, option, index)
    finally:
        painter.end()
    return image


def _has_pixel(image, predicate, width):
    from PyQt5.QtGui import QColor
    return any(predicate(QColor(image.pixel(x, y)))
               for x in range(min(width, image.width()))
               for y in range(image.height()))


def test_the_id_is_painted_in_its_status_colour_and_white_when_selected(tmp_path, monkeypatch):
    from PyQt5.QtGui import QBrush, QColor
    win = _make_window(tmp_path, monkeypatch)
    try:
        view = win.file_list
        assert isinstance(view.itemDelegate(), ui_builder.TwoPartItemDelegate)
        view.item(1).setForeground(QBrush(QColor(120, 220, 120)))     # "labeled"
        id_width = 60                                                  # "45-2" + margin

        def green(c):
            return c.green() > 180 and c.red() < 160 and c.blue() < 160

        def white(c):
            return min(c.red(), c.green(), c.blue()) > 235

        plain = _paint_row(view, 1, selected=False)
        assert _has_pixel(plain, green, id_width)
        selected = _paint_row(view, 1, selected=True)
        assert _has_pixel(selected, white, id_width)
        assert not _has_pixel(selected, green, id_width)
    finally:
        win.close()


def test_painting_a_row_leaves_the_shared_option_font_alone(tmp_path, monkeypatch):
    # The list view reuses one style option for every row of a paint pass;
    # shrinking its font in place made each later row smaller than the last.
    from PyQt5.QtGui import QImage, QPainter
    win = _make_window(tmp_path, monkeypatch)
    try:
        view = win.file_list
        option = view.viewOptions()
        before = option.font.pointSizeF()
        image = QImage(400, 40, QImage.Format_ARGB32)
        painter = QPainter(image)
        try:
            for row in range(view.count()):
                option.rect = view.visualRect(view.model().index(row, 0))
                view.itemDelegate().paint(painter, option, view.model().index(row, 0))
        finally:
            painter.end()
        assert option.font.pointSizeF() == before
    finally:
        win.close()


def test_file_names_start_in_one_column(tmp_path, monkeypatch):
    files = tuple(f"stitched_{n:03d}.jpg" for n in range(1, 12))   # 45-1 … 45-11
    win = _make_window(tmp_path, monkeypatch, files=files, manifest_files=files)
    try:
        from PyQt5.QtGui import QFontMetrics
        widest = QFontMetrics(win.file_list.font()).horizontalAdvance("45-11")
        assert win.file_list.itemDelegate()._primary_width == widest
    finally:
        win.close()
