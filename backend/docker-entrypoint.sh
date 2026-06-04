#!/bin/sh
set -eu

runtime_dir="${RUNTIME_STORE_DIR:-/app/.runtime}"

mkdir -p "$runtime_dir"
chown -R appuser:appuser "$runtime_dir"

command="${*:-uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1}"

exec su -s /bin/sh appuser -c "exec $command"