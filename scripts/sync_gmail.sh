#!/bin/sh
# Ask the running service to sweep Gmail if its daily run is due.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$ROOT/backend/gmail_sync.py" "$@"
