# annotation_tool/tests/conftest.py
import pytest

from annotation_tool import configs


@pytest.fixture(autouse=True)
def _isolated_classes_file(tmp_path, monkeypatch):
    """Never let tests read or write the user's global classes.json."""
    monkeypatch.setattr(configs, "CLASSES_FILE", tmp_path / "classes.json")
