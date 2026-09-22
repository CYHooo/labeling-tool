"""Writable locations: unchanged from source, next to the exe when frozen."""
import subprocess
import sys
from pathlib import Path

from labeling_tool.core import app_paths

ROOT = Path(__file__).resolve().parent.parent


def test_source_mode_paths_are_unchanged():
    from labeling_tool.ui.dialog_helpers import CONFIG_PATH
    from labeling_tool.session.workspace import DEFAULT_DATA_ROOT
    from annotation_tool import configs
    assert not app_paths.is_frozen()
    assert app_paths.app_home() == ROOT
    assert CONFIG_PATH == ROOT / "labeling_tool" / "config.json"
    assert DEFAULT_DATA_ROOT == ROOT / "labeling_tool" / "data"
    # few-shot weights stay relative to the working directory from source
    assert Path(configs.SAM3_CHECKPOINT) == Path("checkpoint/sam3.pt")
    assert Path(configs.SAM2_CHECKPOINT) == Path("checkpoint/sam2.1_hiera_base_plus.pt")
    assert configs.DEFAULT_DATASET_DIR == Path("dataset")


def test_frozen_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "LabelingTool.exe"))
    assert app_paths.is_frozen()
    assert app_paths.app_home() == tmp_path
    assert app_paths.writable_path(Path("ignored"), "config.json") == tmp_path / "config.json"


def test_frozen_module_constants_live_next_to_exe(tmp_path):
    # module-level constants are computed at import: check them in a fresh
    # interpreter that pretends to be the PyInstaller exe
    exe = tmp_path / "LabelingTool.exe"
    code = (
        "import sys; sys.frozen = True; sys.executable = %r\n"
        "from labeling_tool.ui import dialog_helpers as d\n"
        "from labeling_tool.session import workspace as w\n"
        "from annotation_tool import configs as c\n"
        "print(d.CONFIG_PATH, w.DEFAULT_DATA_ROOT, c.SAM3_CHECKPOINT,\n"
        "      c.SAM2_CHECKPOINT, c.CLASSES_FILE, c.DEFAULT_DATASET_DIR, sep='\\n')\n"
    ) % str(exe)
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split("\n")
    assert [Path(p) for p in out[:6]] == [
        tmp_path / "config.json",
        tmp_path / "data",
        tmp_path / "checkpoint" / "sam3.pt",
        tmp_path / "checkpoint" / "sam2.1_hiera_base_plus.pt",
        tmp_path / "classes.json",
        tmp_path / "dataset",
    ]


def test_upload_cli_reuses_config_path():
    from labeling_tool.scripts import upload_session_cli
    from labeling_tool.ui import dialog_helpers
    assert upload_session_cli.CONFIG_PATH is dialog_helpers.CONFIG_PATH


def test_importing_app_paths_does_not_pull_in_main_window():
    # labeling_tool.core.__init__ must lazily export MainWindow so that importing
    # annotation_tool.configs (which only needs labeling_tool.core.app_paths) does
    # not drag in PyQt5/cv2/the whole main window.
    code = (
        "import sys\n"
        "import annotation_tool.configs\n"
        "assert 'labeling_tool.core.window' not in sys.modules\n"
        "assert 'PyQt5' not in sys.modules\n"
        "print('ok')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "ok"


def test_core_main_window_still_importable():
    from labeling_tool.core import MainWindow
    from labeling_tool.core.window.main_window import MainWindow as CoreMainWindow
    assert MainWindow is CoreMainWindow


def test_backend_is_sam2_only_in_exe(tmp_path):
    from annotation_tool import configs
    assert configs.BACKEND == "sam3"          # source runs keep SAM3
    code = ("import sys; sys.frozen = True; sys.executable = %r\n"
            "from annotation_tool import configs; print(configs.BACKEND)\n"
            ) % str(tmp_path / "LabelingTool.exe")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "sam2"
