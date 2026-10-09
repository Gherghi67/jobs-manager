#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SECRETS_SESSION="${JOBS_SECRETS_SESSION:-wap-ags}"
if [ -z "${ADZUNA_APP_ID:-}" ] && command -v ags >/dev/null; then
  ADZUNA_APP_ID=$(CS_SECRETS_SESSION="$SECRETS_SESSION" ags -secrets get ADZUNA_APP_ID 2>/dev/null) || ADZUNA_APP_ID=""
fi
if [ -z "${ADZUNA_APP_KEY:-}" ] && command -v ags >/dev/null; then
  ADZUNA_APP_KEY=$(CS_SECRETS_SESSION="$SECRETS_SESSION" ags -secrets get ADZUNA_APP_KEY 2>/dev/null) || ADZUNA_APP_KEY=""
fi
export ADZUNA_APP_ID ADZUNA_APP_KEY
exec python3 "$ROOT/backend/service.py" "$@"
