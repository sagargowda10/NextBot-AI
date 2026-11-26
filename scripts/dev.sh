#!/usr/bin/env bash
# Run NextBot locally without Docker: backend on SQLite (demo mode) + Next.js dev server.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/backend"
python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements-dev.txt
[ -f .env ] || cp "$ROOT/.env.example" .env
uvicorn app.main:create_app --factory --reload --port 8000 &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT

cd "$ROOT/frontend"
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
