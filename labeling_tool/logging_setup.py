"""Per-session Viewer API logging.

Writes timestamped request + download + prepare-phase entries to
<session_dir>/vapi.log so the data flow and where time is spent (e.g. client
crack-metric computation vs. network) can be monitored and diagnosed.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "labeling_tool.vapi"


def vlog() -> logging.Logger:
    """The shared Viewer API logger. Cheap no-op until a session handler is attached."""
    return logging.getLogger(LOGGER_NAME)


def attach_session_log(session_dir) -> Path:
    """Route Viewer API logs to <session_dir>/vapi.log (one active session at a time).

    Idempotent: replaces any previously attached session file handler so
    switching sessions logs to the right file.
    """
    log = vlog()
    log.setLevel(logging.INFO)
    log.propagate = False
    for h in list(log.handlers):
        if getattr(h, "_session_handler", False):
            log.removeHandler(h)
            h.close()
    path = Path(session_dir) / "vapi.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh._session_handler = True          # tag so we can replace it later
    fh.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S"))
    log.addHandler(fh)
    return path
