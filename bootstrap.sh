#!/usr/bin/env bash
# Idempotent venv setup for tone-analyzer (used by the Claude skill and by humans).
# First run: ~30-60 s. Subsequent runs: <1 s if pyproject.toml is unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
STAMP="$VENV_DIR/.pyproject.sha"

if command -v sha256sum >/dev/null 2>&1; then
  CURRENT_SHA="$(sha256sum pyproject.toml | awk '{print $1}')"
else
  CURRENT_SHA="$(shasum -a 256 pyproject.toml | awk '{print $1}')"
fi

if [ -d "$VENV_DIR" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$CURRENT_SHA" ]; then
  exit 0
fi

# scipy ships no wheels for Python 3.14+ yet, so the venv must be built on 3.11-3.13.
supported() { "$1" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null; }
pick_python() {
  for c in python3 python3.13 python3.12 python3.11; do
    command -v "$c" >/dev/null 2>&1 && supported "$c" && { command -v "$c"; return; }
  done
  if command -v uv >/dev/null 2>&1; then uv python install 3.12 >&2 && uv python find 3.12; return; fi
  echo "bootstrap: Python 3.11-3.13 not found; install one or install uv (https://docs.astral.sh/uv/)" >&2
  exit 1
}
if [ -x "$VENV_DIR"/bin/python ] && ! supported "$VENV_DIR"/bin/python; then rm -rf "$VENV_DIR"; fi
if [ ! -d "$VENV_DIR" ]; then
  "$(pick_python)" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e ".[dev]"

echo "$CURRENT_SHA" > "$STAMP"
