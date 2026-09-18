# annotation_tool/tests/test_smoke_ui.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer

from annotation_tool.segmenter.base import Segmenter
from annotation_tool.ui.canvas import ImageCanvas
from annotation_tool.ui.worker import InferenceWorker

_app = QApplication.instance() or QApplication([])


class _Dummy(Segmenter):
    def load(self): pass
    def set_image(self, pil_rgb): self._wh = pil_rgb.size
    def predict(self, points_xy, labels, box=None):
        w, h = self._wh
        m = np.zeros((h, w), dtype=bool)
        for (x, y) in points_xy:
            m[y, x] = True
        return m
    def reset(self): pass


def test_worker_emits_result():
    seg = _Dummy()
    seg.set_image(Image.new("RGB", (4, 3)))
    worker = InferenceWorker(seg)
    got = {}

    def on_result(mask):
        got["mask"] = mask
        loop.quit()

    worker.result.connect(on_result)
    loop = QEventLoop()
    worker.start()
    worker.request([(1, 2)], [1], None)
    QTimer.singleShot(3000, loop.quit)  # safety timeout
    loop.exec_()

    worker.stop()
    assert "mask" in got
    assert got["mask"][2, 1]


def test_canvas_set_image_and_prompt_collection():
    c = ImageCanvas()
    c.set_image(Image.new("RGB", (10, 8), (0, 0, 0)))
    assert c.image_size == (10, 8)  # (W, H)
    # simulate a positive point in image coords
    c.add_point_image_coords(3, 4, positive=True)
    pts, labels, box = c.current_prompt()
    assert pts == [(3, 4)]
    assert labels == [1]
    c.clear_prompt()
    pts, labels, box = c.current_prompt()
    assert pts == [] and labels == [] and box is None


def test_canvas_overlay_layers_render_no_crash():
    c = ImageCanvas()
    c.set_image(Image.new("RGB", (10, 8)))
    layer = np.zeros((8, 10), dtype=bool)
    layer[0:2, 0:2] = True
    c.set_committed_layers({1: layer, 2: np.zeros((8, 10), bool), 3: np.zeros((8, 10), bool)})
    c.set_candidate(layer)  # should not raise
    c.set_candidate(None)


def test_canvas_add_point_before_image_is_ignored():
    c = ImageCanvas()
    c.add_point_image_coords(5, 5, positive=True)  # no image yet -> ignored
    pts, labels, box = c.current_prompt()
    assert pts == [] and labels == []


# 追加到 annotation_tool/tests/test_smoke_ui.py
def test_main_window_constructs(monkeypatch, tmp_path):
    # images live directly in the chosen folder (no images/ subdir)
    Image.new("RGB", (10, 8)).save(tmp_path / "a.jpg")

    # avoid loading a real SAM backend
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *a, **k: _Dummy())

    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(tmp_path))
    assert w.list_widget.count() == 1
    w.load_index(0)
    assert w.canvas.image_size == (10, 8)
    w.set_active_class(1)
    assert w.active_class == 1
    w.close()


def test_main_window_clears_stale_candidate_on_reload(monkeypatch, tmp_path):
    Image.new("RGB", (10, 8)).save(tmp_path / "a.jpg")
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *a, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(tmp_path))
    w.load_index(0)
    w._candidate = np.zeros((8, 10), dtype=bool)  # simulate stale candidate
    w.load_index(0)                                # reload -> must clear it
    assert w._candidate is None
    w.set_active_class(2)
    assert w._candidate is None                    # class switch also clears
    w.close()


def test_main_window_load_dataset_switch(monkeypatch, tmp_path):
    ds_a = tmp_path / "A"; ds_a.mkdir()
    Image.new("RGB", (10, 8)).save(ds_a / "a.jpg")
    ds_b = tmp_path / "B"; ds_b.mkdir()
    Image.new("RGB", (12, 9)).save(ds_b / "b1.jpg")
    Image.new("RGB", (12, 9)).save(ds_b / "b2.jpg")
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(ds_a))
    assert w.list_widget.count() == 1
    w.load_dataset(ds_b, warn_if_empty=False)      # switch dataset folder
    assert w.list_widget.count() == 2
    assert w.dataset_dir == ds_b
    w.close()


def test_main_window_no_autoload_without_dataset(monkeypatch):
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow()  # no dataset_dir -> nothing loaded on launch
    assert w.list_widget.count() == 0
    assert w.current_image is None
    assert w.items == []
    w.close()


def test_main_window_brush_and_eraser_edit_layer(monkeypatch, tmp_path):
    Image.new("RGB", (10, 8)).save(tmp_path / "a.jpg")
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(tmp_path))
    w.load_index(0)
    w.set_active_class(2)          # concrete
    stroke = np.zeros((8, 10), dtype=bool)
    stroke[0:4, 0:4] = True
    w._on_stroke(stroke, is_erase=False)      # brush -> add
    assert w.state.layers[2][0, 0]
    w._on_stroke(stroke, is_erase=True)       # eraser -> remove
    assert not w.state.layers[2][0, 0]
    w.set_tool("brush")
    assert w.canvas._tool == "brush"
    w.set_tool("sam")
    w.close()


def test_main_window_invalid_folder_is_noop(monkeypatch, tmp_path):
    ds_a = tmp_path / "A"; ds_a.mkdir()
    Image.new("RGB", (10, 8)).save(ds_a / "a.jpg")
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(ds_a))
    w.load_dataset(tmp_path / "no_such_dir", warn_if_empty=False)  # nonexistent -> ignored
    assert w.list_widget.count() == 1              # unchanged
    assert w.dataset_dir == ds_a                   # unchanged
    w.close()


def _make_window(monkeypatch, tmp_path):
    ds = tmp_path / "ds"; ds.mkdir(parents=True)
    Image.new("RGB", (10, 8)).save(ds / "a.jpg")
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(ds))
    w.load_index(0)
    return w


def test_main_window_add_class_paint_save_and_persist(monkeypatch, tmp_path):
    from annotation_tool import configs
    from annotation_tool.core import dataset_io
    w = _make_window(monkeypatch, tmp_path)
    cid = w.add_class("crack", (1, 2, 3))
    assert w.active_class == cid
    assert w._class_group.button(cid) is not None
    stroke = np.zeros((8, 10), dtype=bool)
    stroke[0, :] = True
    w._on_stroke(stroke, is_erase=False)      # paint new class on loaded image
    assert w.state.layers[cid][0].all()
    w.save_current()
    saved = dataset_io.load_mask(dataset_io.mask_dir_of(w.dataset_dir) / "a_mask.png")
    assert (saved[0] == cid).all()
    assert configs.CLASSES_FILE.exists()      # persisted immediately
    w.close()

    w2 = _make_window(monkeypatch, tmp_path / "second")
    assert w2.registry.name(cid) == "crack"   # reloaded from global JSON
    w2.close()


def test_main_window_rename_recolor_and_priority(monkeypatch, tmp_path):
    w = _make_window(monkeypatch, tmp_path)
    w.set_active_class(2)
    w.rename_class(2, "slab")
    assert w._class_group.button(2).text().startswith("2: slab")
    w.set_class_color(2, (9, 9, 9))
    assert w.canvas._brush_color == (9, 9, 9)
    before = w.registry.export_order.index(2)
    w.move_active_priority(+1)
    assert w.registry.export_order.index(2) == before + 1
    w.close()


def test_main_window_corrupt_classes_file_uses_defaults(monkeypatch, tmp_path):
    from annotation_tool import configs
    configs.CLASSES_FILE.write_text("{broken")
    w = _make_window(monkeypatch, tmp_path)
    assert w.registry.class_ids == sorted(configs.CLASS_IDS)
    w.add_class("crack", (1, 2, 3))
    assert configs.CLASSES_FILE.read_text() == "{broken"  # never overwrite a broken file
    w.close()


def test_main_window_loads_and_saves_legacy_layout_masks(monkeypatch, tmp_path):
    from annotation_tool.core import dataset_io
    img_dir = tmp_path / "images"; img_dir.mkdir()
    mask_dir = tmp_path / "masks"; mask_dir.mkdir()
    Image.new("RGB", (10, 8)).save(img_dir / "a.jpg")
    Image.new("RGB", (10, 8)).save(img_dir / "b.jpg")
    existing = np.zeros((8, 10), dtype=np.uint8); existing[0, :] = 2
    dataset_io.save_mask(mask_dir / "a_mask.png", existing)
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    w = MainWindow(dataset_dir=str(img_dir))
    assert w.list_widget.item(0).text().startswith("✓")
    w.load_index(0)
    assert w.state.layers[2][0].all()          # existing annotation loaded
    w.load_index(1)
    w.state.add(1, np.ones((8, 10), dtype=bool))
    w.save_current()                            # new mask goes next to the old ones
    assert (mask_dir / "b_mask.png").exists()
    assert not (img_dir / "masks").exists()
    assert (tmp_path / "verify_overlays" / "b_overlay.jpg").exists()
    w.close()


def test_main_window_size_mismatch_mask_is_not_overwritten(monkeypatch, tmp_path):
    from annotation_tool.core import dataset_io
    Image.new("RGB", (10, 8)).save(tmp_path / "a.jpg")
    bad = np.full((5, 5), 1, dtype=np.uint8)
    dataset_io.save_mask(tmp_path / "masks" / "a_mask.png", bad)
    from annotation_tool.segmenter import base as base_mod
    monkeypatch.setattr(base_mod, "build_segmenter", lambda *args, **k: _Dummy())
    from annotation_tool.ui.main_window import MainWindow
    from annotation_tool.ui import main_window as mw_mod
    warned = []
    monkeypatch.setattr(mw_mod.QMessageBox, "warning", lambda *a, **k: warned.append(a))
    w = MainWindow(dataset_dir=str(tmp_path))  # must not crash on load
    w.load_index(0)
    assert w.state is not None
    w.save_current()                             # must refuse to overwrite
    assert warned
    assert dataset_io.load_mask(tmp_path / "masks" / "a_mask.png").shape == (5, 5)
    w.close()
