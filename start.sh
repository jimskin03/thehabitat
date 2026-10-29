#!/usr/bin/env bash
# One-command start for The Habitat: the Django environment server (port 8000)
# plus the reverie simulation server, both in the background, with one Ctrl+C
# to stop both.
#
#   ./start.sh                  start both, then follow the reverie log
#   ./start.sh send "run 100"   type a command into the running reverie prompt
#   ./start.sh logs             follow the logs again from another terminal
#   ./start.sh stop             stop both from another terminal
#
# Optional settings (environment variables):
#   VENV        path to the virtualenv   (default: environment/frontend_server/.venv)
#   FORK_SIM    simulation to fork from  (default: base_the_ville_isabella_maria_klaus)
#   SIM_NAME    name of the new run      (default: habitat-<timestamp>)
#   WEB_HOST    address Django binds to  (default: 127.0.0.1; "tailscale" uses `tailscale ip -4`)
#   WEB_PORT    Django port              (default: 8000)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$ROOT/environment/frontend_server"
SIM_DIR="$ROOT/reverie/backend_server"
VENV="${VENV:-$WEB_DIR/.venv}"
WEB_PORT="${WEB_PORT:-8000}"
RUN_DIR="$ROOT/.habitat-run"
FIFO="$RUN_DIR/reverie.in"
WEB_LOG="$RUN_DIR/web.log"
SIM_LOG="$RUN_DIR/reverie.log"
PIDS="$RUN_DIR/pids"

stop_all() {
  if [ -f "$PIDS" ]; then
    while read -r pid; do
      [ -n "$pid" ] && kill "$pid" 2>/dev/null
    done < "$PIDS"
    sleep 1
    while read -r pid; do
      [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
    done < "$PIDS"
    rm -f "$PIDS"
  fi
  rm -f "$FIFO"
}

case "${1:-start}" in
  stop)
    stop_all
    echo "Stopped."
    exit 0
    ;;
  logs)
    exec tail -n 50 -f "$WEB_LOG" "$SIM_LOG"
    ;;
  send)
    shift
    [ -p "$FIFO" ] || { echo "reverie is not running (start it with ./start.sh)"; exit 1; }
    printf '%s\n' "$*" > "$FIFO"
    exit 0
    ;;
  start) ;;
  *)
    echo "Usage: ./start.sh [start|send <command>|logs|stop]"
    exit 2
    ;;
esac

# --- checks ---------------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  echo "No Python virtualenv at: $VENV"
  echo "Create it with Python 3.9 (see README), or set VENV=/path/to/venv"
  exit 1
fi
if [ ! -f "$SIM_DIR/utils.py" ]; then
  echo "Missing $SIM_DIR/utils.py"
  echo "Copy utils.py.example to utils.py in that folder and set your key."
  exit 1
fi
if [ -f "$PIDS" ] && kill -0 "$(head -n1 "$PIDS")" 2>/dev/null; then
  echo "Already running. Use ./start.sh stop first."
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

mkdir -p "$RUN_DIR" "$WEB_DIR/temp_storage"
: > "$WEB_LOG"; : > "$SIM_LOG"; : > "$PIDS"
rm -f "$FIFO"; mkfifo "$FIFO"

WEB_HOST="${WEB_HOST:-127.0.0.1}"
if [ "$WEB_HOST" = "tailscale" ]; then
  WEB_HOST="$(tailscale ip -4 2>/dev/null | head -n1)"
  [ -n "$WEB_HOST" ] || { echo "Could not read the Tailscale IP. Is Tailscale up?"; exit 1; }
fi

FORK_SIM="${FORK_SIM:-base_the_ville_isabella_maria_klaus}"
SIM_NAME="${SIM_NAME:-habitat-$(date +%Y%m%d-%H%M%S)}"

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping both servers..."
  stop_all
  exit 0
}
trap cleanup INT TERM EXIT

# --- 1. Django environment server -------------------------------------------
( cd "$WEB_DIR" && exec python manage.py runserver "$WEB_HOST:$WEB_PORT" ) >> "$WEB_LOG" 2>&1 &
echo $! >> "$PIDS"

# --- 2. reverie simulation server --------------------------------------------
# reverie reads typed answers from stdin. A FIFO held open read/write keeps that
# input from ever hitting end-of-file, so it can run in the background.
exec 3<>"$FIFO"
( cd "$SIM_DIR" && exec python -u reverie.py <&3 ) >> "$SIM_LOG" 2>&1 &
echo $! >> "$PIDS"

# answer the two startup questions
printf '%s\n%s\n' "$FORK_SIM" "$SIM_NAME" >&3

sleep 2
echo "Web (Django):  http://$WEB_HOST:$WEB_PORT/"
echo "reverie:       running in the background (simulation: $SIM_NAME, forked from $FORK_SIM)"
echo "Send commands: ./start.sh send \"run 100\"   (from another terminal, or Ctrl+C then restart)"
echo "Logs:          $WEB_LOG and $SIM_LOG"
echo "Press Ctrl+C to stop both."
echo

tail -n 0 -f "$WEB_LOG" "$SIM_LOG" &
echo $! >> "$PIDS"
wait
