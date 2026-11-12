#!/bin/bash
source "$(dirname "$0")/walk-env.sh"
cd "$WTC/frontend" || exit 1
export FIONA_BACKEND_ORIGIN=http://localhost:8063 NEXT_TELEMETRY_DISABLED=1
exec node_modules/.bin/next dev -H 127.0.0.1 -p 3063
