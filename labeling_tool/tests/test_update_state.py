"""The update state file: when we last checked, and which version was skipped."""
import json
from datetime import datetime, timezone

from labeling_tool.core import app_paths
from labeling_tool.update import state


def test_missing_state_reads_as_empty(tmp_path):
    st = state.load(tmp_path)
    assert st.last_check is None and st.skipped_version is None


def test_mark_checked_records_the_time(tmp_path):
    now = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)
    state.mark_checked(tmp_path, now=now)
    assert state.load(tmp_path).last_check == now.isoformat()


def test_no_throttle_remains():
    """Every launch checks; a 24-hour throttle hid fresh releases until the
    next day. last_check stays only as a record."""
    assert not hasattr(state, "should_check")


def test_skip_version_round_trip(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_broken_state_file_is_ignored(tmp_path):
    (tmp_path / state.STATE_NAME).write_text("{broken")
    st = state.load(tmp_path)
    assert st.last_check is None and st.skipped_version is None


def test_mark_checked_keeps_skipped_version(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    state.mark_checked(tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_skip_version_keeps_last_check(tmp_path):
    (tmp_path / state.STATE_NAME).write_text(
        json.dumps({"last_check": "2026-01-01T00:00:00+00:00"}))
    state.skip_version("1.0.1", tmp_path)
    assert state.load(tmp_path).last_check == "2026-01-01T00:00:00+00:00"


def test_default_home_on_linux_frozen_writes_under_xdg(monkeypatch, tmp_path):
    """No ``home`` passed: the default must resolve through user_data_home(),
    which on a Linux frozen build is the XDG data dir, not app_home()'s
    /opt/lm-labeling-tool (root-owned, read-only)."""
    monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_paths.sys, "executable",
                         str(tmp_path / "opt" / "lm-labeling-tool" / "LM_LabelingTool"))
    monkeypatch.setattr(app_paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    state.skip_version("1.0.1")  # no home= -- exercise the real default

    state_path = tmp_path / "xdg" / "lm-labeling-tool" / state.STATE_NAME
    assert state_path.exists()
    assert json.loads(state_path.read_text())["skipped_version"] == "1.0.1"
