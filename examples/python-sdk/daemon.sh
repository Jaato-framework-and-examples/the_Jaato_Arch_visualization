#!/usr/bin/env bash
# Start / stop the DEDICATED jaato daemon the examples run against.
#
# Its own IPC socket, WS port, pid file and log file, so it won't collide with
# any other jaato daemon you may be running on the host. Provider auth
# (openrouter) is read as ${JAATO_OPENROUTER_API_KEY}: the python-sdk examples
# pass it via env_file (.env); the ts-sdk / ws examples connect over WS with no
# env_file, so export JAATO_OPENROUTER_API_KEY in THIS shell before `start` and
# the daemon inherits it.
set -euo pipefail

# Prefer jaato-server on PATH; fall back to the conventional pip-install location.
JAATO_SERVER="${JAATO_SERVER:-$(command -v jaato-server || echo "$HOME/.local/share/jaato/venv/bin/jaato-server")}"
# Provider auth uses the api_key knob with ${ENV_VAR} interpolation
# (plugin_configs.openrouter.api_key = "${JAATO_OPENROUTER_API_KEY}"). Export the
# key before starting (ts-sdk/ws) or set it in .env (python-sdk env_file). This
# replaced a "pass://jaato/openrouter/api-key" secret URI, whose resolver ships
# only in the private jaato-premium package (unavailable on a public checkout).
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
