# annotation_tool/tests/conftest.py
import pytest

from annotation_tool import configs


@pytest.fixture(autouse=True)
def _isolated_classes_file(tmp_path, monkeypatch):
    """Never let tests read or write the user's global classes.json."""
    monkeypatch.setattr(configs, "CLASSES_FILE", tmp_path / "classes.json")


@pytest.fixture(autouse=True)
def _reset_i18n_current_language():
    """Reset the cached current-language singleton around every test.

    labeling_tool/tests/conftest.py has an equivalent fixture, but it only
    covers labeling_tool/tests/. Tests here (annotation_tool/tests/) that
    call i18n.set_language(...) would otherwise leak that language into
    whichever test runs next, so reset it before *and* after each test.
    """
    from labeling_tool.core import i18n
    i18n._current = None
    yield
    i18n._current = None
