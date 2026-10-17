#!/bin/bash
# start (or restart) the sandbox server in the background
cd "$(dirname "$0")/.."
if [ -f var/server.pid ] && kill -0 "$(cat var/server.pid)" 2>/dev/null; then kill "$(cat var/server.pid)"; sleep 1; fi
nohup .venv/bin/uvicorn company.app:app --port "${PORT:-8000}" --log-level warning > var/server.log 2>&1 &
echo $! > var/server.pid
for i in $(seq 1 30); do curl -sf http://127.0.0.1:${PORT:-8000}/admin/api/health >/dev/null && echo "sandbox up (pid $(cat var/server.pid))" && exit 0; sleep 0.5; done
echo "sandbox failed to start"; tail -5 var/server.log; exit 1
