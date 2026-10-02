"""packaging/update_zip.py: the app-layer zip the release publishes."""
import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
import layers  # noqa: E402
import update_zip  # noqa: E402

from labeling_tool.update import patch  # noqa: E402


@pytest.mark.parametrize("platform", [layers.WINDOWS, layers.LINUX])
def test_client_and_packaging_agree_on_the_app_layer(platform):
    assert patch.APP_LAYER_PREFIXES(platform) == layers.app_layer_prefixes(platform)


def test_zip_carries_every_file_and_a_matching_manifest(tmp_path):
    src = tmp_path / "app-layer"
    (src / "_internal/labeling_tool").mkdir(parents=True)
    (src / "_internal/labeling_tool/a.pyc").write_bytes(b"a")
    (src / "LM_LabelingTool.exe").write_bytes(b"exe")
    (src / "build-info.json").write_text("{}")
    z = update_zip.build_update_zip(src, tmp_path / "out", "0.2.1", "r11111111", layers.WINDOWS)
    assert z.name == "update-v0.2.1-r11111111-windows.zip"
    m = patch.read_manifest(z)
    assert (m.version, m.runtime, m.platform) == ("0.2.1", "r11111111", "win32")
    assert m.files["_internal/labeling_tool/a.pyc"] == hashlib.sha256(b"a").hexdigest()
    with zipfile.ZipFile(z) as f:
        assert set(f.namelist()) == set(m.files) | {patch.MANIFEST_NAME}
        # No entry name ends with "/"
        assert not any(name.endswith("/") for name in f.namelist())


def test_a_non_app_layer_file_in_the_source_is_rejected(tmp_path):
    src = tmp_path / "app-layer"
    (src / "_internal/torch").mkdir(parents=True)
    (src / "_internal/torch/x.dll").write_bytes(b"x")
    with pytest.raises(ValueError):
        update_zip.build_update_zip(src, tmp_path / "out", "0.2.1", "r11111111", layers.WINDOWS)
