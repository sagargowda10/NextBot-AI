#!/usr/bin/env bash
# Full backend verification: lint, types, unit + integration tests (integration needs requirements-dev.txt; PG test needs Docker).
set -euo pipefail
cd "$(dirname "$0")/../backend"
ruff check app tests
mypy app
pytest tests/unit -q
pytest tests/integration -q -rs
