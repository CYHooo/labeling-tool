"""Static checks on the Linux local verification script.

Running it for real takes ~15 minutes and several GB of downloads, so the
suite checks the invariants that silently rot instead: the pinned base
image, the step list staying in sync with the PowerShell original, and the
smoke test refusing to paper over a missing dependency.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SH = REPO / "packaging" / "ci" / "local-build.sh"
PS1 = REPO / "packaging" / "ci" / "local-build.ps1"


def _declared_steps(text: str) -> list[str]:
    """Pull the step names out of the script's single explicit declaration,
    e.g. `known_steps=(tests build selftest layers deb smoke)`. Using one
    source of truth (rather than regex-scanning every `step ...` call) means
    a typo in the array is the only way to break this check."""
    match = re.search(r"known_steps=\(([^)]*)\)", text)
    assert match, "no known_steps=(...) array found in local-build.sh"
    return match.group(1).split()


def test_script_exists_and_is_executable():
    assert SH.is_file(), f"{SH} missing"
    assert SH.stat().st_mode & 0o111, "local-build.sh must be executable"


def test_pins_2204_not_latest():
    # glibc only works forwards: a 24.04 build cannot run on 22.04, and the
    # dev machine is 24.04. Building against :latest would silently produce
    # artifacts that exclude half the supported users.
    text = SH.read_text(encoding="utf-8")
    assert "ubuntu:22.04" in text
    assert "ubuntu:latest" not in text


def test_steps_match_the_powershell_original():
    # The two scripts verify the same pipeline on two platforms. A step that
    # exists on one side only is a verification gap nobody will notice.
    sh_steps = set(_declared_steps(SH.read_text(encoding="utf-8")))
    assert sh_steps == {"tests", "build", "selftest", "layers", "deb", "smoke"}


def test_smoke_step_forbids_apt_fix_broken():
    # dpkg -i must succeed on its own. Needing `apt-get install -f` means the
    # runtime package declares a library real users will not have either.
    text = SH.read_text(encoding="utf-8")
    assert "dpkg -i" in text
    assert "install -f" not in text


def test_runs_the_three_test_directories():
    # The repository's authoritative command; labeling_tool/tests alone
    # misses the top-level tests/ directory.
    text = SH.read_text(encoding="utf-8")
    assert "tests labeling_tool/tests annotation_tool/tests" in text


def test_refuses_to_run_outside_a_container():
    # The smoke step dpkg -i's two real packages into /opt. Running this
    # script directly on a developer's host would actually install them.
    text = SH.read_text(encoding="utf-8")
    assert "/.dockerenv" in text or "/proc/1/cgroup" in text


def test_matches_release_yml_dependency_install_order():
    # Verifying against a different environment than CI's is not a
    # verification at all. The three CI-specific environment variables below
    # exist because sam2's repo has symlinks; without them git on a
    # non-symlink-aware checkout writes 30-byte placeholders and the
    # resulting runtime id would never match a real build.
    text = SH.read_text(encoding="utf-8")
    assert "SAM2_BUILD_CUDA" in text
    assert "GIT_CONFIG_COUNT" in text
    assert "GIT_CONFIG_KEY_0" in text
    assert "GIT_CONFIG_VALUE_0" in text
    assert "build-lock-linux.txt" in text
    assert "pyinstaller-hooks-contrib" in text
    assert "torch==2.5.1" in text
    assert "2b90b9f5ceec907a1c18123530e92e794ad901a4" in text
