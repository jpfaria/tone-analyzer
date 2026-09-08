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

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e ".[dev]"

echo "$CURRENT_SHA" > "$STAMP"
