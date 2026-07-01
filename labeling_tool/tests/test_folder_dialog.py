from pathlib import Path
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def test_dialog_exposes_dirs_and_count(tmp_path):
    from labeling_tool.ui.folder_dialog import FolderDialog
    img = tmp_path / "img"; msk = tmp_path / "msk"; img.mkdir(); msk.mkdir()
    (img / "foo.jpg").write_bytes(b"x"); (msk / "foo.png").write_bytes(b"x")
    (img / "bar.jpg").write_bytes(b"x")                 # unpaired
    d = FolderDialog()
    d.set_dirs(str(img), str(msk))                      # test hook (no native picker)
    assert d.image_dir == img and d.mask_dir == msk
    assert d.output_dir == img.parent / "Labeling"      # default output
    assert d.paired_count() == 1                         # only foo paired
