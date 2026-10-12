from labeling_tool.core.bbox.interaction import BBoxInteraction


def test_undo_click_drops_the_last_unconfirmed_point():
    b = BBoxInteraction()
    b.on_left_press(10, 10)
    b.on_left_press(20, 20)
    assert b.undo_click() is True
    assert b.in_progress_clicks == [(10.0, 10.0)]
    assert b.undo_click() is True
    assert b.undo_click() is False             # nothing left
