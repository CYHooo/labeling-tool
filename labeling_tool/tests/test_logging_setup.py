from labeling_tool.logging_setup import attach_session_log, vlog


def _flush():
    for h in vlog().handlers:
        h.flush()


def test_attach_writes_to_session_vapi_log(tmp_path):
    p = attach_session_log(tmp_path)
    assert p == tmp_path / "vapi.log"
    vlog().info("hello %d", 42)
    _flush()
    assert "hello 42" in p.read_text(encoding="utf-8")


def test_attach_replaces_previous_session_handler(tmp_path):
    attach_session_log(tmp_path / "a")
    attach_session_log(tmp_path / "b")
    session_handlers = [h for h in vlog().handlers
                        if getattr(h, "_session_handler", False)]
    assert len(session_handlers) == 1          # only the latest session
    vlog().info("to-b")
    _flush()
    assert "to-b" in (tmp_path / "b" / "vapi.log").read_text(encoding="utf-8")
