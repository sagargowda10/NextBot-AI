#!/usr/bin/env bash
# Reproducibly build NextBot-AI-Complete-Project.zip from a clean tree (no node_modules, builds, caches, secrets).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../NextBot-AI-Complete-Project.zip}"
cd "$ROOT/.."
rm -f "$OUT"
zip -rq "$OUT" "$(basename "$ROOT")" \
  -x '*/node_modules/*' '*/.next/*' '*/__pycache__/*' '*.pyc' '*/.venv/*' '*/.pytest_cache/*' '*/.mypy_cache/*' \
     '*/.ruff_cache/*' '*.db' '*.db-*' '*/.env' '*/playwright-report/*' '*/test-results/*'
echo "wrote $OUT"
