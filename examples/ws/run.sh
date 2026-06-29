#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec env NODE_EXTRA_CA_CERTS="${HOME}/.jaato/certs/ca.crt" node "$@"
