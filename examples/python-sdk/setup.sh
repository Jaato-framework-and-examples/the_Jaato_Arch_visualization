#!/usr/bin/env bash
# Build the python-sdk examples project: a venv with the LOCAL jaato-sdk
# installed editable (`pip install -e`). The examples are a thin client; the
# agent loop / plugins all run in the daemon (see daemon.sh), so only the SDK
# is needed here.
set -euo pipefail
cd "$(dirname "$0")"

SDK_SRC="${JAATO_SDK_SRC:-$HOME/Sources/Jaato-framework-and-examples/jaato/jaato-sdk}"

python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -e "$SDK_SRC"

echo
echo "built. next:"
echo "  ./daemon.sh start          # spin the dedicated GLM daemon"
echo "  ./.venv/bin/python smoke.py # run every example, assert green"
