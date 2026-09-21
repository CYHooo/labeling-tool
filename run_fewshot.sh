#!/usr/bin/env bash
# Launch the few-shot annotation tool (SAM3/SAM2, needs torch).
# Run from anywhere: ./run_fewshot.sh [args...]  (arguments are passed through)
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

exec "$PY" -m annotation_tool.main "$@"
