"""The two build locks must not drift: drift means the platforms differ."""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WIN_LOCK = REPO / "packaging" / "build-lock.txt"
LINUX_LOCK = REPO / "packaging" / "build-lock-linux.txt"

# Load packaging/lock_parity.py by file path rather than
# `from packaging import lock_parity`: pytest itself already imports and
# caches the real, pip-installed `packaging` library (the version-parsing
# one) as sys.modules["packaging"] before this test module runs, so a
# dotted import would silently resolve to that library's namespace instead
# of our local packaging/ directory and fail to find lock_parity.
_spec = importlib.util.spec_from_file_location(
    "lock_parity", REPO / "packaging" / "lock_parity.py")
lock_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lock_parity)


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
