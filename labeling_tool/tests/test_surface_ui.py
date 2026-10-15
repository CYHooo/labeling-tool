"""Surface / delete UI pieces, tested without the labeling window: the
SurfaceRow (촬영면 buttons + tilt), the list delegate's "면" column and
per-row delete button, and the list header's third column."""
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import (
    QApplication, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from labeling_tool.core import i18n
from labeling_tool.core.window import ui_builder
from labeling_tool.core.window.surface_row import SurfaceRow

_app = QApplication.instance() or QApplication([])


def _settle(rounds: int = 10) -> None:
    for _ in range(rounds):
        QApplication.processEvents()


def _korean(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_settings_home", lambda: tmp_path / "settings")
    i18n.set_language("ko")


# ---------------------------------------------------------------- SurfaceRow
def test_a_known_surface_checks_its_button_and_shows_the_rounded_tilt(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.show()
    row.set_value("wall", False, 87.4, "sensor")
    assert row.buttons["wall"].isChecked()
    assert not row.buttons["floor"].isChecked()
    assert not row.buttons["ceiling"].isChecked()
    assert row.tilt.text() == "87°"
    assert not row.unknown.isVisible()
    assert row.label.text() == i18n.tr("surface_label")
    assert row.buttons["wall"].text() == i18n.tr("surface_wall")


def test_an_unknown_surface_checks_nothing_and_says_so(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.show()
    row.set_value("wall", False, 87.4, "sensor")
    row.set_value(None, False, None, None)
    assert not any(b.isChecked() for b in row.buttons.values())
    assert row.unknown.isVisible()
    assert row.unknown.text() == i18n.tr("surface_unknown")
    assert row.tilt.text() == "—"
    # any other string is shown as unknown too
    row.set_value("roof", False, None, None)
    assert not any(b.isChecked() for b in row.buttons.values())
    assert row.unknown.isVisible()


def test_an_edited_surface_is_marked_and_a_manual_tilt_explains_itself(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.set_value("floor", True, 10.0, "manual")
    assert row.buttons["floor"].isChecked()
    assert row.buttons["floor"].property("edited") is True
    assert row.tilt.toolTip() == i18n.tr("tilt_manual_tip")
    row.set_value("floor", False, 10.0, "sensor")
    assert row.buttons["floor"].property("edited") is False
    assert row.tilt.toolTip() == ""


def test_clicking_a_button_reports_the_surface_but_set_value_is_silent(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.show()
    spy = QSignalSpy(row.surfaceChosen)
    row.set_value("wall", False, None, None)
    row.set_value("floor", True, 3.0, "manual")
    assert len(spy) == 0
    QTest.mouseClick(row.buttons["ceiling"], Qt.LeftButton)
    assert [args[0] for args in spy] == ["ceiling"]
    # one checked at a time, and clicking the checked one keeps it checked
    assert [k for k, b in row.buttons.items() if b.isChecked()] == ["ceiling"]
    QTest.mouseClick(row.buttons["ceiling"], Qt.LeftButton)
    assert row.buttons["ceiling"].isChecked()
    assert [args[0] for args in spy] == ["ceiling", "ceiling"]


def test_clicking_the_edited_button_again_shows_it_unchecked_at_once(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.show()
    spy = QSignalSpy(row.surfaceChosen)
    row.set_value("wall", True, None, None)
    QTest.mouseClick(row.buttons["wall"], Qt.LeftButton)
    # still reported, so the window can take the edit back
    assert [args[0] for args in spy] == ["wall"]
    assert not any(b.isChecked() for b in row.buttons.values())


def test_retranslate_changes_the_texts(tmp_path, monkeypatch):
    _korean(tmp_path, monkeypatch)
    row = SurfaceRow()
    row.set_value("wall", True, 5.0, "manual")
    i18n.set_language("en")
    try:
        row.retranslate(i18n.tr)
        assert row.label.text() == "Surface"
        assert row.buttons["ceiling"].text() == "Ceiling"
        assert row.unknown.text() == "Unknown"
        assert row.tilt.toolTip() == "Corrected by hand"
    finally:
        i18n.set_language("ko")


# ---------------------------------------------------------------- delegate
def _list(rows=(("45-1", "stitched_100.jpg", "벽", False, False),
                ("45-2", "stitched_200.jpg", "바닥", True, False))):
    view = QListWidget()
    view.setItemDelegate(ui_builder.TwoPartItemDelegate(view))
    for text, file, surface, edited, pending in rows:
        item = QListWidgetItem(text)
        item.setData(ui_builder.SECONDARY_TEXT_ROLE, file)
        item.setData(ui_builder.SURFACE_ROLE, surface)
        item.setData(ui_builder.SURFACE_EDITED_ROLE, edited)
        item.setData(ui_builder.DELETE_PENDING_ROLE, pending)
        view.addItem(item)
    view.resize(340, 200)
    view.show()
    _settle()
    return view


def test_the_delegate_draws_no_new_columns_by_default():
    delegate = ui_builder.TwoPartItemDelegate()
    assert delegate.surface_width == 0
    assert delegate.delete_width == 0


def test_clicking_the_delete_icon_reports_the_row_and_keeps_the_selection():
    view = _list()
    try:
        delegate = view.itemDelegate()
        delegate.delete_width = 20
        view.setCurrentRow(0)
        spy = QSignalSpy(delegate.delete_clicked)
        rect = view.visualRect(view.model().index(1, 0))
        QTest.mouseClick(view.viewport(), Qt.LeftButton,
                         pos=QPoint(rect.right() - 10, rect.center().y()))
        assert [args[0] for args in spy] == [1]
        assert view.currentRow() == 0
        # the middle of the row selects it as before, and reports nothing
        QTest.mouseClick(view.viewport(), Qt.LeftButton,
                         pos=QPoint(rect.center().x(), rect.center().y()))
        assert len(spy) == 1
        assert view.currentRow() == 1
    finally:
        view.close()


def _send(view, kind, pos, buttons):
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QMouseEvent
    button = Qt.NoButton if kind == QEvent.MouseMove else Qt.LeftButton
    event = QMouseEvent(kind, pos, view.viewport().mapToGlobal(pos),
                        button, buttons, Qt.NoModifier)
    QApplication.sendEvent(view.viewport(), event)


def test_a_shaky_click_on_the_delete_icon_does_not_switch_the_photo():
    from PyQt5.QtCore import QEvent
    view = _list()
    try:
        delegate = view.itemDelegate()
        delegate.delete_width = 20
        view.setCurrentRow(0)
        spy = QSignalSpy(delegate.delete_clicked)
        rect = view.visualRect(view.model().index(1, 0))
        pos = QPoint(rect.right() - 10, rect.center().y())
        _send(view, QEvent.MouseButtonPress, pos, Qt.LeftButton)
        _send(view, QEvent.MouseMove, pos + QPoint(1, 0), Qt.LeftButton)
        _send(view, QEvent.MouseMove, pos + QPoint(-30, 0), Qt.LeftButton)
        _send(view, QEvent.MouseButtonRelease, pos + QPoint(-30, 0), Qt.NoButton)
        assert view.currentRow() == 0
        assert [args[0] for args in spy] == [1]
        # after the release the list drags and selects as before
        QTest.mouseClick(view.viewport(), Qt.LeftButton,
                         pos=QPoint(rect.center().x(), rect.center().y()))
        assert view.currentRow() == 1
    finally:
        view.close()


def test_a_double_click_on_the_delete_icon_toggles_twice():
    from PyQt5.QtCore import QEvent
    view = _list()
    try:
        delegate = view.itemDelegate()
        delegate.delete_width = 20
        view.setCurrentRow(0)
        spy = QSignalSpy(delegate.delete_clicked)
        rect = view.visualRect(view.model().index(1, 0))
        pos = QPoint(rect.right() - 10, rect.center().y())
        # Qt's sequence for a double-click: the second press arrives as DblClick
        _send(view, QEvent.MouseButtonPress, pos, Qt.LeftButton)
        _send(view, QEvent.MouseButtonRelease, pos, Qt.NoButton)
        _send(view, QEvent.MouseButtonDblClick, pos, Qt.LeftButton)
        _send(view, QEvent.MouseButtonRelease, pos, Qt.NoButton)
        assert [args[0] for args in spy] == [1, 1]
        assert view.currentRow() == 0
    finally:
        view.close()


def test_without_a_delete_column_the_row_end_selects_the_row():
    view = _list()
    try:
        delegate = view.itemDelegate()
        view.setCurrentRow(0)
        spy = QSignalSpy(delegate.delete_clicked)
        rect = view.visualRect(view.model().index(1, 0))
        QTest.mouseClick(view.viewport(), Qt.LeftButton,
                         pos=QPoint(rect.right() - 10, rect.center().y()))
        assert len(spy) == 0
        assert view.currentRow() == 1
    finally:
        view.close()


def _red_pixels(view, row: int) -> int:
    rect = view.visualRect(view.model().index(row, 0))
    image = view.viewport().grab(rect).toImage().convertToFormat(QImage.Format_RGB32)
    target = QColor("#e05a5a")
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            c = QColor(image.pixel(x, y))
            if (abs(c.red() - target.red()) < 30 and abs(c.green() - target.green()) < 30
                    and abs(c.blue() - target.blue()) < 30):
                count += 1
    return count


def test_a_row_marked_for_deletion_is_drawn_red():
    view = _list(rows=(("45-1", "stitched_100.jpg", "벽", False, False),
                       ("45-2", "stitched_200.jpg", "벽", False, True)))
    try:
        delegate = view.itemDelegate()
        delegate.surface_width = 30
        delegate.delete_width = 20
        view.setCurrentRow(-1)
        view.clearSelection()
        view.viewport().update()
        _settle()
        assert _red_pixels(view, 0) == 0
        assert _red_pixels(view, 1) > 20
    finally:
        view.close()


def test_the_surface_column_fits_its_widest_text():
    from PyQt5.QtGui import QFont, QFontMetrics
    delegate = ui_builder.TwoPartItemDelegate()
    font = QFont()
    delegate.fit_surface_column(["벽", "Ceiling", "면"], font)
    assert delegate.surface_width == QFontMetrics(font).horizontalAdvance("Ceiling")
    delegate.fit_surface_column([], font)
    assert delegate.surface_width == 0


# ---------------------------------------------------------------- header
def test_the_header_keeps_two_titles_unless_given_a_surface_title():
    view = _list()
    header = ui_builder.ListHeader(view)
    header.set_labels("번호", "파일 이름")
    assert header.labels() == ("번호", "파일 이름")
    assert header.surface_label() == ""
    header.set_labels("번호", "파일 이름", "면")
    assert header.labels() == ("번호", "파일 이름")
    assert header.surface_label() == "면"
    view.close()


def test_the_header_columns_make_room_for_the_surface_column():
    # header and list in one window, as in the side panel (column_offsets
    # maps both into the same top-level widget)
    box = QWidget()
    lay = QVBoxLayout(box)
    view = QListWidget()
    view.setItemDelegate(ui_builder.TwoPartItemDelegate(view))
    header = ui_builder.ListHeader(view)
    lay.addWidget(header)
    lay.addWidget(view)
    box.resize(340, 200)
    box.show()
    _settle()
    try:
        delegate = view.itemDelegate()
        delegate.fit_primary_column(["45-1", "45-2"], view.font())
        number_x, surface_x, file_x = header.column_offsets()
        gap = ui_builder._PART_GAP
        assert surface_x == number_x + delegate.primary_column_width() + gap
        assert file_x == surface_x            # no surface column yet
        delegate.surface_width = 30
        number_x, surface_x, file_x = header.column_offsets()
        assert file_x == surface_x + 30 + gap
    finally:
        box.close()


def test_a_row_not_on_the_server_is_grey_not_red():
    view = _list(rows=(("45-1", "stitched_100.jpg", "벽", False, True),))
    try:
        delegate = view.itemDelegate()
        delegate.surface_width = 30
        delegate.delete_width = 20
        view.item(0).setData(ui_builder.SERVER_MISSING_ROLE, True)
        view.setCurrentRow(-1)
        view.clearSelection()
        view.viewport().update()
        _settle()
        assert _red_pixels(view, 0) == 0          # not drawn as a delete
    finally:
        view.close()


def test_the_missing_label_takes_the_delete_label_slot(monkeypatch):
    drawn = []
    real = ui_builder.layout_pending_row

    def spy(nm, lm, name, label, width):
        drawn.append(label)
        return real(nm, lm, name, label, width)
    monkeypatch.setattr(ui_builder, "layout_pending_row", spy)
    view = _list(rows=(("45-1", "stitched_100.jpg", "벽", False, False),))
    try:
        delegate = view.itemDelegate()
        delegate.delete_width = 20
        view.item(0).setData(ui_builder.SERVER_MISSING_ROLE, True)
        view.viewport().repaint()
        _settle()
        assert i18n.tr("server_missing_label") in drawn
    finally:
        view.close()
