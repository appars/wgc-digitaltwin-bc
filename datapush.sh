#!/usr/bin/env bash
set -Eeuo pipefail

# --- Config ---
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"
VENV_PY=".venv/bin/python"
LOG="replay.log"
PIDFILE="replay.pid"
BACKEND_URL="${BACKEND_URL:-https://wgc-digitaltwin-bc-1.onrender.com}"

start() {
  # Kill any existing
  pkill -f "simulator/replay.py" 2>/dev/null || true

  # Simple log rotation (keep one previous)
  [[ -f "$LOG" ]] && mv "$LOG" "${LOG}.1" || true

  # Verify deps fast (optional)
  "$VENV_PY" -c "import requests" 2>/dev/null || {
    echo "[err] 'requests' not found in venv. Installing..."
    "$VENV_PY" -m pip install -q --upgrade pip
    "$VENV_PY" -m pip install -q requests python-dotenv
  }

  # Health check (optional but nice)
  if curl -fsS "$BACKEND_URL/ingest-wgc/health" > /dev/null; then
    echo "[ok] Backend health check passed: $BACKEND_URL"
  else
    echo "[warn] Backend health check failed (continuing): $BACKEND_URL"
  fi

  # Start unbuffered, capture PID, and echo env for sanity
  BACKEND_URL="$BACKEND_URL" PYTHONUNBUFFERED=1 \
  nohup bash -lc 'echo "BACKEND_URL=${BACKEND_URL}";
  exec '"$VENV_PY"' -u simulator/replay.py' > "$LOG" 2>&1 &
  echo $! > "$PIDFILE"

  echo "[start] PID $(cat "$PIDFILE") → logging to $LOG"
  sleep 1
  tail -n 50 "$LOG" || true
}

stop() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" || true
    sleep 1
  fi
  pkill -f "simulator/replay.py" 2>/dev/null || true
  rm -f "$PIDFILE"
  echo "[stop] replay stopped."
}

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[status] running (PID $(cat "$PIDFILE"))"
  else
    echo "[status] not running"
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac

