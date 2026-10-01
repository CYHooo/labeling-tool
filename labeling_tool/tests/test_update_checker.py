"""GitHub Releases lookup: version compare, asset pick, checksum parse."""
import hashlib
import io
import json

import pytest

from labeling_tool.update import checker


def test_asset_name_and_version_parsing():
    assert (checker.full_asset_names("1.2.3", checker.WINDOWS)
            == ("LM_LabelingTool-Setup-v1.2.3.exe",))
    assert (checker.app_asset_name("1.2.3", "r3f8a1c92", checker.WINDOWS)
            == "LM_LabelingTool-App-v1.2.3-r3f8a1c92.exe")
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


def test_windows_asset_names_are_unchanged():
    # Every client ever shipped looks for exactly these names.
    assert (checker.full_asset_names("1.2.3", checker.WINDOWS)
            == ("LM_LabelingTool-Setup-v1.2.3.exe",))
    assert (checker.app_asset_name("1.2.3", "r3f8a1c92", checker.WINDOWS)
            == "LM_LabelingTool-App-v1.2.3-r3f8a1c92.exe")


def test_linux_asset_names():
    # The runtime deb's FILENAME carries no runtime id: a client taking a full
    # update knows the target version but not the new runtime id, so it could
    # not spell the name otherwise. The id lives in its Version field instead.
    assert (checker.full_asset_names("1.2.3", checker.LINUX)
            == ("lm-labeling-tool-runtime_1.2.3_amd64.deb",
                "lm-labeling-tool_1.2.3-RUNTIME_amd64.deb"))
    assert (checker.app_asset_name("1.2.3", "r3f8a1c92", checker.LINUX)
            == "lm-labeling-tool_1.2.3-r3f8a1c92_amd64.deb")


def test_windows_update_carries_exactly_one_asset():
    # The list is length 1 on Windows, always. This pins the refactor.
    info = checker.find_update("1.0.0", "full", opener=_opener(_release()),
                               platform=checker.WINDOWS)
    assert len(info.assets) == 1
    assert info.assets[0].name == "LM_LabelingTool-Setup-v1.0.1.exe"
    assert info.total_size == info.assets[0].size


def test_linux_full_update_carries_both_debs():
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info.kind == "full"
    assert [a.name for a in info.assets] == list(names[:2])
    assert info.total_size == sum(a.size for a in info.assets)


def test_linux_app_update_carries_one_deb():
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full", runtime="r3f8a1c92",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info.kind == "app"
    assert [a.name for a in info.assets] == ["lm-labeling-tool_1.0.1-r3f8a1c92_amd64.deb"]


def test_linux_full_update_is_refused_when_the_runtime_deb_is_missing():
    # spec 7.2.1: a release that lost its runtime deb must not produce a
    # half-installable update. Offering the app deb alone would hand the user
    # a download that dpkg then refuses.
    names = ("lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names)),
                               platform=checker.LINUX)
    assert info is None


def test_an_asset_without_a_published_checksum_is_never_offered():
    # Already true before this change; it must stay true per asset, not just
    # for the first one.
    names = ("lm-labeling-tool-runtime_1.0.1_amd64.deb",
             "lm-labeling-tool_1.0.1-rdeadbeef_amd64.deb", "SHA256SUMS.txt")
    info = checker.find_update("1.0.0", "full",
                               opener=_opener(_release(names=names),
                                              omit_sum=names[0]),
                               platform=checker.LINUX)
    assert info is None
