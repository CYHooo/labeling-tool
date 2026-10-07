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
# "smoke" step's availability and 24.04 cross-validation checks can each
# start a fresh sibling container -- NOT nested docker-in-docker, a
# sibling started via the HOST's own dockerd through the mounted socket;
# --tmpfs /repo/.venv shadows a host dev venv if one exists -- see the
# check below for why that matters):
#
#   docker build -f packaging/linux/builder.Dockerfile -t lt-linux-builder .
#   docker run --rm -v "$PWD:/repo" -v /var/run/docker.sock:/var/run/docker.sock \
#     -e HOST_REPO_ROOT="$PWD" --tmpfs /repo/.venv -w /repo \
#     lt-linux-builder bash packaging/ci/local-build.sh
#
# lt-linux-builder is the pinned ubuntu:22.04 image CI builds in (base
# digest, apt snapshot date, exact Python 3.12.10) -- the same system
# libraries get bundled, so this build's runtime id is CI's.
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
# The dependency install, PyInstaller build, selftest and layers are
# packaging/ci/linux-build.sh -- the script release.yml's build-linux job runs
# in the same pinned image -- so this is a verification of CI's build, not of
# a look-alike.
#
# Every external call that can hang -- a GUI process, dpkg, a container
# download -- goes through bounded() below. This project has already been
# burned by an unbounded wait: a stray MsgBox in installer.iss once hung a
# Windows CI job for 96 minutes before anyone noticed (see local-build.ps1 /
# bounded.ps1). A verification script that can hang forever is worse than
# no verification script, because the failure mode is silence, not an error.
#
# The "smoke" step mirrors release.yml's build-linux install checks one
# for one -- see step_smoke() below for the four checks and why each runs
# where it does. In short: availability on a stock 22.04 desktop container
# (dpkg -i only), sufficiency and the zip-update round trip in THIS outer
# container (which, like CI's runner, carries the libraries the build
# needs), and a 24.04 desktop container for the cross-validation.

set -euo pipefail

known_steps=(tests build selftest layers deb smoke)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DIST="dist/LM_LabelingTool"
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
    echo "    lt-linux-builder bash packaging/ci/local-build.sh" >&2
    exit 1
fi

# Only the pinned builder image bundles the system libraries CI bundles; a
# plain ubuntu:22.04 with today's apt would give a different runtime id.
if [ ! -x /opt/hostedtoolcache/Python/3.12.10/x64/bin/python3.12 ]; then
    echo "error: not running in the lt-linux-builder image (see the usage comment)." >&2
    echo "  docker build -f packaging/linux/builder.Dockerfile -t lt-linux-builder ." >&2
    exit 1
fi

# The dependency install, PyInstaller build, selftest and layers all run
# through packaging/ci/linux-build.sh -- the very script CI runs in this
# image -- so this build bundles exactly what a release does.
PY=/tmp/buildenv/bin/python
export LT_VERSION="$version" LT_COMMIT=local

ensure_venv() {
    if [ ! -x "$PY" ]; then
        bounded 3600 "install the locked dependencies (linux-build.sh)" \
            env LT_INSTALL_ONLY=1 bash packaging/ci/linux-build.sh
    fi
}

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
    ensure_venv
    bounded 1800 "pytest (tests labeling_tool/tests annotation_tool/tests)" \
        env QT_QPA_PLATFORM=offscreen "$PY" -m pytest tests labeling_tool/tests annotation_tool/tests -q -p no:cacheprovider
}

step_build() {
    # Install (reused venv), PyInstaller, selftest, runtime id + build info,
    # app layer: one script, the one CI runs.
    bounded 3600 "linux-build.sh (build, selftest, layers)" bash packaging/ci/linux-build.sh
    RUNTIME_ID=$(cat diag/runtime-id.txt)
    echo "runtime id: $RUNTIME_ID"
}

# selftest and layers run inside the build step's linux-build.sh; the names
# stay for parity with local-build.ps1. Asked for without build they would
# check nothing, so refuse rather than report a pass.
step_selftest() {
    want_step build || { echo "selftest runs inside the build step: add build to --steps" >&2; exit 1; }
}

step_layers() {
    want_step build || { echo "layers runs inside the build step: add build to --steps" >&2; exit 1; }
}

step_deb() {
    # The packaging helpers are stdlib-only: the image's Python will do, so
    # `--steps deb` needs no dependency install.
    if [ -z "$RUNTIME_ID" ] && [ -f "$DIST/build-info.json" ]; then
        RUNTIME_ID=$(python3.12 -c "import json,sys; print(json.load(open(sys.argv[1]))['runtime'])" "$DIST/build-info.json")
    fi
    if [ -z "$RUNTIME_ID" ]; then
        echo "no runtime id: run the layers step first" >&2
        exit 1
    fi
    if [ ! -d dist/app-layer ]; then
        python3.12 packaging/layers.py stage "$DIST" dist/app-layer
    fi
    mkdir -p out
    rm -f out/*.deb out/*.zip
    # Fast gzip compression for local iteration (LT_FAST=1); a release build
    # uses xz via CI's own invocation of this same function.
    bounded 300 "deb.py build" env LT_FAST=1 python3.12 packaging/deb.py build "$DIST" out "$version"
    # The app-layer update zip, named for the runtime id it was built
    # against -- what the smoke step's update round trip applies.
    bounded 300 "update_zip.py" python3.12 packaging/update_zip.py dist/app-layer out "$version" "$RUNTIME_ID" linux
    ls -la out/
}

step_smoke() {
    # The docker client for the sibling containers below. Installed here, not
    # in the image, so nothing beyond what CI has can reach the build steps;
    # from the image's own apt snapshot.
    if ! command -v docker >/dev/null; then
        bounded 300 "apt-get update (snapshot)" apt-get -o Acquire::Check-Valid-Until=false update
        bounded 600 "apt-get install docker client" apt-get install -y --no-install-recommends docker.io
    fi
    # Mirrors release.yml's build-linux install checks one for one (CI runs
    # 36841286350..36969300396 settled their shape):
    #
    #   1. availability -- a stock 22.04 DESKTOP (ubuntu-desktop-minimal),
    #      dpkg -i only: does a normal desktop already carry everything
    #      RUNTIME_DEPENDS declares? Needing apt's fix-up would mean users
    #      cannot install either.
    #   2. sufficiency -- THIS outer container, which (like CI's runner)
    #      already has RUNTIME_DEPENDS + deb.BUNDLED_LIBS installed for the
    #      build: install the deb and run the installed app's selftest.
    #   3. update round trip -- damage one installed app-layer file, let
    #      the installed app apply this build's update zip (the path every
    #      routine update takes), and check the file is back, the journal
    #      is gone and the selftest still passes.
    #   4. 24.04 cross-validation -- a stock 24.04 desktop: install AND run
    #      the selftest (glibc only works forwards). Started in the
    #      background so its desktop install overlaps check 1, as in CI.
    #
    # This replaces an earlier design that ran check 2 in a bare ubuntu:22.04
    # sibling with only dpkg-dev/xvfb/build-essential: there dpkg -i cannot
    # succeed (the declared libraries are simply absent -- the same wall CI
    # run 36841286350 hit) and the step hung or failed for reasons unrelated
    # to the package. Check 1 answers the question that design was after.
    local zip sha victim noble_log noble_exit noble_pid code

    echo "-- 24.04 cross-validation: started in the background --"
    noble_log="$(mktemp /tmp/lt-noble.XXXXXX)"; noble_exit="$noble_log.exit"
    (
        set +e
        timeout --kill-after=10 1800 docker run --rm -v "$HOST_REPO_ROOT/out:/out:ro" \
            -e DEBIAN_FRONTEND=noninteractive ubuntu:24.04 bash -euo pipefail -c '
            apt-get update
            # A desktop metapackage postinst may try to start services; a
            # container has no init system to receive them.
            printf "#!/bin/sh\nexit 101\n" > /usr/sbin/policy-rc.d
            chmod +x /usr/sbin/policy-rc.d
            apt-get install -y ubuntu-desktop-minimal
            apt-get install -y --no-install-recommends xvfb
            dpkg -i /out/lm-labeling-tool_*.deb
            set +e
            timeout --kill-after=10 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full
            code=$?
            set -e
            for f in selftest.log selftest-hang.txt; do
              p="$HOME/.local/share/lm-labeling-tool/$f"
              if [ -s "$p" ]; then echo "--- $f"; cat "$p"; fi
            done
            exit "$code"
        '
        echo $? > "$noble_exit"
    ) > "$noble_log" 2>&1 < /dev/null &
    noble_pid=$!

    echo "-- 1/4 availability: dpkg -i on a stock 22.04 desktop, no fix-up --"
    bounded 1800 "22.04 desktop availability check" \
        docker run --rm -v "$HOST_REPO_ROOT/out:/out:ro" -e DEBIAN_FRONTEND=noninteractive ubuntu:22.04 bash -euo pipefail -c '
        apt-get update
        printf "#!/bin/sh\nexit 101\n" > /usr/sbin/policy-rc.d
        chmod +x /usr/sbin/policy-rc.d
        apt-get install -y ubuntu-desktop-minimal
        dpkg -i /out/lm-labeling-tool_*.deb
    '

    echo "-- 2/4 sufficiency: install here and run the installed app --"
    bounded 600 "dpkg -i (outer container)" dpkg -i out/lm-labeling-tool_*.deb
    rm -f "$HOME/.local/share/lm-labeling-tool/selftest.log" "$HOME/.local/share/lm-labeling-tool/selftest-hang.txt"
    code=0
    timeout --kill-after=10 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full || code=$?
    for f in selftest.log selftest-hang.txt; do
        if [ -s "$HOME/.local/share/lm-labeling-tool/$f" ]; then
            echo "--- $f"; cat "$HOME/.local/share/lm-labeling-tool/$f"
        fi
    done
    if [ "$code" -ne 0 ]; then
        echo "installed-app selftest failed with exit code $code" >&2
        return 1
    fi

    echo "-- 3/4 update round trip: the installed app applies its own zip --"
    zip=$(ls out/update-v*-linux.zip)
    sha=$(sha256sum "$zip" | cut -d' ' -f1)
    # Damage one installed app-layer file, then let the zip repair it.
    # (build-info.json must stay intact: apply_patch reads its runtime id.)
    # A fixed file the --apply-update run never imports: the first .pyc find
    # meets depends on directory order and once was a module app.py imports
    # at startup, so the app could not start to repair itself. The selftest
    # below imports it, proving the zip restored it.
    victim=_internal/labeling_tool/selftest.pyc
    if [ ! -f "/opt/lm-labeling-tool/$victim" ]; then
        echo "no installed $victim to damage" >&2
        return 1
    fi
    rm "/opt/lm-labeling-tool/$victim"
    bounded 300 "--apply-update on the installed app" \
        /opt/lm-labeling-tool/LM_LabelingTool --apply-update "$zip" --sha256 "$sha"
    if [ ! -f "/opt/lm-labeling-tool/$victim" ]; then
        echo "the zip update did not restore $victim" >&2
        return 1
    fi
    if [ -e /opt/lm-labeling-tool/.update-journal ]; then
        echo "the zip update left its journal behind" >&2
        return 1
    fi
    rm -f "$HOME/.local/share/lm-labeling-tool/selftest.log" "$HOME/.local/share/lm-labeling-tool/selftest-hang.txt"
    code=0
    timeout --kill-after=10 300 xvfb-run -a /opt/lm-labeling-tool/LM_LabelingTool --selftest=full || code=$?
    if [ "$code" -ne 0 ]; then
        for f in selftest.log selftest-hang.txt; do
            if [ -s "$HOME/.local/share/lm-labeling-tool/$f" ]; then
                echo "--- $f"; cat "$HOME/.local/share/lm-labeling-tool/$f"
            fi
        done
        echo "selftest after the zip update failed with exit code $code" >&2
        return 1
    fi
    echo "zip update applied and the app still passes its selftest"

    echo "-- 4/4 24.04 cross-validation: collecting --"
    wait "$noble_pid" || true
    cat "$noble_log"
    code=$(cat "$noble_exit" 2>/dev/null || echo 1)
    rm -f "$noble_log" "$noble_exit"
    if [ "$code" -ne 0 ]; then
        echo "24.04 desktop install + selftest failed (exit $code)" >&2
        return 1
    fi
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
