"""Static checks on packaging/installer.iss.

Inno Setup only runs on Windows, so these are the only automated guard we
have over the installer script. Both checks come from real failures:
CI run 36518723697 hung for 96 minutes because a [Code] MsgBox blocked a
silent install, and the registry key it read was misspelled so the guard
never found the install it was meant to protect.
"""

import re
from pathlib import Path

import pytest

ISS = Path(__file__).resolve().parents[2] / "packaging" / "installer.iss"


@pytest.fixture(scope="module")
def iss() -> str:
    return ISS.read_text(encoding="utf-8")


def _section(text: str, name: str) -> str:
    """The body of a section, located by a line that IS the header -- the
    file's own comments mention [Files] and [Code] in prose."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, l in enumerate(lines) if l.strip() == name]
    assert starts, f"no {name} section header"
    i = starts[0] + 1
    out = []
    while i < len(lines) and not (lines[i].startswith("[") and lines[i].strip().endswith("]")):
        out.append(lines[i])
        i += 1
    return "".join(out)


def _code_section(text: str) -> str:
    return _section(text, "[Code]")


def test_code_section_never_calls_blocking_msgbox(iss):
    """/SUPPRESSMSGBOXES does NOT suppress a MsgBox called from [Code]. A
    silent install -- which is what the in-app updater runs -- would wait
    forever for a click nobody makes. SuppressibleMsgBox returns the
    default instead."""
    calls = re.findall(r"(?<![A-Za-z])MsgBox\s*\(", _code_section(iss))
    assert not calls, (
        f"{len(calls)} blocking MsgBox call(s) in [Code]; use "
        "SuppressibleMsgBox so /SUPPRESSMSGBOXES cannot hang the install")


def test_guard_reads_the_same_appid_the_setup_section_declares(iss):
    """The guard looks the install up under
    HKCU\\...\\Uninstall\\<AppId>_is1. If that GUID drifts from [Setup]'s
    AppId the lookup silently returns nothing, the guard finds no install
    and refuses (or, before the fix, let everything through)."""
    # Two pairs, in the same order in both places: production first, then
    # the /DMyTestInstall id used by local smoke tests.
    declared = re.findall(r"^AppId=\{\{([0-9A-Fa-f-]+)\}", iss, re.M)
    used = re.findall(r"APP_GUID\s*=\s*'\{'\s*\+\s*'([0-9A-Fa-f-]+)'", _code_section(iss))
    assert len(declared) == 2, f"expected production + test AppId, got {declared}"
    assert used == declared, f"AppIds {declared} != guard GUIDs {used}"
    assert declared[0] == "9E1E0C6B-6E0F-4E8E-9E2F-0F7B5C1A0F02", (
        "the production AppId changed: every existing install would stop "
        "upgrading in place")


def test_test_install_can_never_touch_the_real_install(iss):
    """A local smoke test installs and UNINSTALLS. Under the production
    AppId or Start menu name that takes the workstation's real copy with it."""
    setup = _section(iss, "[Setup]")
    prod = setup[setup.index("#ifndef MyTestInstall"):setup.index("#else")]
    test = setup[setup.index("#else"):setup.index("#endif")]
    assert "9E1E0C6B" in prod and "9E1E0C6B" not in test
    name = re.search(r'#define MyAppName "([^"]+)"', test).group(1)
    assert name != "LM_LabelingTool"
    assert "DefaultGroupName={#MyAppName}" in setup


def test_app_layer_installdelete_never_clears_internal_wholesale(iss):
    """The app package does not ship the ~1.4 GB runtime layer; clearing
    _internal would leave the program unable to start."""
    block = _section(iss, "[InstallDelete]")
    app_part = block[block.index('#if MyLayer == "app"'):block.index("#else")]
    assert '"{app}\\_internal"' not in app_part
    assert "_internal\\labeling_tool" in app_part
    assert "_internal\\annotation_tool" in app_part


# ------------------------------------------------------------- CI workflow
# Every wait in the Windows build must be bounded. Two runs were lost to
# unbounded waits: one hung 96 minutes on a modal dialog, one left a tag
# build with nothing after 47 minutes. Both surfaced only as "the hosted
# runner lost communication with the server".

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "build-windows.yml"


@pytest.fixture(scope="module")
def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_no_unbounded_process_wait_in_the_workflow(workflow):
    """`Start-Process -Wait` has no timeout: a hung child holds the job
    until GitHub kills it, and the log is usually lost with it."""
    assert "-Wait -PassThru" not in workflow
    assert re.search(r"Start-Process[^\n]*\s-Wait(\s|$)", workflow) is None


LOCAL_BUILD = WORKFLOW.parent.parent.parent / "packaging" / "ci" / "local-build.ps1"


@pytest.fixture(scope="module", params=["workflow", "local-build"])
def powershell_source(request) -> str:
    """Both places that drive PowerShell against ISCC, pip and the exe."""
    path = WORKFLOW if request.param == "workflow" else LOCAL_BUILD
    return path.read_text(encoding="utf-8")


def test_waits_go_through_the_shared_helper(workflow):
    helper = WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1"
    assert helper.is_file(), "packaging/ci/bounded.ps1 is missing"
    assert ". packaging/ci/bounded.ps1" in workflow
    assert "bounded.ps1" in LOCAL_BUILD.read_text(encoding="utf-8")


def test_ci_only_releases(workflow):
    """Verification runs locally (packaging/ci/local-build.ps1); a CI round
    is too slow to iterate on. CI runs for a tag, or by hand as a dry run."""
    on = workflow[workflow.index("\non:"):workflow.index("\npermissions:")]
    assert "pull_request" not in on
    assert "tags:" in on
    assert "pytest" not in workflow


def test_ci_builds_in_a_clean_pinned_environment(workflow):
    """The runner's own Python carries preinstalled packages that follow the
    runner image; bundled, they move the runtime id between identical
    builds. CI builds in a fresh venv, with everything pinned by the lock."""
    assert "python -m venv" in workflow
    assert "packaging/build-lock.txt" in workflow
    lock = (WORKFLOW.parent.parent.parent / "packaging" / "build-lock.txt").read_text(encoding="utf-8")
    pins = [l for l in lock.splitlines() if l and not l.startswith("#")]
    assert pins and all("==" in l for l in pins), "every lock line must pin an exact version"
    for must in ("torch==", "numpy==", "filelock==", "PyQt5=="):
        assert any(l.startswith(must) for l in pins), f"{must} is not pinned"


def test_a_reused_full_installer_is_verified_before_it_is_republished(workflow):
    """A code-only release ships the previous full installer again under a
    fresh checksum line; it has to match the checksum it was first published
    with, or a corrupted download would be blessed."""
    step = workflow[workflow.index("Reuse the previous full installer"):workflow.index("- name: Build installers")]
    assert "reuse_full.py plan" in step
    assert "reuse_full.py verify" in step
    assert step.index("reuse_full.py verify") < step.index("LT_REUSE_FULL=")
    build = workflow[workflow.index("- name: Build installers"):workflow.index("- name: Assert the asset names")]
    assert 'Copy-Item $env:LT_REUSE_FULL "out\\LM_LabelingTool-Setup-v$ver.exe"' in build


def test_no_string_interpolation_runs_into_a_colon(powershell_source):
    """"$prevTag: x" parses as a scope-qualified variable, like $env:X, and
    fails. Use ${name}: instead. Only $env: is a real scope here."""
    for line in powershell_source.splitlines():
        if line.strip().startswith("#"):
            continue
        for m in re.finditer(r"\$([A-Za-z_]\w*):", line):
            assert m.group(1).lower() in ("env", "script", "global", "using"), (
                f"${m.group(1)}: reads as a scope-qualified name: {line.strip()}")


def test_ci_resolves_git_symlinks_when_installing_sam2(workflow):
    """sam2's repo holds symlinked yaml files. A git with core.symlinks=false
    writes placeholders instead, and local and CI runtime ids part ways
    (run 36682820480: r1970c21b locally vs r88c8d3f0)."""
    assert "GIT_CONFIG_KEY_0: core.symlinks" in workflow
    assert 'GIT_CONFIG_VALUE_0: "true"' in workflow


def test_helper_caches_the_handle_before_waiting():
    """Without touching .Handle first, PowerShell leaves ExitCode null and
    a failed process reads as success."""
    text = (WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1").read_text(encoding="utf-8")
    handle = text.index("$proc.Handle")
    wait = text.index("WaitForExit")
    assert handle < wait, "$proc.Handle must be read before WaitForExit"


def test_release_builds_keep_maximum_compression(iss):
    """Fast compression is a CI-time shortcut: it cuts ~10 minutes off a
    verification run. What users download must still be squeezed as hard as
    possible, so the fast path has to be opt-in via MyFast and the default
    must remain lzma2/max."""
    block = iss[iss.index("#ifdef MyFast"):iss.index("[Languages]")]
    fast, full = block.index("lzma2/fast"), block.index("lzma2/max")
    assert block.index("#else") < full, "lzma2/max must be the #else default"
    assert fast < block.index("#else"), "lzma2/fast must sit under #ifdef MyFast"


def test_release_compression_is_multithreaded(iss):
    """Single-threaded lzma2/max was ~11 of ~18 minutes of a release; four
    block threads cut it to about a third for 1% more size."""
    block = iss[iss.index("#ifdef MyFast"):iss.index("[Languages]")]
    release = block[block.index("#else"):block.index("#endif")]
    assert "LZMANumBlockThreads=4" in release


def test_the_size_ceiling_only_binds_on_published_builds(workflow):
    """A fast-compressed verification build is legitimately larger than a
    release one; the 2 GiB release ceiling must not fail it."""
    assert "GITHUB_REF_TYPE -eq 'tag' -and $full.Length -ge 1.9GB" in workflow


def test_every_iscc_invocation_honours_the_compression_mode(workflow):
    """CI compiles two packages, full and app, from one common argument list
    that carries /DMyFast=1 on a dry run. (The deliberately mismatched
    package is compiled locally, for the smoke test.)"""
    assert workflow.count("/DMyFast=1") == 1, "only via the common list"
    assert workflow.count("& $iscc @") == 2, "both invocations splat a full array"


def test_local_installers_never_carry_the_production_appid():
    """The local smoke test installs and uninstalls on a workstation that may
    have the app installed for real."""
    text = LOCAL_BUILD.read_text(encoding="utf-8")
    assert '"/DMyTestInstall=1"' in text
    assert text.count("& $iscc @") == 3
    assert "9E1E0C6B" not in text, "the local script must not name the production AppId"


def test_scripts_never_assign_powershell_automatic_variables(powershell_source):
    """$args is the function-arguments automatic variable; assigning to it
    is undefined behaviour and has already dropped arguments here once --
    including /VERYSILENT, which turned a silent install into a wizard that
    hung for 96 minutes."""
    reserved = ("args", "input", "error", "host", "home", "pwd", "matches")
    for name in reserved:
        assert re.search(rf"^\s*\${name}\s*=", powershell_source, re.M | re.I) is None, (
            f"${name} is a PowerShell automatic variable; pick another name")


def test_splats_are_always_the_whole_argument_list(powershell_source):
    """`& $iscc /A @extra script.iss` does NOT expand @extra -- splatting
    only works as the entire rest of the command. The literal "@extra" then
    reaches ISCC as a second script filename (run 36672426334), or pip as a
    requirement. A splat must be the last thing on its line."""
    for line in powershell_source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # comments show the broken form on purpose
        for m in re.finditer(r"(?<=\s)@[A-Za-z_]\w*", stripped):
            assert not stripped[m.end():].strip(), (
                f"splat {m.group()} is not the whole argument list: {stripped}")
