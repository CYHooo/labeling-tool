#!/usr/bin/env bash
# Verify a Linux release locally, the way local-build.ps1 already does for
# Windows. RELEASING.md's premise is that checks run locally and CI only
# builds and publishes, because a CI round took 18-25 minutes and every
# failure cost another one. Leaving the Linux smoke test in CI only would
# put this half of the release back on that tag-and-wait loop.
#
# Must run in a container: the dev machine is Ubuntu 24.04 (glibc 2.39),
# the release target is 22.04 (glibc 2.35), and glibc only works forwards
# -- a host build would not represent what ships. The script refuses to run
# outside a container (see the check below) because the "smoke" step does a
# real `dpkg -i` into /opt.
#
# Usage, from the repository root (needs the host's docker socket so the
# "smoke" step's sufficiency/guard and 24.04 cross-validation checks can
# each start a fresh sibling container -- NOT nested docker-in-docker, a
# sibling started via the HOST's own dockerd through the mounted socket;
# --tmpfs /repo/.venv shadows a host dev venv if one exists -- see the
# check below for why that matters):
#
#   docker run --rm -v "$PWD:/repo" -v /var/run/docker.sock:/var/run/docker.sock \
#     -e HOST_REPO_ROOT="$PWD" --tmpfs /repo/.venv -w /repo \
#     ubuntu:22.04 bash packaging/ci/local-build.sh
#
#   ... bash packaging/ci/local-build.sh --steps build,layers   # subset
#   ... bash packaging/ci/local-build.sh --version 1.4.0         # tag dry run
#
# HOST_REPO_ROOT matters because sibling containers are started through the
# HOST's dockerd (the socket above is just a pipe to it): a `-v SRC:DST`
# passed from inside this container is resolved by that daemon against the
# HOST's filesystem, not this container's. Passing this container's own
# path (e.g. /repo/out) would ask the host for a path that does not exist
# there, and docker silently creates an empty directory instead of failing
# -- the sibling container then sees an empty /out and every `dpkg -i`
# inside it fails with a confusing "no such file", not an obviously wrong
# path. Confirmed by hitting exactly that failure before this comment and
# the HOST_REPO_ROOT plumbing below existed.
#
# The dependency-install order below is copied from
# .github/workflows/release.yml's build-linux job, field for field,
# including the three sam2-symlink environment variables -- a local
# environment that diverges from CI's is not a verification of CI's build.
#
# Every external call that can hang -- a GUI process, dpkg, a container
# download -- goes through bounded() below. This project has already been
# burned by an unbounded wait: a stray MsgBox in installer.iss once hung a
# Windows CI job for 96 minutes before anyone noticed (see local-build.ps1 /
# bounded.ps1). A verification script that can hang forever is worse than
# no verification script, because the failure mode is silence, not an error.
#
# Why "smoke" needs TWO separate fresh containers, not one bare environment:
# this script's own outer container (the one running tests/build/selftest)
# needs Qt's xcb platform to actually start, which needs real X11/GL
# libraries -- without them Qt does not fail cleanly, it HANGS (confirmed:
# QApplication() under xvfb-run with only xvfb's own transitive deps
# installed blocks forever; installing packaging/deb.py's RUNTIME_DEPENDS
# equivalents fixes it immediately). So the outer container is deliberately
# NOT minimal. That means it can no longer serve as the "does dpkg -i
# succeed on a machine that only has what RUNTIME_DEPENDS lists filled in
# the Depends line, not pre-installed" question -- asking it in the outer
# container would be the exact tautology the brief warns about (install the
# dependency, then verify the dependency is satisfied). So the sufficiency
# check and the mismatched-deb guard run in a FRESH ubuntu:22.04 sibling
# container that only ever gets dpkg-dev/xvfb/build-essential, mirroring
# release.yml's build-linux job's own (GH-runner-hosted) minimal baseline.
# The existing 24.04 "usability" cross-check already followed this pattern;
# it now has a sibling for the same reason, not a new one.

set -euo pipefail

known_steps=(tests build selftest layers deb smoke)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DIST="dist/LM_LabelingTool"
VENV=""
RUNTIME_ID=""

steps=("${known_steps[@]}")
# Debian's Version field must start with a digit (dpkg-deb enforces this
# at build time) -- a bare "dev-local" is rejected outright. Mirrors
# release.yml's non-tag dry-run version shape (dev-<sha>) but digit-first.
version="0.0.0-dev-local"

usage() {
    echo "usage: local-build.sh [--steps tests,build,selftest,layers,deb,smoke] [--version VER]" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --steps)
            [ $# -ge 2 ] || usage
            IFS=',' read -r -a steps <<< "$2"
            shift 2
            ;;
        --version)
            [ $# -ge 2 ] || usage
            version="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

for s in "${steps[@]}"; do
    known=0
    for k in "${known_steps[@]}"; do
        [ "$s" = "$k" ] && known=1 && break
    done
    if [ "$known" -ne 1 ]; then
        echo "unknown step: $s; known: ${known_steps[*]}" >&2
        exit 2
    fi
done

want_step() {
    for s in "${steps[@]}"; do
        [ "$s" = "$1" ] && return 0
    done
    return 1
}

# Run a command with a hard wall-clock ceiling. A timeout is reported the
# same way a real failure is (non-zero exit, `set -e` stops the script) --
# the caller never has to special-case it. SIGKILL ten seconds after SIGTERM
# in case the process ignores the first signal (an X server has, before).
bounded() {
    local secs="$1" desc="$2"
    shift 2
    # `code=$?` must be set via `||`, not inside `if ! cmd; then`: the
    # latter's `$?` reflects the NEGATED pipeline's own status (always 0
    # inside the then-branch), not the wrapped command's real exit code --
    # that bug silently turned every bounded() failure into a reported
    # success and let `set -e` sail past genuine failures uncaught.
    local code=0
    timeout --kill-after=10 "$secs" "$@" || code=$?
    if [ "$code" -ne 0 ]; then
        if [ "$code" -eq 124 ] || [ "$code" -eq 137 ]; then
            echo "TIMEOUT after ${secs}s: $desc" >&2
        else
            echo "FAILED ($code): $desc" >&2
        fi
        return "$code"
    fi
}

# This script's own `smoke` step does `dpkg -i` straight into /opt, and
# installing dependencies rewrites the container's apt state wholesale.
# Running it directly on a developer's machine would really do both.
if [ ! -f /.dockerenv ] && ! grep -q 'docker\|containerd' /proc/1/cgroup 2>/dev/null; then
    echo "local-build.sh refuses to run outside a container -- see the" >&2
    echo "usage comment at the top of this file for the docker run command." >&2
    exit 1
fi

# See the usage comment's HOST_REPO_ROOT paragraph: sibling containers
# resolve bind-mount sources against the HOST's filesystem, not this
# container's, so the smoke step needs the real host path, not $REPO_ROOT.
if want_step smoke && [ -z "${HOST_REPO_ROOT:-}" ]; then
    echo "error: \$HOST_REPO_ROOT is not set, but the smoke step needs it to" >&2
    echo "bind-mount out/ into its sibling containers correctly. Re-run with:" >&2
    echo "  docker run ... -e HOST_REPO_ROOT=\"\$PWD\" ... bash packaging/ci/local-build.sh" >&2
    exit 1
fi

# run.sh (tested by tests/test_launch_scripts.py) prefers .venv/bin/python
# when present. A developer's own checkout commonly has one, and bind-
# mounting the whole repo carries it straight into this container -- but
# that .venv's "python3" is typically a symlink to an ABSOLUTE host path
# (e.g. /usr/bin/python3), which resolves inside this container to a
# completely different, package-less interpreter (the container's own
# default python3, not this script's venv). Confirmed: this is exactly
# what made test_sh_launcher_runs_from_another_directory fail the first
# time this script ran against a checkout with a .venv present. Shadow it
# with a tmpfs mount (see the usage comment) rather than silently ignoring
# it here -- deleting or renaming the host's venv from inside the container
# would reach back out and mutate the host checkout.
if [ -d "$REPO_ROOT/.venv" ] && [ -n "$(ls -A "$REPO_ROOT/.venv" 2>/dev/null)" ]; then
    echo "error: $REPO_ROOT/.venv exists and is not empty." >&2
    echo "run.sh would pick it up and use the HOST's python interpreter, which" >&2
    echo "does not exist as such in this container. Re-run with it shadowed:" >&2
    echo "  docker run --rm -v \"\$PWD:/repo\" --tmpfs /repo/.venv -w /repo \\" >&2
    echo "    ubuntu:22.04 bash packaging/ci/local-build.sh" >&2
    exit 1
fi

echo "==> system packages"
export DEBIAN_FRONTEND=noninteractive
bounded 300 "apt-get update" apt-get update
# dpkg-dev: dpkg-deb, used to build the two .deb packages.
# xvfb: runs the Qt GUI headless for the tests/selftest steps.
# build-essential: a C compiler, for any pinned package with no prebuilt wheel.
# software-properties-common: add-apt-repository, for deadsnakes below.
# docker.io: only the client binary -- talks to the host's docker socket
#   (mounted by the `docker run` in the usage comment) so the smoke step's
#   sibling containers can be started.
#
# The X11/GL/dbus libraries below are packaging/deb.py's RUNTIME_DEPENDS,
# by name (stripped of version/alternative syntax) plus libfontconfig1.
# They are installed here so Qt's xcb platform plugin can actually start in
# THIS (outer) container for the tests/build/selftest steps -- seeing the
# module docstring above for why going without them does not fail cleanly,
# it hangs. Installing them here is deliberately NOT the sufficiency check;
# that happens below in a separate, genuinely fresh sibling container.
bounded 600 "apt-get install base + Qt runtime packages" \
    apt-get install -y --no-install-recommends \
    dpkg-dev xvfb build-essential software-properties-common \
    ca-certificates gnupg git curl docker.io \
    libfontconfig1 libgl1 libglib2.0-0 libxkbcommon-x11-0 \
    libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libdbus-1-3

bounded 120 "add-apt-repository deadsnakes" add-apt-repository -y ppa:deadsnakes/ppa
bounded 300 "apt-get update (deadsnakes)" apt-get update
bounded 600 "apt-get install python3.12" \
    apt-get install -y --no-install-recommends python3.12 python3.12-venv python3.12-dev

VENV="$(mktemp -d /tmp/lt-venv.XXXXXX)"
python3.12 -m venv "$VENV"
PY="$VENV/bin/python"
export PATH="$VENV/bin:$PATH"
export PIP_DISABLE_PIP_VERSION_CHECK=1

echo "==> install dependencies (mirrors release.yml's build-linux job)"
# A fresh venv, never any preinstalled interpreter packages: PyInstaller
# bundles whatever is importable, and a stray package would move the
# runtime id between two builds of the same commit.
lock=(-c packaging/build-constraints.txt -c packaging/build-lock-linux.txt)
bounded 900 "pip install dev dependencies + pyinstaller" \
    "$PY" -m pip install "${lock[@]}" -r requirements-dev.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.7
bounded 1800 "pip install torch/torchvision" \
    "$PY" -m pip install "${lock[@]}" torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
# sam2's repo has symlinks (sam2/sam2_hiera_*.yaml). Without these three
# variables, git on a checkout that defaults core.symlinks=false writes
# 30-byte placeholder files instead, and the runtime id would differ from a
# real build. Set explicitly, exactly as release.yml does.
bounded 900 "pip install sam2 (no-build-isolation)" \
    env SAM2_BUILD_CUDA=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.symlinks GIT_CONFIG_VALUE_0=true \
    "$PY" -m pip install "${lock[@]}" --no-build-isolation \
        "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"

declare -A timings

run_step() {
    local name="$1"
    shift
    want_step "$name" || return 0
    echo "==> $name"
    local start
    start=$(date +%s)
    "$@"
    timings["$name"]=$(( $(date +%s) - start ))
}

step_tests() {
    bounded 1800 "pytest (tests labeling_tool/tests annotation_tool/tests)" \
        env QT_QPA_PLATFORM=offscreen "$PY" -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider
}

step_build() {
    rm -rf build "$DIST"
    bounded 1200 "pyinstaller build" "$PY" -m PyInstaller --noconfirm --log-level WARN packaging/labeling_tool.spec
}

step_selftest() {
    # `code=$?` must be set via `||`, not inside `if ! cmd; then` -- see
    # bounded()'s own comment above for exactly this bug (and this was a
    # second, independent occurrence of it: fixed inside bounded(), then
    # reproduced right outside it at this call site). Inside the
    # then-branch of `if ! cmd; then`, `$?` reflects the NEGATED pipeline's
    # own status (always 0), not the wrapped command's real exit code --
    # that silently turned a failed or hung selftest into a reported
    # success, printed the log, and still `exit 0`'d the whole script,
    # silently skipping `deb` and `smoke`.
    local code=0
    bounded 300 "selftest on the build output" xvfb-run -a "$DIST/LM_LabelingTool" --selftest=full || code=$?
    if [ "$code" -ne 0 ]; then
        if [ -f "$DIST/selftest.log" ]; then
            cat "$DIST/selftest.log"
        else
            echo "selftest.log not found (early crash?)"
        fi
        exit "$code"
    fi
    if [ -f "$DIST/selftest.log" ]; then
        cat "$DIST/selftest.log"
        rm -f "$DIST/selftest.log"
    fi
    rm -rf "$DIST/data" "$DIST/config.json"
}

step_layers() {
    RUNTIME_ID=$("$PY" packaging/layers.py runtime-id "$DIST")
    if ! [[ "$RUNTIME_ID" =~ ^r[0-9a-f]{8}$ ]]; then
        echo "bad runtime id: $RUNTIME_ID" >&2
        exit 1
    fi
    echo "runtime id: $RUNTIME_ID"
    mkdir -p diag
    "$PY" packaging/layers.py manifest "$DIST" > diag/runtime-manifest-local.txt
    printf '{"version": "%s", "variant": "full", "runtime": "%s", "commit": "local"}' \
        "$version" "$RUNTIME_ID" > "$DIST/build-info.json"
    rm -rf dist/app-layer
    "$PY" packaging/layers.py stage "$DIST" dist/app-layer
    local app_bytes
    app_bytes=$(find dist/app-layer -type f -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')
    printf 'app layer: %.1f MB\n' "$(awk -v b="$app_bytes" 'BEGIN{print b/1024/1024}')"
    if [ "$app_bytes" -gt $((20 * 1024 * 1024)) ]; then
        echo "app layer unexpectedly large: $app_bytes bytes" >&2
        exit 1
    fi
}

step_deb() {
    if [ -z "$RUNTIME_ID" ] && [ -f "$DIST/build-info.json" ]; then
        RUNTIME_ID=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['runtime'])" "$DIST/build-info.json")
    fi
    mkdir -p out
    rm -f out/*.deb
    # Fast gzip compression for local iteration (LT_FAST=1); a release build
    # uses xz via CI's own invocation of this same function.
    bounded 300 "deb.py build" env LT_FAST=1 "$PY" packaging/deb.py build "$DIST" out "$version"
    ls -la out/
}

step_smoke() {
    local runtime_deb app_deb bad_stage bad_deb
    runtime_deb=$(ls out/lm-labeling-tool-runtime_*.deb)
    app_deb=$(ls out/lm-labeling-tool_*.deb)

    # Built here (in the outer container, which already has python+deb.py)
    # but installed only inside the fresh sibling container below -- see
    # the module docstring for why the sufficiency/guard check cannot run
    # in this (deliberately non-minimal) outer container.
    bad_stage="$REPO_ROOT/out-bad"
    rm -rf "$bad_stage"
    bounded 300 "building a mismatched-runtime app deb" \
        env LT_FAST=1 "$PY" packaging/deb.py build --app-only --runtime-id rdeadbeef \
            "$DIST" "$bad_stage" "$version"
    bad_deb=$(ls "$bad_stage"/lm-labeling-tool_*.deb)

    echo "-- sufficiency + dependency guard, in a fresh minimal sibling container --"
    # This sibling container only ever gets dpkg-dev/xvfb/build-essential --
    # NOT packaging/deb.py's RUNTIME_DEPENDS. dpkg -i succeeding is a real
    # check (not a tautology: install a dependency, then verify the
    # dependency is satisfied), and it is also the one place a genuinely
    # missing-but-undeclared library would surface as a selftest crash
    # instead of a clean dpkg -i failure.
    #
    # KNOWN OPEN ISSUE, not yet root-caused (2026-09-30 investigation):
    # xvfb-run'ing a Qt app under the xcb platform in a container this bare
    # can HANG instead of failing cleanly. Confirmed directly: a plain
    # `pip install PyQt5` + `QApplication(["x"])` under `xvfb-run -a` in a
    # throwaway `ubuntu:22.04` container that only had
    # dpkg-dev/xvfb/build-essential/software-properties-common/ca-
    # certificates/gnupg/git/curl installed (i.e. this sufficiency
    # sibling's own package set) hung indefinitely -- `QT_QPA_PLATFORM=
    # offscreen` with the exact same binary printed "OK offscreen" and
    # exited immediately. Ruled out: a missing shared library at dlopen
    # time -- that fails fast with "Cannot load library ...: ... .so:
    # cannot open shared object file" (seen for libqoffscreen.so before
    # libfontconfig1 was installed), not a hang; adding libfontconfig1
    # alone did not fix the xcb hang, so it is not simply the offscreen
    # plugin's missing dependency recurring under xcb. Confirmed fix (for
    # the OUTER build container only, not here): explicitly installing
    # libgl1, libglib2.0-0, libxkbcommon-x11-0, libxcb-xinerama0,
    # libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0,
    # libxcb-render-util0, libxcb-shape0, libdbus-1-3 and libfontconfig1
    # (i.e. packaging/deb.py's RUNTIME_DEPENDS by name, plus fontconfig)
    # made the same QApplication() call under xcb succeed within seconds.
    # That fix is deliberately NOT applied to this sibling: doing so here
    # would be the exact tautology the brief warns against (pre-install the
    # dependency, then verify the dependency is satisfied). What was NOT
    # established before this investigation was time-boxed: whether apt's
    # own transitive dependencies of dpkg-dev/xvfb/build-essential already
    # cover enough of that list for THIS sibling to avoid the same hang --
    # i.e. whether RUNTIME_DEPENDS is genuinely sufficient on a truly
    # minimal base, which is the one question this check exists to answer.
    # Suspected but unconfirmed direction: Qt's xcb integration has known
    # failure modes that block indefinitely rather than erroring out (e.g.
    # a D-Bus/session-bus autolaunch attempt that never completes) when a
    # soft dependency is present but incomplete; confirming this would need
    # attaching strace/gdb to the hung process, which was not done. The
    # `bounded` wrapper below turns a recurrence of this hang into a clean
    # TIMEOUT failure after 900s rather than a silent, indefinite wait --
    # if this step times out, treat it as this same open issue, not a
    # regression in this script, and check whether CI's build-linux job
    # (a real GH-hosted ubuntu-22.04 runner, not a bare docker image, so it
    # may simply carry more of this out of the box) hits the same wall.
    bounded 900 "fresh-container sufficiency + dependency-guard check" \
        docker run --rm \
            -v "$HOST_REPO_ROOT/out:/out:ro" -v "$HOST_REPO_ROOT/out-bad:/bad:ro" \
            -e DEBIAN_FRONTEND=noninteractive ubuntu:22.04 bash -euo pipefail -c '
        apt-get update
        apt-get install -y --no-install-recommends dpkg-dev xvfb build-essential
        dpkg -i /out/lm-labeling-tool-runtime_*.deb /out/lm-labeling-tool_*.deb
        timeout --kill-after=10 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full
        echo "installed app selftest passed"
        if dpkg -i /bad/lm-labeling-tool_*.deb; then
            echo "a mismatched-runtime app deb installed; it must be rejected" >&2
            exit 1
        fi
        echo "mismatched-runtime app deb correctly rejected by dpkg"
    '
    rm -rf "$bad_stage"

    echo "-- usability: a stock desktop, not RUNTIME_DEPENDS itself, must already cover it --"
    # ubuntu-desktop-minimal, not packaging/deb.py's RUNTIME_DEPENDS: pre-
    # installing RUNTIME_DEPENDS before dpkg -i would make "no dependency
    # fixup needed afterwards" a tautology. This also doubles as the "built
    # on 22.04, runs on 24.04" cross-validation release.yml does, since
    # glibc only works forwards. Runs as a sibling container (via the
    # host's docker socket) rather than nested docker-in-docker.
    bounded 1800 "24.04 desktop usability cross-check" \
        docker run --rm -v "$HOST_REPO_ROOT/out:/out:ro" -e DEBIAN_FRONTEND=noninteractive ubuntu:24.04 bash -euo pipefail -c '
        apt-get update
        # A desktop metapackage postinst may try to start services; a
        # container has no init system to receive them. This is the
        # standard way to install such packages under plain docker run.
        printf "#!/bin/sh\nexit 101\n" > /usr/sbin/policy-rc.d
        chmod +x /usr/sbin/policy-rc.d
        apt-get install -y ubuntu-desktop-minimal
        apt-get install -y --no-install-recommends xvfb
        dpkg -i /out/lm-labeling-tool-runtime_*.deb /out/lm-labeling-tool_*.deb
        timeout --kill-after=10 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full
    '
    echo "24.04 desktop install + selftest passed"
}

run_step tests step_tests
run_step build step_build
run_step selftest step_selftest
run_step layers step_layers
run_step deb step_deb
run_step smoke step_smoke

echo ""
for s in "${known_steps[@]}"; do
    if [ -n "${timings[$s]+x}" ]; then
        printf '%-10s %5s s\n' "$s" "${timings[$s]}"
    fi
done
