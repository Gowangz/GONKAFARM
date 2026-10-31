#!/usr/bin/env bash
# Jalankan forward gateway PetaniProxy (rotating proxy) utk GONKAFARM.
# Gunakan: ./scripts/start_petani.sh [target] [port]
set -euo pipefail

PETANI_DIR="${PETANI_DIR:-$HOME/PROJECT/FARM/petani-proxy}"
TARGET="${1:-20}"
PORT="${2:-8888}"
LOG="$HOME/PROJECT/FARM/petani-proxy/serve.log"
PIDFILE="$HOME/PROJECT/FARM/petani-proxy/serve.pid"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "PetaniProxy sudah berjalan (pid $(cat "$PIDFILE")) — skip."
  exit 0
fi

echo "Memulai PetaniProxy forward gateway di 127.0.0.1:$PORT target=$TARGET ..."
cd "$PETANI_DIR"
nohup python main.py --serve "$PORT" --target "$TARGET" >"$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "started pid=$(cat "$PIDFILE") — log: $LOG"
sleep 3
echo "--- health check ---"
curl -s http://127.0.0.1:$PORT/api/status || echo "(status belum siap, cek $LOG)"
