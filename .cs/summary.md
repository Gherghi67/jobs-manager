# Session Summary: Fieldwork / jobs-manager

**Date:** 7 November 2026
**Duration:** about 1 h 35 min (14:26–16:01 Europe/Bucharest, one Claude conversation)

## Objective

Four requests, in order:
1. Make the app and website return **hybrid roles in Romania and in Malta**, beside the existing fully remote, Romania-eligible results.
2. Answer "is the Gmail check working?", then, at the user's "lets solve the problem with gmail", unblock it and stop one email from jamming it again.
3. Fix two display bugs the user reported from the website ("Fetching null", and an old Gmail error under the results).
4. Branch out a separate feature session for an in-app LLM that tailors the CV with the resume-tailoring skill, then `/wrap`.

## Environment

- Session checkout `~/.local/share/code-sessions/home/sessions/jobs-manager`, branch `claude-ranking-app-updates` at `909864f`. No commits were made here; the large set of earlier uncommitted work (Gmail IMAP sync, session notes) is still uncommitted, now with this session's changes on top.
- Python service `backend/service.py` on the Mac, reached at `https://macbook-pro-2.tailaedfae.ts.net/` over Tailscale Serve; Flutter client shared by Android and the web.
- LinkedIn and Glassdoor are searched by the jev-ultrafast browser agent in the Chrome profile signed in to LinkedIn. The Gmail sync reads the personal mailbox over IMAP (app password from the keychain) and sorts it with the engine picked in the app (Codex · Personal today).

## Key Discoveries

- **No job source covered Romania or Malta hybrid work before.** Adzuna has no RO or MT market; LinkedIn and Glassdoor only ran "… remote" searches in Romania; the remote boards are remote-only.
- **LinkedIn's Malta geoId is 100961908.** LinkedIn's logged-out guest endpoint (`jobs-guest/jobs/api/seeMoreJobPostings/search?geoId=…`) lists card locations without touching the signed-in account; it's a safe way to check any geoId.
- **Glassdoor lists no jobs in Malta.** Its Malta page (`IN166`) was empty even for "software engineer", while Glassdoor's Romania hybrid search returned 25 roles, so the page reader works.
- **The Gmail check had imported nothing since 22 Oct**, for two reasons in sequence. The service running since 2 Nov started before the app password was available. After today's restart it read the mailbox, but one Micro1 reply ("Application Update – Competitive Data Scientist") had no entry with that company name. The application is saved as Xperteez Technology, the name on the Himalayas listing, and Micro1 hires for it through Dover. The old design dropped the whole batch on one unmatched reply and never advanced its watermark, so every check hit the same email.
- **A search's Gmail line is a snapshot.** The red Micro1 error the user saw after the fix came from the 15:17 search, which ran before the 15:25 fix.
- **branch-out can't find this session under cs.** The `~/.claude-sessions/jobs-manager` link is gone; only the code-sessions profile has the session.

## Changes Made

**Hybrid roles (backend and app)**
- New search option `hybrid` (`romania`, `malta`; both on by default; older app builds that don't send it get both).
- `service.hybrid_place()` decides each role before the remote and eligibility gates. A site's workplace tag decides (LinkedIn's `(Hybrid)`, `(On-site)`, `(Remote)`). Otherwise the title or location must say hybrid (not "hybrid cloud" or "hybrid app"), or the description must describe hybrid work in English or Romanian. Only the location places a role, by country or main towns. Kept roles get eligibility `hybrid-romania` or `hybrid-malta` and sort with the eligible group.
- Extra browser-agent runs:
  - LinkedIn searches "… hybrid" in Malta, then Romania, so the account's last LinkedIn location stays Romania.
  - Glassdoor searches Romania only (`glassdoor.HYBRID_PLACES`).
  - Source statuses carry `place`.
- The AI ranking prompt says hybrid roles there are wanted and Malta's needn't be hireable from Romania.
- App:
  - Romania and Malta chips under "Fully remote only".
  - "Hybrid · Romania" and "Hybrid · Malta" pills.
  - "LinkedIn · hybrid in Malta" in the source list.
  - The header reads "Fully remote + hybrid in Romania, Malta".
  - A Malta role's details leave out the AI's "open to Romania" line.

**Display fix**
- The progress line read "Fetching null" because the run state names its source `source`, not `name`. It moved into a tested `progressLine()` in `lib/models.dart`.

**Gmail sync**
- `gmail_sync.placed()` decides where each email goes, in this order:
  - The application the model named.
  - Within the same company: by thread, then by exact title, then a title-less single entry.
  - For **replies only**, across company names: a thread match, or an earlier email naming the sender about the same role. A confirmation from a new company still starts its own entry.
- Emails that can't be placed are **set aside** with a reason (`left_out` in the state file: headers and classification, up to 50, for 30 days), and the rest imports. Every sweep retries them, so adding the application in the app is enough.
- `merge()` now returns `(added, left_out)`. Validation was split into `clean_event()`.
- The search's Gmail line and the Applied tab name the waiting replies. The "checked in the last 15 minutes" line names them too.

**Deployments:**
- Website rebuilt four times.
- APKs 29900922 (hybrid), 29900954 (progress-line fix) and 29900964 (waiting replies on the Applied tab).
- Service restarted four times, each time with no search, sweep or Claude-page reply running. Process ids 55022 → 56266 → 26934 → 39345.

## Key Files & Outputs

- `backend/service.py`: `HYBRID_PLACES`, `hybrid_place()`, the hybrid path in `rank()`, per-place agent plans, `place` in statuses and progress.
- `backend/linkedin.py`, `backend/glassdoor.py`, `backend/jev.py`: `request(o, place)`, `fetch(..., place)`, `GEO_IDS['malta']`, `HYBRID_PLACES`, `jev.PLACES`.
- `backend/ai_pick.py`: hybrid preferences in the ranking prompt.
- `backend/gmail_sync.py`: `placed()`, `clean_event()`, `waiting()`, `left_out_note()`, set-aside handling in `merge()` and the sweep.
- Tests:
  - `backend/tests/test_service.py`, `test_linkedin.py`, `test_glassdoor.py`, `test_ai_pick.py`, `test_gmail_sync.py`: hybrid rules, plans, cross-name linking, set-aside and retry. 291 backend tests pass.
  - `test/widget_test.dart`, `test/ranking_options_test.dart`, `test/daily_refresh_test.dart`: 68 Flutter tests pass, and `flutter analyze` is clean.
- `lib/models.dart`, `lib/main.dart`, `lib/stats.dart`: chips, labels, `sourceStatusName()`, `progressLine()`, `leftOutNote()`.
- `README.md`: new "Hybrid roles in Romania and Malta" section; Gmail matching and set-aside rules.
- Backups: `backend/applied.json.before-left-out-20261107-152527` and `backend/gmail-sync-state.json.before-left-out-20261107-152527` (gitignored).
- Feature session `jobs-manager@cv-tailor` (code-sessions) on branch `cs/cv-tailor` from `909864f`, with handoff commit `992ad8f` (`.cs/handoffs/2026-11-07-cv-tailor.md`).
- Memory: `project_session_home.md` (new); `project_fieldwork.md` updated (hybrid roles, set-aside replies).

## Outcome

- **Hybrid roles work live:**
  - LinkedIn's Malta search found 25 roles, and 8 passed (Betsson, Twin Harbour, Catena Media and others).
  - LinkedIn's Romania search found 25, and 17 passed.
  - Glassdoor's Romania search found 25, and 11 passed.
  - The user's first full search ran all 13 searches, including LinkedIn Malta 24 and Romania 25.
- **The Gmail sync works again.** A dry run on copies matched the real run exactly: 15 emails imported, 4 set aside, the error cleared, last success 7 Nov 13:25 UTC.
  - Status changes: Xperteez (Micro1) Competitive Data Scientist → interview, Flosum → screening, Powerprozesse and edenity. → rejected.
  - Set aside: SME Careers (interview), DataAnnotation, Curotec, LSEG.
- Twin Harbour's Senior Node.js Developer has a 6 Nov rejection email. The user re-marked it applied in the app today, and the newer manual status wins; the user was told.
- The cv-tailor feature session was created and launched in a terminal tab. Nothing is built there yet.
- Nothing committed. The live service and APK 29900964 run uncommitted code.

## Notes for Future Reference

- The cv-tailor branch starts from `909864f`, so it lacks all uncommitted work in this checkout (hybrid roles, the Gmail IMAP sync, set-aside replies). Commit or merge this checkout's work before relying on it there.
- Run `/branch-out` here with `--launch code-sessions` (see `project_session_home.md`).
- Snag tasks filed: fix the session README's open and branch-out line (#4), put the Gmail sync's state into `/health` (#5), stop an old search's Gmail line from reading as a current failure (#6).
- The user hasn't answered whether they want a "remote in Malta" search too. Remote roles open only to Malta residents are dropped today.
- Four set-aside replies wait for applications. If the user applied to SME Careers, DataAnnotation, Curotec or LSEG, adding the application in the app attaches the email on the next check. Otherwise they age out after 30 days.
