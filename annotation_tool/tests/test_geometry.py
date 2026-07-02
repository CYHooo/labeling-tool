# annotation_tool/tests/test_geometry.py
import pytest
from annotation_tool.ui.geometry import clamp_point, scene_to_image, image_to_scene


def test_scene_to_image_identity_when_same_scale():
    assert scene_to_image(10.0, 20.0, scale=1.0, offset=(0.0, 0.0)) == (10, 20)


def test_scene_to_image_with_scale_and_offset():
    assert scene_to_image(25.0, 15.0, scale=2.0, offset=(5.0, 5.0)) == (10, 5)


def test_image_to_scene_inverse():
    sx, sy = image_to_scene(10, 5, scale=2.0, offset=(5.0, 5.0))
    assert (sx, sy) == (25.0, 15.0)


def test_clamp_point_inside():
    assert clamp_point(3, 4, 8, 6) == (3, 4)


def test_clamp_point_outside():
    assert clamp_point(-1, 100, 8, 6) == (0, 5)
