#!/usr/bin/env bash
# Build the Linux app inside the pinned builder image
# (packaging/linux/builder.Dockerfile): install the locked dependencies,
# PyInstaller, selftest, runtime id + build info, and stage the app layer.
# Everything that lands in dist/ comes from this script -- CI runs it, and so
# does local-build.sh's build step -- so a release build and a local build of
# the same commit bundle the same files.
#
# Run from the repository root, mounted at the working directory:
#   docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp/home -e USER=builder \
#     -e LT_VERSION=v0.2.4 -e LT_COMMIT=abc1234 -e PIP_CACHE_DIR=/pipcache \
#     -v "$PWD:/w" -v "$HOME/.cache/pip:/pipcache" -w /w \
#     lt-linux-builder bash packaging/ci/linux-build.sh
#
# Writes dist/LM_LabelingTool, dist/app-layer, diag/runtime-id.txt and
# diag/runtime-manifest-linux.txt. With LT_INSTALL_ONLY=1 it stops after the
# dependency install (local-build.sh's tests step needs only the venv).
# The venv is /tmp/buildenv; an existing one is reused.
set -euo pipefail

: "${LT_VERSION:?set LT_VERSION (a tag like v0.2.4, or 0.0.0-dev-<sha>)}"
: "${LT_COMMIT:?set LT_COMMIT (short commit id)}"
mkdir -p "$HOME"

# A fresh venv, never the image's own site-packages: anything extra there
# would be bundled by PyInstaller and move the runtime id.
[ -x /tmp/buildenv/bin/python ] || python3.12 -m venv /tmp/buildenv
export PATH="/tmp/buildenv/bin:$PATH"

# sam2's repo has symlinks (sam2/sam2_hiera_*.yaml); without core.symlinks
# git writes 30-byte placeholder files and the runtime id differs.
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.symlinks GIT_CONFIG_VALUE_0=true
export SAM2_BUILD_CUDA=0 PIP_DISABLE_PIP_VERSION_CHECK=1
lock=(-c packaging/build-constraints.txt -c packaging/build-lock-linux.txt)
python -m pip install "${lock[@]}" -r requirements-dev.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.7
python -m pip install "${lock[@]}" torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
# sam2's build needs the torch installed above (no CUDA extension: SAM2_BUILD_CUDA=0)
python -m pip install "${lock[@]}" --no-build-isolation "git+https://github.com/facebookresearch/sam2.git@2b90b9f5ceec907a1c18123530e92e794ad901a4"
if [ "${LT_INSTALL_ONLY:-}" = "1" ]; then
    exit 0
fi

rm -rf build dist/LM_LabelingTool dist/app-layer
pyinstaller --noconfirm --log-level WARN packaging/labeling_tool.spec

# Selftest the packaged exe. It logs to the XDG data dir, not dist/.
log="$HOME/.local/share/lm-labeling-tool/selftest.log"
rm -f "$log"
set +e
timeout 300 xvfb-run -a dist/LM_LabelingTool/LM_LabelingTool --selftest=full
code=$?
set -e
if [ -f "$log" ]; then cat "$log"; else echo "selftest.log not found (early crash?)"; fi
if [ "$code" -ne 0 ]; then
    echo "selftest failed with exit code $code" >&2
    exit 1
fi
# the app may create these next to the exe; never ship them
rm -rf dist/LM_LabelingTool/data dist/LM_LabelingTool/config.json

# The runtime id measures the runtime layer itself (each file's path and size).
rt=$(python packaging/layers.py runtime-id dist/LM_LabelingTool)
if ! [[ "$rt" =~ ^r[0-9a-f]{8}$ ]]; then
    echo "bad runtime id: $rt" >&2
    exit 1
fi
mkdir -p diag
python packaging/layers.py manifest dist/LM_LabelingTool > diag/runtime-manifest-linux.txt
echo "$rt" > diag/runtime-id.txt
echo "runtime id: $rt"
printf '{"version": "%s", "variant": "full", "runtime": "%s", "commit": "%s"}' \
    "${LT_VERSION#v}" "$rt" "$LT_COMMIT" > dist/LM_LabelingTool/build-info.json
cat dist/LM_LabelingTool/build-info.json

python packaging/layers.py stage dist/LM_LabelingTool dist/app-layer
app_bytes=$(find dist/app-layer -type f -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')
printf 'app layer: %.1f MB\n' "$(awk -v b="$app_bytes" 'BEGIN{print b/1024/1024}')"
# The update zip is what every routine update downloads. If it climbs back
# into the tens of MB something leaked out of the runtime layer.
if [ "$app_bytes" -gt $((20 * 1024 * 1024)) ]; then
    echo "app layer unexpectedly large: $app_bytes bytes" >&2
    exit 1
fi
