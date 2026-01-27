#!/bin/bash
# Restart the GBH dashboard server so it picks up template/code changes.
cd "$(dirname "$0")/.."
pkill -f "uvicorn server:app" 2>/dev/null
sleep 1
./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 &
echo "Server starting at http://localhost:8000 — wait 2s then open in browser (use Cmd+Shift+R to hard refresh)"
