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
# The Gmail sync reads the personal mailbox over IMAP with a Google app password from the login keychain:
# the password item named fieldwork-gmail (JOBS_GMAIL_KEYCHAIN_ITEM), or else an imap.gmail.com internet password,
# or else invoice-script-smtp, the same mailbox's app password that the invoice script sends mail with.
if [ -z "${JOBS_GMAIL_APP_PASSWORD:-}" ] && command -v security >/dev/null; then
  JOBS_GMAIL_APP_PASSWORD=$(security find-generic-password -s "${JOBS_GMAIL_KEYCHAIN_ITEM:-fieldwork-gmail}" -w 2>/dev/null) ||
    JOBS_GMAIL_APP_PASSWORD=$(security find-internet-password -s imap.gmail.com -w 2>/dev/null) ||
    JOBS_GMAIL_APP_PASSWORD=$(security find-generic-password -s invoice-script-smtp -w 2>/dev/null) || JOBS_GMAIL_APP_PASSWORD=""
fi
export ADZUNA_APP_ID ADZUNA_APP_KEY JOBS_GMAIL_APP_PASSWORD
# Keep the Mac awake while the service runs. exec keeps this PID, so caffeinate exits with the service.
if command -v caffeinate >/dev/null; then
  env -u JOBS_GMAIL_APP_PASSWORD caffeinate -is -w $$ &
fi
exec python3 "$ROOT/backend/service.py" "$@"
