"""The two build locks must not drift: drift means the platforms differ."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WIN_LOCK = REPO / "packaging" / "build-lock.txt"
LINUX_LOCK = REPO / "packaging" / "build-lock-linux.txt"

# Insert the packaging/ directory itself (not the repo root) and import the
# module by its bare name, same as test_reuse_full.py and test_layers.py.
# This never goes through the name "packaging" as a package, so it cannot
# collide with the pip-installed packaging library that pytest itself
# already imports and caches into sys.modules before this module runs.
sys.path.insert(0, str(REPO / "packaging"))
import lock_parity  # noqa: E402


def test_parse_lock_ignores_comments_and_blanks():
    text = "# a comment\n\nNumPy==1.26.4\ntorch==2.5.1+cu124\n"
    assert lock_parity.parse_lock(text) == {"numpy": "1.26.4", "torch": "2.5.1+cu124"}


def test_both_locks_exist():
    assert WIN_LOCK.is_file() and LINUX_LOCK.is_file()


def test_shared_packages_pin_identical_versions():
    # A version that differs between platforms is a functional difference
    # nobody declared. Either sync it, or declare it in PLATFORM_ONLY or
    # VERSION_MAY_DIFFER.
    problems = lock_parity.compare(WIN_LOCK.read_text(encoding="utf-8"),
                                   LINUX_LOCK.read_text(encoding="utf-8"))
    assert problems == [], "\n".join(problems)


def test_every_platform_only_entry_states_a_reason():
    for name, reason in lock_parity.PLATFORM_ONLY.items():
        assert name == name.lower(), f"{name} must be lowercased"
        assert len(reason.strip()) > 20, f"{name}: reason too thin to audit"


def test_every_version_may_differ_entry_states_a_reason():
    for name, reason in lock_parity.VERSION_MAY_DIFFER.items():
        assert name == name.lower(), f"{name} must be lowercased"
        assert len(reason.strip()) > 20, f"{name}: reason too thin to audit"


def test_a_version_mismatch_is_reported():
    problems = lock_parity.compare("numpy==1.26.4\n", "numpy==1.27.0\n")
    assert any("numpy" in p for p in problems)


def test_an_undeclared_one_sided_package_is_reported():
    problems = lock_parity.compare("onlywin==1.0\n", "")
    assert any("onlywin" in p for p in problems)


def test_a_declared_one_sided_package_is_accepted():
    name = next(iter(lock_parity.PLATFORM_ONLY))
    assert lock_parity.compare(f"{name}==1.0\n", "") == []


def test_a_declared_version_may_differ_package_is_accepted():
    name = next(iter(lock_parity.VERSION_MAY_DIFFER))
    assert lock_parity.compare(f"{name}==1.0\n", f"{name}==2.0\n") == []


def test_an_undeclared_version_mismatch_is_still_reported_even_if_name_looks_platform_specific():
    # A mismatch must be reported unless explicitly declared in
    # VERSION_MAY_DIFFER -- being in both locks with different versions is
    # never silently accepted just because the package name is unusual.
    problems = lock_parity.compare("totallyundeclaredpkg==1.0\n",
                                   "totallyundeclaredpkg==2.0\n")
    assert any("totallyundeclaredpkg" in p for p in problems)
