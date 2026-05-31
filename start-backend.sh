#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  python3 -m venv .venv
fi

if [[ ! -x ".venv/bin/uvicorn" ]]; then
  ".venv/bin/python" -m pip install -r backend/requirements.txt
fi

args=(
  main:app
  --app-dir backend
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8000}"
)

if [[ "${RELOAD:-0}" == "1" ]]; then
  args+=(--reload --reload-dir backend)
fi

exec ".venv/bin/uvicorn" "${args[@]}"
