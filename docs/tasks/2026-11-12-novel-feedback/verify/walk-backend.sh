#!/bin/bash
source "$(dirname "$0")/walk-env.sh"
cd "$WTC/backend" || exit 1
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8063 --env-file "$D/empty.env"
