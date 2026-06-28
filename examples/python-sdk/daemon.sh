#!/usr/bin/env bash
# Start / stop the DEDICATED jaato daemon the examples run against.
#
# Isolated from every other daemon on this host: its own IPC socket, WS port,
# pid file and log file. It never touches the live telegram bot (:8089) or the
# kb socket (/tmp/jaato-glm.sock). Provider auth (zhipuai/GLM) resolves from
# stored:zhipuai-auth — no key is passed here.
set -euo pipefail

JAATO_SERVER="${JAATO_SERVER:-/home/apanoia/.local/share/jaato/venv/bin/jaato-server}"
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
