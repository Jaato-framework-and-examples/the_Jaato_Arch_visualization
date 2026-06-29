#!/usr/bin/env bash
# Build the ts-sdk examples: vendor the LOCAL @jaato/sdk (built), npm install,
# and tsc type-check. The examples are a thin WebSocket client; the agent loop /
# plugins run in the daemon (the same dedicated daemon python-sdk/daemon.sh runs,
# serving both IPC and WS :8099).
set -euo pipefail
cd "$(dirname "$0")"

SDK_SRC="${JAATO_SDK_TS_SRC:-$HOME/Sources/Jaato-framework-and-examples/jaato/jaato-sdk-ts}"

# Ensure the SDK is built (its package main is dist/index.js).
(cd "$SDK_SRC" && npm run build >/dev/null 2>&1) || true

# Vendor it via a stable in-project symlink so package.json stays portable
# (no absolute path committed); vendor/ is gitignored.
mkdir -p vendor
rm -f vendor/jaato-sdk
ln -s "$SDK_SRC" vendor/jaato-sdk

npm install
npm run build   # tsc type-check (noEmit)

echo
echo "built. next:"
echo "  (examples/python-sdk/daemon.sh start  — shared dedicated daemon, serves WS :8099)"
echo "  ./run.sh src/ex01_basic_ask.ts"
echo "  ./run.sh src/smoke.ts"
