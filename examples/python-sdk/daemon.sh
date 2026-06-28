#!/usr/bin/env bash
# Start / stop the DEDICATED jaato daemon the examples run against.
#
# Its own IPC socket, WS port, pid file and log file, so it won't collide with
# any other jaato daemon you may be running on the host. Provider auth
# (openrouter) resolves from a `pass:` knob in the profiles
# (plugin_configs.openrouter.api_key) — no key is passed here.
set -euo pipefail

# Prefer jaato-server on PATH; fall back to the conventional pip-install location.
JAATO_SERVER="${JAATO_SERVER:-$(command -v jaato-server || echo "$HOME/.local/share/jaato/venv/bin/jaato-server")}"
# Provider auth is NOT injected here. Credentials live in the profiles as a
# `pass:` resolver knob of the provider plugin
# (plugin_configs.openrouter.api_key = "pass://jaato/openrouter/api-key") — no
# env var, no secret in any tracked file.
SOCKET="/tmp/jaato-examples.sock"
WSPORT=":8099"
PIDFILE="/tmp/jaato-examples.pid"
LOGFILE="/tmp/jaato-examples.log"

start() {
  if [ -S "$SOCKET" ]; then echo "already up: $SOCKET"; exit 0; fi
  rm -f "$SOCKET"
  "$JAATO_SERVER" --ipc-socket "$SOCKET" --web-socket "$WSPORT" \
    --pid-file "$PIDFILE" --log-file "$LOGFILE" --daemon
  for i in $(seq 1 60); do
    [ -S "$SOCKET" ] && { echo "up after ${i}s: $SOCKET (ws$WSPORT)"; exit 0; }
    sleep 1
  done
  echo "daemon did not come up — see $LOGFILE" >&2; exit 1
}

stop() {
  "$JAATO_SERVER" --stop --pid-file "$PIDFILE" || true
  rm -f "$SOCKET"
  echo "stopped"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) [ -S "$SOCKET" ] && echo "up: $SOCKET" || echo "down" ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
