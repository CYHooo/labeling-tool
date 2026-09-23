"""Throttling and skipped versions for the update check."""
from datetime import datetime, timedelta, timezone

from labeling_tool.update import state


def test_missing_state_allows_check(tmp_path):
    st = state.load(tmp_path)
    assert st.last_check is None and st.skipped_version is None
    assert state.should_check(st) is True


def test_recent_check_is_throttled(tmp_path):
    now = datetime.now(timezone.utc)
    state.mark_checked(tmp_path, now=now)
    st = state.load(tmp_path)
    assert state.should_check(st, now=now + timedelta(hours=1)) is False
    assert state.should_check(st, now=now + timedelta(hours=25)) is True


def test_skip_version_round_trip(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"


def test_broken_state_file_is_ignored(tmp_path):
    (tmp_path / state.STATE_NAME).write_text("{broken")
    st = state.load(tmp_path)
    assert st.last_check is None
    assert state.should_check(st) is True


def test_mark_checked_keeps_skipped_version(tmp_path):
    state.skip_version("1.0.1", tmp_path)
    state.mark_checked(tmp_path)
    assert state.load(tmp_path).skipped_version == "1.0.1"
