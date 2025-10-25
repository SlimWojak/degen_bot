#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"; PID_FILE="$RUN_DIR/uvicorn.pid"; LOG_FILE="$RUN_DIR/backend.log"
PORT="${PORT:-8000}"; HOST="127.0.0.1"
mkdir -p "$RUN_DIR"
is_running(){ [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }
start_bg(){
  if is_running; then echo "running (pid $(cat "$PID_FILE"))"; exit 0; fi
  
  # Kill any existing processes on the port
  lsof -ti :8000 | xargs -n1 kill -9 2>/dev/null || true
  sleep 1
  
  : > "$LOG_FILE"
  nohup /Library/Developer/CommandLineTools/usr/bin/python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"; echo "started (pid $(cat "$PID_FILE")) → $LOG_FILE"
}
stop(){
  if ! is_running; then echo "stopped"; rm -f "$PID_FILE"; exit 0; fi
  kill "$(cat "$PID_FILE")" 2>/dev/null || true; sleep 0.5
  is_running && kill -9 "$(cat "$PID_FILE")" 2>/dev/null || true
  rm -f "$PID_FILE"; echo "stopped"
}
wait_ready(){ local t=$((SECONDS+${1:-20}))
  while (( SECONDS < t )); do curl -sS --max-time 1 "http://$HOST:$PORT/status" >/dev/null && { echo "ready"; return 0; }; sleep 0.5; done
  echo "not ready"; tail -n 80 "$LOG_FILE" || true; exit 1
}
logs(){ tail -n ${1:-120} -f "$LOG_FILE"; }
restart(){ stop || true; start_bg; wait_ready 20; }
case "${1:-}" in start) start_bg ;; stop) stop ;; restart) restart ;; wait) wait_ready "${2:-20}" ;; logs) logs "${2:-120}" ;; status) is_running && echo "running" || echo "stopped" ;; *) echo "usage: devctl.sh {start|stop|restart|wait|logs|status}"; exit 2 ;; esac
