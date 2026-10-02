"""Picking the right package. The update zip's asset name carries the
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


APP = "update-v1.3.1-r3f8a1c92-windows.zip"
FULL = "LM_LabelingTool-Setup-v1.3.1.exe"
H = "a" * 64


def test_app_package_is_preferred_when_the_runtime_matches():
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums), platform=checker.WINDOWS)
    assert info.kind == "app"
    assert info.asset_name == APP
    assert info.assets[0].size == 31_000_000


def test_falls_back_to_full_when_the_runtime_changed():
    """torch got upgraded: the release carries an app package built against
    a different runtime, which must not be installed here."""
    other = "update-v1.3.1-rdeadbeef-windows.zip"
    rel = _release("v1.3.1", [(other, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {other}\n{H}  {FULL}\n"
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, sums), platform=checker.WINDOWS)
    assert info.kind == "full"
    assert info.asset_name == FULL


def test_falls_back_to_full_when_the_release_has_no_app_package():
    """The first layered release, and every release that changes the
    runtime, ships only the full installer."""
    rel = _release("v1.3.1", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"), platform=checker.WINDOWS)
    assert info.kind == "full"


def test_no_runtime_on_this_install_goes_straight_to_full():
    """A machine upgrading from v1.2.0 has no runtime id. It must not build
    an asset name containing 'None' and then match nothing."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    sums = f"{H}  {APP}\n{H}  {FULL}\n"
    info = checker.find_update("1.2.0", "full", runtime=None,
                               opener=_opener(rel, sums), platform=checker.WINDOWS)
    assert info.kind == "full"


def test_app_package_without_a_published_checksum_is_refused():
    """Never install an unverifiable download -- fall back to the full
    installer, which does have one."""
    rel = _release("v1.3.1", [(APP, 31_000_000), (FULL, 1_610_000_000),
                              ("SHA256SUMS.txt", 200)])
    info = checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"), platform=checker.WINDOWS)
    assert info.kind == "full"


def test_returns_none_when_neither_package_is_usable():
    rel = _release("v1.3.1", [("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, ""), platform=checker.WINDOWS) is None


def test_returns_none_when_the_release_has_no_checksum_file():
    """Without SHA256SUMS.txt nothing can be verified, so nothing is
    offered -- not even the full installer."""
    rel = _release("v1.3.1", [(FULL, 1_610_000_000)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, ""), platform=checker.WINDOWS) is None


def test_up_to_date_returns_none():
    rel = _release("v1.3.0", [(FULL, 1_610_000_000), ("SHA256SUMS.txt", 200)])
    assert checker.find_update("1.3.0", "full", runtime="r3f8a1c92",
                               opener=_opener(rel, f"{H}  {FULL}\n"),
                               platform=checker.WINDOWS) is None


def test_asset_name_templates_match_what_ci_builds():
    """These two strings are a contract with packaging/installer.iss's
    OutputBaseFilename and the update zip builder."""
    assert checker.update_asset_name("1.3.1", "r3f8a1c92", checker.WINDOWS) == APP
    assert checker.full_asset_name("1.3.1", checker.WINDOWS) == FULL


# ------------------------------------------------------------ the prompt
# An app update and a full reinstall cost the user very different things,
# so they must not read the same.

from labeling_tool.core import i18n  # noqa: E402
from labeling_tool.update import ui as update_ui  # noqa: E402


def _info(kind, size):
    return checker.UpdateInfo(
        version="1.3.1", variant="full",
        assets=(checker.Asset(name="x.exe", url="https://x/x.exe",
                              size=size, sha256=H),),
        notes="", kind=kind)


def test_app_update_text_states_the_version_but_no_download_size():
    """The zip is already downloaded when the prompt appears."""
    text = update_ui.prompt_text(_info("app", 31 * 1024 * 1024))
    assert "1.3.1" in text
    assert "31" not in text


def test_app_update_text_carries_no_reinstall_warning():
    """A 31 MB update must not scare the user with the reinstall notice."""
    text = update_ui.prompt_text(_info("app", 31 * 1024 * 1024))
    assert i18n.tr("update_full_warning") not in text


def test_full_update_text_warns_about_the_reinstall():
    text = update_ui.prompt_text(_info("full", 1536 * 1024 * 1024))
    assert "1.3.1" in text
    assert "1536" in text
    assert i18n.tr("update_full_warning") in text


def test_the_warning_names_the_runtime_layer_not_the_variant():
    """The lite/full variant is gone in v1.3.0; the reason a reinstall is
    needed is now that torch/CUDA changed."""
    warning = i18n.tr("update_full_warning")
    assert "torch" in warning or "CUDA" in warning
    assert "lite" not in warning
