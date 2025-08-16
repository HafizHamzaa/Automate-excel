#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
	PY=python3
fi
exec "$PY" -m app.main