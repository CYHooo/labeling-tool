# annotation_tool/tests/test_dataset_io.py
import numpy as np
from PIL import Image
from annotation_tool.core import dataset_io


def test_list_images_reads_folder_directly_and_marks_mask(tmp_path):
    # images live directly in the chosen folder; masks in its masks/ subdir
    Image.new("RGB", (8, 6)).save(tmp_path / "a.jpg")
    Image.new("RGB", (8, 6)).save(tmp_path / "b.jpg")
    (tmp_path / "masks").mkdir()
    Image.new("L", (6, 8)).save(tmp_path / "masks" / "a_mask.png")
    items = dataset_io.list_images(tmp_path)
    names = {it.name: it.has_mask for it in items}
    assert names == {"a": True, "b": False}


def test_list_images_ignores_mask_subdir_contents(tmp_path):
    # a mask PNG sitting in masks/ must not be listed as an image to annotate
    Image.new("RGB", (8, 6)).save(tmp_path / "photo.jpg")
    (tmp_path / "masks").mkdir()
    Image.new("L", (6, 8)).save(tmp_path / "masks" / "photo_mask.png")
    (tmp_path / "verify_overlays").mkdir()
    Image.new("RGB", (8, 6)).save(tmp_path / "verify_overlays" / "photo_overlay.jpg")
    items = dataset_io.list_images(tmp_path)
    assert [it.name for it in items] == ["photo"]


def test_load_image_applies_exif_transpose(tmp_path):
    # 4x2 landscape image, Orientation=6 -> should become 2x4 portrait
    img = Image.new("RGB", (4, 2))
    exif = img.getexif()
    exif[274] = 6
    p = tmp_path / "rot.jpg"
    img.save(p, exif=exif)
    out = dataset_io.load_image_rgb(p)
    assert out.size == (2, 4)  # (W, H) transposed
    assert out.mode == "RGB"


def test_save_and_load_mask_roundtrip(tmp_path):
    (tmp_path / "masks").mkdir()
    arr = np.array([[0, 1], [2, 3]], dtype=np.uint8)
    p = tmp_path / "masks" / "x_mask.png"
    dataset_io.save_mask(p, arr)
    loaded = dataset_io.load_mask(p)
    assert loaded.dtype == np.uint8
    assert np.array_equal(loaded, arr)
    assert Image.open(p).mode == "L"


def test_save_overlay_writes_file(tmp_path):
    img = Image.new("RGB", (4, 4), (10, 10, 10))
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[0, 0] = 1
    p = tmp_path / "ov.jpg"
    dataset_io.save_overlay(p, img, mask)
    assert p.exists()
    assert Image.open(p).size == (4, 4)


def test_mask_path_for():
    assert dataset_io.mask_filename("CRACK_1") == "CRACK_1_mask.png"


def test_list_images_missing_dir_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        dataset_io.list_images(tmp_path / "does_not_exist")


def test_list_images_empty_folder_returns_empty(tmp_path):
    assert dataset_io.list_images(tmp_path) == []


def test_save_overlay_blends_class_color(tmp_path):
    img = Image.new("RGB", (4, 4), (10, 10, 10))
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[0, 0] = 1  # joint -> red (255,0,0)
    p = tmp_path / "ov.jpg"
    dataset_io.save_overlay(p, img, mask)
    result = np.array(Image.open(p))
    assert result[0, 0, 0] > 10   # red channel blended up
    assert result[0, 0, 1] < 60   # green channel stays near base (jpeg tolerance)
