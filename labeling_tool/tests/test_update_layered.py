"""Picking the right installer. The app package's asset name carries the
runtime id, so the client decides by name alone -- no extra metadata file."""

import json

from labeling_tool.update import checker


def _release(tag, assets):
    return json.dumps({"tag_name": tag, "body": "",
                       "assets": [{"name": n, "browser_download_url": f"https://x/{n}",
                                   "size": s} for n, s in assets]})


def _opener(release_json, sums_text):
    class _Resp:
        def __init__(self, text):
            self._t = text

        def read(self):
            return self._t.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open(url, timeout=None):
        return _Resp(sums_text if url.endswith("SHA256SUMS.txt") else release_json)
    return _open


APP = "LM_LabelingTool-App-v1.3.1-r3f8a1c92.exe"
FULL = "LM_LabelingTool-Setup-v1.3.1.exe"
H = "a" * 64


def test_app_package_is_preferred_when_the_runtime_matches():
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums))
    assert info.kind == "app"
    assert info.asset_name == APP
    assert info.size == 31_000_000


def test_falls_back_to_full_when_the_runtime_changed():
    """torch got upgraded: the release carries an app package built against
    a different runtime, which must not be installed here."""
    other = "LM_LabelingTool-App-v1.3.1-rdeadbeef.exe"
    rel = _release("v1.3.1", [(other, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {other}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums))
    assert info.kind == "full"
    assert info.asset_name == FULL


def test_falls_back_to_full_when_the_release_has_no_app_package():
    """The first layered release, and every release that changes the
    runtime, ships only the full installer."""
    rel = _release("v1.3.1", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"))
    assert info.kind == "full"


def test_no_runtime_on_this_install_goes_straight_to_full():
    """A machine upgrading from v1.2.0 has no runtime id. It must not build
    an asset name containing 'None' and then match nothing."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.2.0", "full", runtime=None,
                               opener=_opener(rel, sums))
    assert info.kind == "full"


def test_app_package_without_a_published_checksum_is_refused():
    """Never install an unverifiable download -- fall back to the full
    installer, which does have one."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"))
    assert info.kind == "full"


def test_returns_none_when_neither_package_is_usable():
    rel = _release("v1.3.1", [("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, "")) is None


def test_returns_none_when_the_release_has_no_checksum_file():
    """Without SHA256SUMS.txt nothing can be verified, so nothing is
    offered -- not even the full installer."""
    rel = _release("v1.3.1", [(FULL, 1_610_000_000)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, "")) is None


def test_up_to_date_returns_none():
    rel = _release("v1.3.0", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n")) is None


def test_asset_name_templates_match_what_ci_builds():
    """These two strings are a contract with packaging/installer.iss's
    OutputBaseFilename. CI asserts the same thing from the other side."""
    assert checker.app_asset_name("1.3.1", "r3f8a1c92") == APP
    assert checker.full_asset_name("1.3.1") == FULL
