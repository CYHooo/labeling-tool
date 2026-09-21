from pathlib import Path
from PyQt5.QtWidgets import QApplication

from labeling_tool.core.window.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


def _win():
    return MainWindow()


def test_default_save_mask_path(tmp_path):
    w = _win(); w.output_dir = tmp_path
    assert w._save_mask_path("foo.jpg") == tmp_path / "foo_mask.png"


def test_default_build_image_list(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "note.txt").write_bytes(b"x")
    w = _win(); w.origin_dir = tmp_path
    assert w._build_image_list() == ["a.jpg", "b.png"]


def test_default_display_mask_path_finds_labeling(tmp_path):
    lab = tmp_path / "Labeling"; det = tmp_path / "Detected"
    lab.mkdir(); det.mkdir()
    (lab / "foo_mask.png").write_bytes(b"x")
    w = _win(); w.output_dir = lab; w.detected_dir = det
    path, source = w._display_mask_path("foo.jpg")
    assert path == str(lab / "foo_mask.png")
