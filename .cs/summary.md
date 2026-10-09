# Task summary — daily Gmail sync and analytics refresh

## Objective

Fetch the user's Gmail once per day on the Fieldwork server using the user's Claude subscription, apply application-email updates to the existing tracking data, and refresh the app's analytics page daily.

## Environment

- Workspace: `/Users/bogdan.gherghina/Documents/jobs-manager`, branch `claude-ranking-app-updates`, HEAD `2a4c169` (`Track application status, details and emails, with stats in the app`). No commit was made for this task.
- The worktree already contained changes from ranking and Claude chat work. This task's additions share `backend/service.py`, `lib/main.dart`, and the README; retain the other uncommitted changes.
- Python service runs on port 8765. Tailnet HTTPS `https://macbook-pro-2.tailaedfae.ts.net` proxies to it. Existing service was restarted with `JOBS_CLAUDE_CHAT=off` preserved.

## Key Discoveries

- The authenticated Claude CLI can load the claude.ai Gmail connector in the scheduled runtime and the correct existing Claude Max account can be verified before each model run.
- The first live model invocation hit the subscription session limit and reported reset at 22:20 Europe/Bucharest on October 9, 2026. A complete live Gmail import has not yet been verified.
- Daily state, configuration and the pre-import backup are private, gitignored backend files. The app's analytics remain available offline.

## Changes Made

- Added `backend/gmail_sync.py` and `scripts/sync_gmail.sh`. The service checks every 60 seconds and runs at most once per 24 hours, catches up after downtime, uses an inter-process lock, and records attempts before model calls to avoid quota retry loops. The first 30-day sweep was scheduled for 22:25 EEST on October 9, then at 24-hour intervals.
- Pins Claude login email and organization, strips inherited API billing credentials, and uses a deny-by-default PreToolUse hook allowing only Gmail search/thread reads, tool discovery and structured output. Mail is treated as untrusted input.
- Requires a complete sweep and verified mailbox, validates the entire batch before applying it, associates evidence conservatively, deduplicates by message ID, preserves manual details and newer status history, and writes atomically with a private backup. It stores no full message bodies.
- `GET /applied` includes Gmail sync status. Added authenticated `GET /gmail-sync` and `POST /gmail-sync`; `scripts/sync_gmail.sh` only requests a run when due.
- The Applied tab refreshes its server copy once daily on app open/resume or while open, caches the fetch time and Gmail status, keeps stale data offline, retries network failures hourly, and still supports pull-to-refresh.
- Documented configuration, privacy, schedule and recovery in `README.md`; added project memory and narrative handoff notes.

## Key Files & Outputs

- `backend/gmail_sync.py` — daily scheduler, locked read-only model call, validation and import.
- `backend/service.py` — service lifecycle, status and sync endpoints; `AppliedStore` email message-ID deduplication.
- `scripts/sync_gmail.sh` — authenticated due-check helper.
- `lib/main.dart`, `lib/stats.dart`, `test/daily_refresh_test.dart` — persisted daily refresh and sync status UI.
- `backend/tests/test_gmail_sync.py` — account pinning, tool guard, scheduling, recovery, deduplication and atomicity tests.
- Private runtime configuration/state: `backend/gmail-sync-config.json`, `backend/gmail-sync-state.json*`.
- Published `artifacts/fieldwork.apk`, build 29859405.

## Outcome

- All 186 backend tests and 38 Flutter tests passed; `flutter analyze` and `git diff --check` were clean.
- Verified `/health`, `/gmail-sync` (enabled; next run 22:25 EEST) and `/app` locally and through Tailscale Serve. The existing application list was unchanged during deployment. The restricted runtime exposed the Gmail connector.
- The first successful import is pending the scheduled run after the Claude usage reset. Check `GET /gmail-sync`; if the connector needs reauthorization, reconnect it in Claude Code and the daily runner will retry.
- The service must stay running and the Mac awake. The app update is available via **Options → App updates**.

## Notes for Future Reference

- Run `./scripts/sync_gmail.sh` to request a due check; it does not bypass the daily quota guard. Use authenticated `GET /gmail-sync` for status.
- To pause the job, set `"enabled": false` in the private sync config; it takes effect without a restart.
- For a bulk import/store change, retain the backup and test against a temporary copy of `applied.json` first.
- No continuation task was requested. No `CLAUDE_CODE_SESSION_ID` was present; no wrapped marker was created. `cs -narrative rotate` was attempted once and skipped because this directory is not inside a CS session.
