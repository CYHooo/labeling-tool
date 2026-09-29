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
    declared = re.search(r"^AppId=\{\{([0-9A-Fa-f-]+)\}", iss, re.M)
    assert declared, "AppId not found in [Setup]"
    used = re.search(r"APP_GUID\s*=\s*'\{'\s*\+\s*'([0-9A-Fa-f-]+)'", _code_section(iss))
    assert used, "the [Code] guard does not define APP_GUID by literal parts"
    assert declared.group(1) == used.group(1), (
        f"AppId {declared.group(1)} != guard GUID {used.group(1)}")


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


def test_waits_go_through_the_shared_helper(workflow):
    helper = WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1"
    assert helper.is_file(), "packaging/ci/bounded.ps1 is missing"
    assert workflow.count(". packaging/ci/bounded.ps1") >= 2


def test_helper_caches_the_handle_before_waiting():
    """Without touching .Handle first, PowerShell leaves ExitCode null and
    a failed process reads as success."""
    text = (WORKFLOW.parent.parent.parent / "packaging" / "ci" / "bounded.ps1").read_text(encoding="utf-8")
    handle = text.index("$proc.Handle")
    wait = text.index("WaitForExit")
    assert handle < wait, "$proc.Handle must be read before WaitForExit"
