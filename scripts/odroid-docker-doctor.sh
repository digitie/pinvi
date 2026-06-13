#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PINVI_NODE_NAME="${PINVI_NODE_NAME:-odroid-m1s}"
export PINVI_EXPECTED_ARCH="${PINVI_EXPECTED_ARCH:-aarch64}"
export PINVI_EXPECTED_OS_VERSION="${PINVI_EXPECTED_OS_VERSION:-24.04}"

exec "${SCRIPT_DIR}/ops-node-doctor.sh"
