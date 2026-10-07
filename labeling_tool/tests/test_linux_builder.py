"""The Linux app is built in one pinned image (packaging/linux/builder.Dockerfile)
by one script (packaging/ci/linux-build.sh), in CI and locally alike.

PyInstaller bundles the build machine's system libraries into the runtime
layer, so an unpinned build environment moves the runtime id on its own:
libssl.so.3 from a GitHub runner image update did exactly that between
v0.2.2 and v0.2.3 and sent every Linux user a 1.7 GB full update."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "packaging" / "linux" / "builder.Dockerfile"
BUILD_SH = REPO / "packaging" / "ci" / "linux-build.sh"
LOCAL_SH = REPO / "packaging" / "ci" / "local-build.sh"
WORKFLOW = REPO / ".github" / "workflows" / "release.yml"


def _linux_job() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("\n  build-linux:\n")
    end = text.index("\n  release:\n", start)
    return text[start:end]


def test_the_image_pins_base_apt_and_python():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM ubuntu:22\.04@sha256:[0-9a-f]{64}$", text, re.M), "base image not pinned by digest"
    assert re.search(r"^ARG SNAPSHOT=\d{8}T\d{6}Z$", text, re.M), "apt snapshot date not pinned"
    for pocket in ("jammy", "jammy-updates", "jammy-security"):
        assert f"snapshot.ubuntu.com/ubuntu/${{SNAPSHOT}} {pocket} " in text
    assert re.search(r"^ARG PYTHON_SHA256=[0-9a-f]{64}$", text, re.M)
    assert "sha256sum -c" in text
    assert "python-3.12.10-linux-22.04-x64.tar.gz" in text


def test_the_image_installs_the_debs_libraries_from_deb_py():
    """Qt's xcb plugin chain must be present at build time, or PyInstaller
    ships a bundle whose platform plugin cannot start; the list lives in
    deb.py so the image and the deb's Depends cannot drift apart."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "deb.RUNTIME_DEPENDS + deb.BUNDLED_LIBS" in text
    assert "apt-get satisfy" in text


def test_ci_builds_the_linux_app_only_in_the_pinned_image():
    job = _linux_job()
    assert "file: packaging/linux/builder.Dockerfile" in job
    assert "lt-linux-builder bash packaging/ci/linux-build.sh" in job
    for runner_build in ("pyinstaller", "pip install", "python -m venv"):
        assert runner_build not in job, f"{runner_build!r} runs on the runner again"
    assert 'echo "LT_RUNTIME=$rt" >> "$GITHUB_ENV"' in job


def test_the_build_script_keeps_the_pins_that_hold_the_runtime_id():
    text = BUILD_SH.read_text(encoding="utf-8")
    assert BUILD_SH.stat().st_mode & 0o111
    for pin in ("GIT_CONFIG_KEY_0=core.symlinks", "SAM2_BUILD_CUDA=0", "build-lock-linux.txt",
                "pyinstaller==6.22.3", "pyinstaller-hooks-contrib==2026.7", "torch==2.5.1",
                "2b90b9f5ceec907a1c18123530e92e794ad901a4", "--selftest=full",
                "layers.py runtime-id", "layers.py stage", "diag/runtime-id.txt"):
        assert pin in text, pin


def test_local_build_delegates_to_the_build_script():
    """One copy of the install/build steps: local-build.sh calls the script
    CI runs instead of keeping its own, so its runtime id predicts CI's."""
    text = LOCAL_SH.read_text(encoding="utf-8")
    assert "bash packaging/ci/linux-build.sh" in text
    assert "LT_INSTALL_ONLY=1" in text
    assert "pip install" not in text and "-m PyInstaller" not in text and "pyinstaller --" not in text


def test_every_pip_install_uses_the_lock():
    lines = [l for l in BUILD_SH.read_text(encoding="utf-8").splitlines() if "pip install" in l]
    assert len(lines) == 3
    assert all('"${lock[@]}"' in l for l in lines)


def test_apt_never_touches_the_live_archive():
    """A live-archive install before the sources switch could pull a newer
    libssl3 than the snapshot's and move the runtime id on an image rebuild."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    switch = text.index("> /etc/apt/sources.list")
    assert text.find("apt-get") > switch, "apt-get runs before the snapshot sources are in place"
    assert "archive.ubuntu.com" not in text


def test_local_build_runs_only_in_the_pinned_image():
    text = LOCAL_SH.read_text(encoding="utf-8")
    assert "lt-linux-builder bash packaging/ci/local-build.sh" in text
    assert "/opt/hostedtoolcache/Python/3.12.10/x64/bin/python3.12" in text
    assert "deadsnakes" not in text
