#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SECRETS_SESSION="${JOBS_SECRETS_SESSION:-wap-ags}"
# ags was renamed code-sessions (alias ccs); try the current names first.
SECRETS_CLI=""
for name in code-sessions ccs ags; do
  if command -v "$name" >/dev/null; then SECRETS_CLI=$name; break; fi
done
if [ -z "${ADZUNA_APP_ID:-}" ] && [ -n "$SECRETS_CLI" ]; then
  ADZUNA_APP_ID=$(CS_SECRETS_SESSION="$SECRETS_SESSION" "$SECRETS_CLI" -secrets get ADZUNA_APP_ID 2>/dev/null) || ADZUNA_APP_ID=""
fi
if [ -z "${ADZUNA_APP_KEY:-}" ] && [ -n "$SECRETS_CLI" ]; then
  ADZUNA_APP_KEY=$(CS_SECRETS_SESSION="$SECRETS_SESSION" "$SECRETS_CLI" -secrets get ADZUNA_APP_KEY 2>/dev/null) || ADZUNA_APP_KEY=""
fi
export ADZUNA_APP_ID ADZUNA_APP_KEY
# Keep the Mac awake while the service runs. exec keeps this PID, so caffeinate exits with the service.
if command -v caffeinate >/dev/null; then
  caffeinate -is -w $$ &
fi
exec python3 "$ROOT/backend/service.py" "$@"
