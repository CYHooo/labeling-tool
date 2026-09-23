"""GitHub Releases lookup: version compare, asset pick, checksum parse."""
import io
import json

import pytest

from labeling_tool.update import checker


def test_asset_name_and_version_parsing():
    assert checker.asset_name_for("lite", "1.2.3") == "LabelingTool-lite-Setup-v1.2.3.exe"
    assert checker.parse_version("v1.2.3") == (1, 2, 3)
    assert checker.parse_version("1.0.10") == (1, 0, 10)
    assert checker.parse_version("nightly") is None


@pytest.mark.parametrize("latest,current,expected", [
    ("1.0.1", "1.0.0", True),
    ("1.0.10", "1.0.9", True),
    ("v1.0.0", "1.0.0", False),
    ("0.9.9", "1.0.0", False),
    ("1.1", "1.0.5", True),
    ("garbage", "1.0.0", False),
    ("1.0.1", "0.0.0-dev", False),          # dev builds never auto-update
])
def test_is_newer(latest, current, expected):
    assert checker.is_newer(latest, current) is expected


def test_parse_sha256sums():
    text = ("a" * 64 + "  LabelingTool-lite-Setup-v1.0.1.exe\n"
            + "b" * 64 + "  LabelingTool-full-Setup-v1.0.1.exe\n\n")
    sums = checker.parse_sha256sums(text)
    assert sums["LabelingTool-lite-Setup-v1.0.1.exe"] == "a" * 64
    assert len(sums) == 2


def _release(tag="v1.0.1", names=("LabelingTool-lite-Setup-v1.0.1.exe",
                                  "LabelingTool-full-Setup-v1.0.1.exe",
                                  "SHA256SUMS.txt")):
    return {"tag_name": tag, "body": "fixes things",
            "assets": [{"name": n, "browser_download_url": f"https://x/{n}", "size": 1234}
                       for n in names]}


def _opener(release, sums_text):
    """Fake urlopen: returns the release JSON, then the SHA256SUMS body."""
    def open_url(url, timeout=None):
        payload = sums_text if url.endswith("SHA256SUMS.txt") else json.dumps(release)
        return io.BytesIO(payload.encode())
    return open_url


def test_find_update_returns_matching_asset():
    sums = "c" * 64 + "  LabelingTool-lite-Setup-v1.0.1.exe\n"
    info = checker.find_update("1.0.0", "lite", opener=_opener(_release(), sums))
    assert info.version == "1.0.1"
    assert info.asset_name == "LabelingTool-lite-Setup-v1.0.1.exe"
    assert info.asset_url == "https://x/LabelingTool-lite-Setup-v1.0.1.exe"
    assert info.sha256 == "c" * 64
    assert info.size == 1234
    assert "fixes things" in info.notes


def test_find_update_none_when_same_version():
    assert checker.find_update("1.0.1", "lite", opener=_opener(_release(), "")) is None


def test_find_update_none_when_variant_asset_missing():
    rel = _release(names=("LabelingTool-full-Setup-v1.0.1.exe", "SHA256SUMS.txt"))
    assert checker.find_update("1.0.0", "lite", opener=_opener(rel, "")) is None


def test_find_update_requires_checksum():
    # an asset without an entry in SHA256SUMS.txt must not be offered
    assert checker.find_update("1.0.0", "lite", opener=_opener(_release(), "")) is None


def test_find_update_propagates_network_errors():
    def boom(url, timeout=None):
        raise OSError("no network")
    with pytest.raises(OSError):
        checker.find_update("1.0.0", "lite", opener=boom)
