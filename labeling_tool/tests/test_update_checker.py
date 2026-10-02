"""GitHub Releases lookup: version compare, asset pick, checksum parse."""
import hashlib
import io
import json

import pytest

from labeling_tool.update import checker


def test_version_parsing():
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
    ("1.2.0", "1.2", False),                # trailing zeros normalized
    ("1.2", "1.2.0", False),                # both directions normalized
    ("1.2.1", "1.2", True),                 # but 1.2.1 > 1.2
])
def test_is_newer(latest, current, expected):
    assert checker.is_newer(latest, current) is expected


def test_parse_sha256sums():
    text = ("a" * 64 + "  LabelingTool-lite-Setup-v1.0.1.exe\n"
            + "b" * 64 + "  LabelingTool-full-Setup-v1.0.1.exe\n\n")
    sums = checker.parse_sha256sums(text)
    assert sums["LabelingTool-lite-Setup-v1.0.1.exe"] == "a" * 64
    assert len(sums) == 2


def _release(tag="v1.0.1", names=("LM_LabelingTool-Setup-v1.0.1.exe",
                                  "SHA256SUMS.txt")):
    return {"tag_name": tag, "body": "fixes things",
            "assets": [{"name": n, "browser_download_url": f"https://x/{n}", "size": 1234}
                       for n in names]}


def _opener(release, sums_text=None, omit_sum=None):
    """Fake urlopen: returns the release JSON, then the SHA256SUMS body.

    When `sums_text` is not given, a checksum line is synthesized for every
    asset in `release` except SHA256SUMS.txt itself and `omit_sum` (used to
    simulate a release that lost the published checksum for one asset)."""
    if sums_text is None:
        lines = []
        for asset in release["assets"]:
            name = asset["name"]
            if name in (checker.SUMS_ASSET, omit_sum):
                continue
            lines.append(f"{hashlib.sha256(name.encode()).hexdigest()}  {name}\n")
        sums_text = "".join(lines)

    def open_url(url, timeout=None):
        payload = sums_text if url.endswith("SHA256SUMS.txt") else json.dumps(release)
        return io.BytesIO(payload.encode())
    return open_url


def test_find_update_returns_matching_asset():
    sums = "c" * 64 + "  LM_LabelingTool-Setup-v1.0.1.exe\n"
    info = checker.find_update("1.0.0", "full", opener=_opener(_release(), sums),
                               platform=checker.WINDOWS)
    assert info.version == "1.0.1"
    assert info.assets[0].name == "LM_LabelingTool-Setup-v1.0.1.exe"
    assert info.assets[0].url == "https://x/LM_LabelingTool-Setup-v1.0.1.exe"
    assert info.assets[0].sha256 == "c" * 64
    assert info.assets[0].size == 1234
    assert info.total_size == 1234
    assert "fixes things" in info.notes


def test_find_update_none_when_same_version():
    assert checker.find_update("1.0.1", "full", opener=_opener(_release(), ""),
                               platform=checker.WINDOWS) is None


def test_find_update_none_when_no_installer_asset_present():
    """Variant no longer selects the asset -- only the version and, for the
    app package, the runtime id do. A release carrying neither installer
    offers nothing."""
    rel = _release(names=("SomethingElse-v1.0.1.zip", "SHA256SUMS.txt"))
    assert checker.find_update("1.0.0", "full", opener=_opener(rel, ""),
                               platform=checker.WINDOWS) is None


def test_find_update_requires_checksum():
    # an asset without an entry in SHA256SUMS.txt must not be offered
    assert checker.find_update("1.0.0", "full", opener=_opener(_release(), ""),
                               platform=checker.WINDOWS) is None


def test_find_update_propagates_network_errors():
    def boom(url, timeout=None):
        raise OSError("no network")
    with pytest.raises(OSError):
        checker.find_update("1.0.0", "lite", opener=boom)


def test_one_full_asset_per_platform():
    assert checker.full_asset_name("0.2.0", checker.WINDOWS) == "LM_LabelingTool-Setup-v0.2.0.exe"
    assert checker.full_asset_name("0.2.0", checker.LINUX) == "lm-labeling-tool_0.2.0_amd64.deb"


def test_update_zip_name_carries_runtime_and_platform():
    assert checker.update_asset_name("0.2.1", "r88c8d3f0", checker.WINDOWS) == "update-v0.2.1-r88c8d3f0-windows.zip"
    assert checker.update_asset_name("0.2.1", "ra493a449", checker.LINUX) == "update-v0.2.1-ra493a449-linux.zip"


def test_windows_update_carries_exactly_one_asset():
    # The list is length 1 on Windows, always. This pins the refactor.
    info = checker.find_update("1.0.0", "full", opener=_opener(_release()),
                               platform=checker.WINDOWS)
    assert len(info.assets) == 1
    assert info.assets[0].name == "LM_LabelingTool-Setup-v1.0.1.exe"
    assert info.total_size == info.assets[0].size



def _json_release(names, body=""):
    assets = [{"name": n, "browser_download_url": f"https://x/{n}", "size": 10} for n in names]
    return json.dumps({"tag_name": "v0.2.1", "body": body, "assets": assets})


def _sums_opener(release_json, sums):
    def opener(url, timeout=None):
        return io.BytesIO((sums if url.endswith("SHA256SUMS.txt") else release_json).encode())
    return opener


SUMS = "\n".join(f"{c * 64}  {n}" for c, n in [
    ("a", "LM_LabelingTool-Setup-v0.2.1.exe"),
    ("b", "update-v0.2.1-r88c8d3f0-windows.zip"),
    ("c", "lm-labeling-tool_0.2.1_amd64.deb"),
    ("d", "update-v0.2.1-ra493a449-linux.zip"),
])
ALL = ["LM_LabelingTool-Setup-v0.2.1.exe", "update-v0.2.1-r88c8d3f0-windows.zip",
       "lm-labeling-tool_0.2.1_amd64.deb", "update-v0.2.1-ra493a449-linux.zip", "SHA256SUMS.txt"]


def test_same_runtime_gets_the_zip():
    info = checker.find_update("0.2.0", "full", opener=_sums_opener(_json_release(ALL), SUMS),
                               runtime="r88c8d3f0", platform=checker.WINDOWS)
    assert info.kind == "app"
    assert [a.name for a in info.assets] == ["update-v0.2.1-r88c8d3f0-windows.zip"]
    assert info.assets[0].sha256 == "b" * 64


def test_changed_runtime_gets_the_full_package():
    info = checker.find_update("0.2.0", "full", opener=_sums_opener(_json_release(ALL), SUMS),
                               runtime="rdeadbeef", platform=checker.LINUX)
    assert info.kind == "full"
    assert [a.name for a in info.assets] == ["lm-labeling-tool_0.2.1_amd64.deb"]


def test_an_asset_without_a_checksum_is_never_offered():
    sums = "\n".join(l for l in SUMS.splitlines() if "windows.zip" not in l)
    info = checker.find_update("0.2.0", "full", opener=_sums_opener(_json_release(ALL), sums),
                               runtime="r88c8d3f0", platform=checker.WINDOWS)
    assert info.kind == "full"


def test_a_full_package_without_a_checksum_is_not_offered():
    sums = "\n".join(l for l in SUMS.splitlines() if ".deb" not in l)
    assert checker.find_update("0.2.0", "full", opener=_sums_opener(_json_release(ALL), sums),
                               runtime="rdeadbeef", platform=checker.LINUX) is None


def test_find_update_returns_only_the_notes_section():
    body = "| t |\n<!-- notes:start -->\n- fixed\n<!-- notes:end -->\ntrailer"
    info = checker.find_update("0.2.0", "full",
                               opener=_sums_opener(_json_release(ALL, body), SUMS),
                               runtime="r88c8d3f0", platform=checker.WINDOWS)
    assert info.notes == "- fixed"


def test_extract_notes_returns_only_the_marked_section():
    body = "| table |\n<!-- notes:start -->\n- 버그 수정\n- 속도 개선\n<!-- notes:end -->\n### 어떤 파일"
    assert checker.extract_notes(body) == "- 버그 수정\n- 속도 개선"


def test_extract_notes_without_markers_falls_back_to_eight_lines():
    body = "\n".join(f"line {i}" for i in range(20))
    assert checker.extract_notes(body) == "\n".join(f"line {i}" for i in range(8))
