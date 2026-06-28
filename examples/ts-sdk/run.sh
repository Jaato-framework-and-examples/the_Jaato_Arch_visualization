#!/usr/bin/env bash
# Run a TS example via tsx, trusting the daemon's self-signed Jaato Dev CA for
# the wss:// connection. NODE_EXTRA_CA_CERTS is the clean way (no disabling of
# TLS verification); it must be set before Node starts, so it lives here rather
# than in the example source.
set -euo pipefail
cd "$(dirname "$0")"
exec env NODE_EXTRA_CA_CERTS="${HOME}/.jaato/certs/ca.crt" ./node_modules/.bin/tsx "$@"
