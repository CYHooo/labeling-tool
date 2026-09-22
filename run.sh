#!/usr/bin/env bash
# Launch the labeling tool; pick online / local job / few-shot on the login screen.
# Run from anywhere: ./run.sh [args...]  (arguments are passed through)
# Uses .venv/bin/python when present, otherwise python3 / python on PATH.

# Work from the repo root so the package and relative paths (./checkpoint) resolve.
cd "$(dirname "$(readlink -f "$0")")" || exit 1

if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

exec "$PY" -m labeling_tool.app "$@"
