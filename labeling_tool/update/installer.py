"""Hand the downloaded Inno Setup installer control, then quit.

Windows cannot replace a running exe, so the app launches the installer
detached and exits immediately; /RESTARTAPP makes the installer start the new
version when it is done.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SILENT_ARGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTAPP")


def build_command(installer_path: Path, log_path: Path) -> list[str]:
    return [str(installer_path), *SILENT_ARGS, f"/LOG={log_path}"]


def launch_and_exit_args() -> dict:
    """Popen kwargs that detach the installer from this process."""
    if sys.platform == "win32":
        return {"close_fds": True,
                "creationflags": subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"close_fds": True}


def launch_installer(installer_path: Path, log_path: Path,
                     popen=subprocess.Popen) -> None:
    """Start the installer detached. The caller must exit right after."""
    installer_path = Path(installer_path)
    if not installer_path.is_file():
        raise FileNotFoundError(installer_path)
    popen(build_command(installer_path, log_path), **launch_and_exit_args())
