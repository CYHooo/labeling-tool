"""Closing the labeling window while photos still carry ● (edited, not
uploaded) asks first: upload and close / close / cancel. An upload that is
still running keeps the window open."""
from PyQt5.QtWidgets import QApplication, QMessageBox

from labeling_tool.core import i18n
from labeling_tool.session import mask_store
from labeling_tool.tests.test_side_panel import (
    _FILES, _SIX, _fake_worker, _make_window, _range_window, _result,
)
from labeling_tool.ui.main_window import ViewerMainWindow


def _answer(monkeypatch, choice):
    """Answer the close prompt with `choice`, recording each count asked."""
    counts = []

    def ask(_self, count):
        counts.append(count)
        return choice
    monkeypatch.setattr(ViewerMainWindow, "_ask_close_unuploaded", ask)
    return counts


def _edit_mask(win, filename):
    """A saved mask in Labeling/ that was never uploaded = ●."""
    win.output_dir.mkdir(parents=True, exist_ok=True)
    (win.output_dir / mask_store.mask_name(filename)).write_bytes(b"x")


def _really_close(win, monkeypatch):
    _answer(monkeypatch, "close")
    win._upload_worker = None
    win.close()


def test_nothing_pending_closes_without_asking(tmp_path, monkeypatch, close_prompts):
    win = _make_window(tmp_path, monkeypatch)
    assert win.close()
    assert close_prompts == []


def test_cancel_keeps_the_window_open(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        counts = _answer(monkeypatch, "cancel")
        win._on_surface_chosen("floor")
        _edit_mask(win, _FILES[1])
        assert not win.close()
        assert win.isVisible()
        assert counts == [2]
    finally:
        _answer(monkeypatch, "close")
        win.close()


def test_close_closes_and_keeps_the_edits(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    counts = _answer(monkeypatch, "close")
    win._on_surface_chosen("floor")
    assert win.close()
    assert counts == [1]
    assert win._manifest.get(_FILES[0]).surface_edit == "floor"


def test_uploaded_photos_and_photos_gone_from_the_server_are_not_counted(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, synced=(_FILES[0],))
    counts = _answer(monkeypatch, "close")
    _edit_mask(win, _FILES[0])                     # uploaded since: ✓
    win._manifest.get(_FILES[1]).server_missing = True
    _edit_mask(win, _FILES[1])
    assert win._list_item_mark(_FILES[0]) == "uploaded"
    assert win.close()
    assert counts == []


def test_an_unsaved_repair_area_change_on_an_uploaded_photo_counts(tmp_path, monkeypatch):
    # saved before asking: the change re-opens the uploaded photo
    win = _make_window(tmp_path, monkeypatch, synced=_FILES)
    counts = _answer(monkeypatch, "close")
    for f in _FILES:
        _edit_mask(win, f)
    current = win.image_files[win.current_idx]
    win._bbox_edited[current] = True
    assert win.close()
    assert counts == [1]
    assert not win._manifest.get(current).synced


def test_a_range_view_counts_only_the_listed_photos(tmp_path, monkeypatch):
    win = _range_window(tmp_path, monkeypatch)
    counts = _answer(monkeypatch, "close")
    _edit_mask(win, _SIX[0])          # outside the range: not listed
    _edit_mask(win, _SIX[2])
    assert win.close()
    assert counts == [1]


def test_an_unconfirmed_sam_selection_counts_and_cancel_keeps_it(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        committed = []
        monkeypatch.setattr(win.canvas, "has_sam_preview", lambda: not committed)
        monkeypatch.setattr(win.canvas, "commit_sam", lambda: committed.append(True) or True)
        counts = _answer(monkeypatch, "cancel")
        assert not win.close()
        assert counts == [1] and committed == []     # cancel changes nothing
        counts = _answer(monkeypatch, "close")
        assert win.close()
        assert counts == [1] and committed == [True]  # closing confirms it
    finally:
        _answer(monkeypatch, "close")
        win.close()


def test_cancel_keeps_unconfirmed_repair_area_points(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        counts = _answer(monkeypatch, "cancel")
        win._on_surface_chosen("floor")
        win.canvas.bbox_interaction.in_progress_clicks = [(1, 1)]
        assert not win.close()
        assert win.canvas.bbox_interaction.in_progress_clicks == [(1, 1)]
        assert counts == [1]                      # a lone point makes no box
    finally:
        _answer(monkeypatch, "close")
        win.close()


def test_repair_area_points_enough_for_a_box_count(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        counts = _answer(monkeypatch, "cancel")
        win.canvas._bbox_padding_px = 4.0
        win.canvas.bbox_interaction.in_progress_clicks = [(1, 1), (5, 5)]
        assert not win.close()
        assert counts == [1]
    finally:
        _answer(monkeypatch, "close")
        win.close()


def test_upload_and_close_starts_the_upload_and_stays_open(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        _answer(monkeypatch, "upload")
        win._on_surface_chosen("floor")
        assert not win.close()
        assert len(made) == 1
        assert win.isVisible()
    finally:
        _really_close(win, monkeypatch)


def test_a_finished_upload_closes_the_window(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    win._client = object()
    _fake_worker(monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
    counts = _answer(monkeypatch, "upload")
    win._on_surface_chosen("floor")
    win.close()
    win._on_upload_done(_result(surface_timestamps=[1]))
    QApplication.processEvents()
    assert not win.isVisible()
    assert counts == [1]               # nothing left: no second question


def test_photos_still_pending_after_the_upload_ask_again(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
        _edit_mask(win, _FILES[0])
        _edit_mask(win, _FILES[1])
        counts = _answer(monkeypatch, "upload")
        win.close()
        counts2 = _answer(monkeypatch, "cancel")
        win._on_upload_done(_result(timestamps=[1], uploaded=1))   # photo 2 not confirmed
        QApplication.processEvents()
        assert counts == [2] and counts2 == [1]
        assert win.isVisible()
    finally:
        _really_close(win, monkeypatch)


def test_a_failed_upload_keeps_the_window_open(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        _answer(monkeypatch, "upload")
        win._on_surface_chosen("floor")
        win.close()
        win._on_upload_error("boom")
        QApplication.processEvents()
        assert win.isVisible()
        # a later upload the user starts by hand does not close the window
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
        win._on_upload()
        win._on_upload_done(_result(surface_timestamps=[1]))
        QApplication.processEvents()
        assert win.isVisible()
    finally:
        _really_close(win, monkeypatch)


def test_upload_and_close_that_cannot_start_stays_open(tmp_path, monkeypatch):
    # offline: the usual warning, the window stays, and nothing closes later
    win = _make_window(tmp_path, monkeypatch)
    try:
        _answer(monkeypatch, "upload")
        win._on_surface_chosen("floor")
        assert not win.close()
        assert win.isVisible()
        assert not getattr(win, "_close_after_upload", False)
    finally:
        _really_close(win, monkeypatch)


def test_upload_and_close_without_a_scale_stays_open(tmp_path, monkeypatch):
    win = _make_window(tmp_path, monkeypatch, second_photo_scale=0.0)
    try:
        win._client = object()
        made = _fake_worker(monkeypatch)
        counts = _answer(monkeypatch, "upload")
        _edit_mask(win, _FILES[1])                 # only the unscaled photo
        assert not win.close()
        assert counts == [1] and made == []
        assert not win._close_after_upload
    finally:
        _really_close(win, monkeypatch)


def test_an_upload_finishing_while_the_busy_notice_shows_still_closes(tmp_path, monkeypatch):
    # X pressed again during "upload and close"; the result arrives then
    win = _make_window(tmp_path, monkeypatch)
    win._client = object()
    _fake_worker(monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(win, "_start_photo_refresh", lambda: None)
    _answer(monkeypatch, "upload")
    win._on_surface_chosen("floor")
    assert not win.close()
    monkeypatch.setattr(ViewerMainWindow, "_tell_upload_running",
                        lambda self: self._on_upload_done(_result(surface_timestamps=[1])))
    assert not win.close()
    QApplication.processEvents()
    assert not win.isVisible()


def test_the_busy_notice_is_not_modal(tmp_path, monkeypatch, close_prompts):
    win = _make_window(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(QMessageBox, "exec_", lambda *a: (_ for _ in ()).throw(
            AssertionError("the notice must not block")))
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("the notice must not block")))
        close_prompts.real_busy(win)
        boxes = [b for b in win.findChildren(QMessageBox) if b.isVisible()]
        assert [b.text() for b in boxes] == [i18n.tr("close_upload_running_msg")]
        boxes[0].close()
    finally:
        win.close()


def test_closing_while_an_upload_runs_is_refused(tmp_path, monkeypatch, close_prompts):
    win = _make_window(tmp_path, monkeypatch)
    try:
        win._client = object()
        _fake_worker(monkeypatch)
        win._on_surface_chosen("floor")
        win._on_upload()
        assert not win.close()
        assert close_prompts == [("busy", None)]
    finally:
        _really_close(win, monkeypatch)


def test_the_prompt_offers_upload_close_and_cancel(tmp_path, monkeypatch, close_prompts):
    win = _make_window(tmp_path, monkeypatch)
    try:
        seen = []

        def run(box):
            seen.append(([b.text() for b in box.buttons()],
                         box.defaultButton().text(), box.escapeButton().text(),
                         box.text()))
            box.escapeButton().click()
        monkeypatch.setattr(QMessageBox, "exec_", run)
        assert close_prompts.real(win, 3) == "cancel"
        buttons, default, escape, text = seen[0]
        assert set(buttons) == {i18n.tr("close_unuploaded_btn_upload"),
                                i18n.tr("close_unuploaded_btn_close"),
                                i18n.tr("close_unuploaded_btn_cancel")}
        assert default == i18n.tr("close_unuploaded_btn_upload")
        assert escape == i18n.tr("close_unuploaded_btn_cancel")
        assert text == i18n.tr("close_unuploaded_msg", n=3)

        def pick(label):
            def run(box):
                next(b for b in box.buttons() if b.text() == i18n.tr(label)).click()
            monkeypatch.setattr(QMessageBox, "exec_", run)
        pick("close_unuploaded_btn_upload")
        assert close_prompts.real(win, 1) == "upload"
        pick("close_unuploaded_btn_close")
        assert close_prompts.real(win, 1) == "close"
    finally:
        win.close()


def test_close_prompt_texts_exist_in_every_language():
    for code in ("ko", "zh", "en"):
        i18n.set_language(code)
        for key in ("close_unuploaded_title", "close_unuploaded_btn_upload",
                    "close_unuploaded_btn_close", "close_unuploaded_btn_cancel",
                    "close_upload_running_title", "close_upload_running_msg"):
            assert i18n.tr(key) != key, (code, key)
        assert "3" in i18n.tr("close_unuploaded_msg", n=3)
    i18n.set_language("ko")
