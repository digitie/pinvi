#!/usr/bin/env bash
# Run a Python script from stdin inside a Docker container on a remote host.
#
# Usage:
#   scripts/remote-docker-python.sh <n150-ssh-target> pinvi-api-latest <<'PY'
#   print("hello")
#   PY

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/remote-docker-python.sh <ssh-target> <container-name> < script.py

Example:
  scripts/remote-docker-python.sh <n150-ssh-target> pinvi-api-latest <<'PY'
  print("hello from container")
  PY
EOF
}

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi

SSH_TARGET="$1"
CONTAINER="$2"

if [[ ! "$SSH_TARGET" =~ ^[A-Za-z0-9_.@:-]+$ ]]; then
  echo "Invalid ssh target: $SSH_TARGET" >&2
  exit 2
fi

if [[ ! "$CONTAINER" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "Invalid container name: $CONTAINER" >&2
  exit 2
fi

ssh -o BatchMode=yes "$SSH_TARGET" "docker exec -i $CONTAINER python -"
