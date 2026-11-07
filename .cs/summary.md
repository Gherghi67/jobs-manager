# Session Summary: Fieldwork / jobs-manager — feature `cv-tailor`

**Date:** 7 November 2026
**Duration:** About 40 minutes, 15:55–16:35 EET, in one conversation in the feature worktree `jobs-manager@cv-tailor` (branch `cs/cv-tailor`).

## Objective

The user asked, through `/branch-out`, for "a llm builtin" in the Fieldwork phone app and website that tailors their CV to a job with the resume-tailoring skill. At the start of the conversation they settled the open scope questions:
- **Entry point:** a "Tailor CV" button on a job (plus a way to paste a posting) that opens a Claude page chat, and a list of tailored CVs.
- **Experience discovery:** the skill's gap questions are answered in that chat from the phone.
- **Output:** the one-page PDF and its `Report.md`. No cover letters or form answers.
- **Engine:** the Claude page's setup (Opus 5.5 at xhigh effort on the Mac's live Claude login, auto mode), not a Claude/Codex selector.

## Environment

- **Fieldwork:** a Flutter client shared by Android and the web, plus a standard-library Python service on the user's Mac, published tailnet-only through Tailscale Serve.
- **Live service:** runs from the base cs session folder `~/.local/share/code-sessions/home/sessions/jobs-manager` (PID 39345, branch `claude-ranking-app-updates`). That checkout holds a lot of uncommitted work: search changes, the Gmail sync rework, models and stats.
- **This feature:** started from the base's committed HEAD (`909864f`).
- **CV sources:** the master CV is `~/Documents/cv-refactor/latex/cv.tex` with `plushcv.cls`. The skill lives at `~/.claude/skills/resume-tailoring/`, and its local `latex-output.md` gives the build and check steps.

## Key Discoveries

- **Three places for tailored CVs.** The handoff named `~/Documents/jobs-manager/cv/tailored`. That folder is an older, separate clone (HEAD `399c0c5`), which the service never reads, and it holds the LSEG CV. The service's own `cv/tailored/` holds only Twin Harbour. The skill's `latex-output.md` names a third place, `~/Documents/cv-refactor/tailored/`. The feature uses the service's `cv/tailored/<Company>/<Role>/`, beside the CV it already serves.
- **Tailoring chats inherit the cs session.** `cv/` sits inside the base session folder, so a Claude Code chat working there loads that folder's `CLAUDE.local.md` (the cs session-notes protocol) and its `autoMemoryDirectory` (the shared memory). The tailoring prompt now tells those chats to ignore session-notes instructions, save no memory entries and write nothing outside the CV folder.
- **The skill works headless through the Claude page.** A live run on a temporary instance showed that `claude -p` in auto mode loads the skill, reads the CV rules and earlier reports, checks the work repository and the company, and stops with a short numbered list of gap questions. A follow-up message builds and checks the PDF. Both turns took about 2–3 minutes on `claude-opus-5-5`.
- **Two Flutter test traps.** A dialog that disposes its `TextEditingController` as soon as `showDialog` returns crashes during the closing animation. `http.Response(String)` in a MockClient encodes latin1, so JSON containing "—" throws, and the test only reports a missing widget.
- **A merge-conflict risk.** `dart format lib/main.dart` would also reflow line 166 (`saved =Map`), which the base's uncommitted work changes. The line was left as it was, so `/finish` stays clean.

## Changes Made

**Service:**
- New `backend/tailor.py`:
  - folder names: short ASCII, words joined by underscores;
  - checks on incoming jobs and pasted postings;
  - posting text wrapped in `<posting>` tags and marked as data, never instructions;
  - tailoring rules appended to the Claude page's phone prompt on every turn;
  - `job.json` in each folder, recording the job and its chat;
  - the list, files and report readers, with path and symlink containment;
  - `adopt`, which links a pasted-posting chat to the first new PDF folder;
  - `start`, which reopens a role's existing chat instead of starting a second run.
- `claude_chat.py`:
  - `create(..., tailor=, title=)`, where tailoring chats must stay inside `cv/tailored/`;
  - an extra system-prompt argument;
  - a `tailor` block in chat summaries (folder id, `pdf`, `report`);
  - `ChatStore.adopt` after each turn.
- `service.py`:
  - `POST /tailor` (403 when `JOBS_CLAUDE_CHAT=off`, 200 for an existing chat, 202 for a new one);
  - `GET /tailored`;
  - `GET /tailored/<Company>/<Role>/cv` and `/report`.

**App:**
- New `lib/tailor.dart`:
  - job fields with the description clipped;
  - start, confirm and posting dialogs;
  - the **Your CVs** sheet with download, report and chat actions;
  - `ReportPage`, a plain Markdown reader;
  - `TailorBar` above a tailoring chat.
- `ClaudePage(chatId:)` shows that bar.
- `main.dart`: **Tailor CV for this job** in a job's details, the CV icon opens **Your CVs**, plus `openClaude([chatId])` and `tailorCv`.

**Docs and tests:**
- A README "Tailor your CV" section with the API, the rules and the live verification. The "Your CV" text was updated.
- 11 new backend tests in `test_tailor.py` and 7 new Flutter tests in `tailor_test.dart`. The CV-download widget test was updated for the sheet.

## Key Files & Outputs

| Commit | What |
|---|---|
| `5839c84` | The feature: `backend/tailor.py`, `backend/tests/test_tailor.py`, `lib/tailor.dart`, `test/tailor_test.dart`, plus changes to `claude_chat.py`, `service.py`, `claude_chat.dart`, `main.dart`, `widget_test.dart` and `README.md` |
| `7d6b7e6` | The session notes (`.cs/README.md`, narrative) |
| `992ad8f` | The branch-out handoff (before this conversation) |

- **Live-check output (scratch, not kept):** the conversation scratchpad's `live/cv/tailored/In_The_Pocket/Nodejs_Back_End_Engineer/`, with the PDF, `cv.tex`, `Report.md`, `Changes.diff`, `extracted.txt` and `preview.png`.

## Outcome

The feature is built, tested and committed on `cs/cv-tailor`. It is not deployed.

**Checks:** 275 backend tests and 72 Flutter tests pass, and `flutter analyze` is clean.

**Live end-to-end check:** it ran on a temporary instance from this worktree, with a scratch CV folder and chats file and no Gmail sync. The job was In The Pocket's Node.js Back-End Engineer listing.
- **Turn 1 (171 s):** Claude asked four gap questions: headline level, a Secrets Manager bullet, auth work, and Terraform or queues. They were deliberately not answered on the user's behalf.
- **Turn 2 (118 s):** after a "test run, add no new claims" reply, it built a one-page PDF whose text extracts cleanly, plus the report. The chat then reported `pdf: true` and `report: true`.
- **API:** the list and download routes returned the folder, its chat and the PDF byte for byte, under the main CV's file name.
- **Containment:** nothing outside the folder changed.

**Not yet done:**
- The app hasn't been tried on a device.
- The live service still runs the base checkout. Landing this needs the base's uncommitted work committed first, then `/finish cv-tailor` in `jobs-manager`, a service restart, and a new APK and web build.

## Notes for Future Reference

- **Proposed tasks:** (1) point the skill's `latex-output.md` (and the Codex `local-cv-setup.md`) output folder at the service's `cv/tailored/`, and decide whether to move LSEG out of `~/Documents/jobs-manager/cv/tailored`; (2) add a shared UTF-8 JSON reply helper for MockClient tests.
- **Downloads:** a tailored PDF keeps the main CV's file name, so saving it replaces Fieldwork's earlier copy of that name in Downloads.
- **Same role twice:** **Tailor CV** reopens that role's chat. After the chat is deleted, a new run builds on the PDF already in the folder.
- **Sidebar task tools:** headless tailoring chats call the agents-sidebar task tools, as all Claude page chats do.
- **Duplicate worktree:** a sibling worktree `jobs-manager@cv-tailoring` (`cs/cv-tailoring`, only notes edited) from 15:20 looks like an earlier branch-out of the same feature. The user may want to remove it with `cs -rm`.
