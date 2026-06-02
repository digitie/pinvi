#!/usr/bin/env bash
# Backward-compatible wrapper. Canonical Docker app workflow:
# `scripts/docker-app.sh` and `docs/runbooks/docker-app.md`.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--keep-running" || "${1:-}" == "keep-running" ]]; then
  exec "$ROOT_DIR/scripts/docker-app.sh" smoke --keep-running
fi

exec "$ROOT_DIR/scripts/docker-app.sh" smoke
