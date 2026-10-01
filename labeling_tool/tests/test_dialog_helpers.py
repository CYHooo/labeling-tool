"""save_config() must create its parent directory before writing: CONFIG_PATH
resolves to an XDG directory on a Linux frozen build, and that directory does
not exist yet on a fresh install."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_default_home_on_linux_frozen_writes_under_xdg(tmp_path):
    # CONFIG_PATH is a module-level constant computed at import time, so the
    # frozen/platform state has to be set before dialog_helpers is imported.
    # Same approach as test_frozen_module_constants_* in tests/test_app_paths.py:
    # a fresh subprocess, since monkeypatching sys.platform after the fact
    # would not make the already-computed constant re-resolve.
    exe = tmp_path / "opt" / "lm-labeling-tool" / "LM_LabelingTool"
    xdg = tmp_path / "xdg"
    code = (
        "import sys; sys.frozen = True; sys.executable = %r; sys.platform = 'linux'\n"
        "from labeling_tool.ui import dialog_helpers as d\n"
        "d.save_config('http://example.com', 'secret-key')\n"
    ) % str(exe)
    env = {**os.environ, "XDG_DATA_HOME": str(xdg)}
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                    capture_output=True, text=True, check=True)

    config_path = xdg / "lm-labeling-tool" / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data == {"base": "http://example.com", "apiKey": "secret-key"}
