# Session Summary: Fieldwork / jobs-manager

**Date:** 2026-10-09 to 2026-10-12
**Duration:** About 13 hours of work over nine conversations. On 9 Oct, five conversations ran 15:08–20:58. On 10 Oct, 14:58–18:50. On 11 Oct, a ten-minute fix at 17:44. On 12 Oct, 08:54–10:25, 14:46–15:30 and 15:30–15:50. All times are EEST.

## Objective

Turn Fieldwork into something the user relies on every day from their phone. Fieldwork is the user's personal Android jobs app, backed by a Python search service on their Mac. Requests over the four days:

- **9 Oct:** test the app on an emulator and fix what turned up. Reach the service without a USB cable, and keep the Mac awake while it serves. Rank jobs with the Claude subscription, and update the app from a button. Record applications on the server, imported from Gmail, so searches never show those jobs again. Download the CV to the phone. Track each application's status and emails, with statistics. Talk to Claude Code on the Mac from a page in the app.
- **10 Oct:** fix the Applied page's "Gmail sync needs attention" error and add a green or red mark for refresh status. Add photo uploads to the Claude page and run it on Opus 5.5 at xhigh effort. Draft a Supabase application answer.
- **11 Oct:** explain why the tailnet URL returned 502.
- **12 Oct:** keep dismissed roles out of Claude's ranking. Keep a job search going while the app is in the background. Improve the CV from the application history, as a dry run first. Then have a grumpy reviewer check the draft, fix what the review got right, and make the result the real CV.

## Environment

- **Mac (`macbook-pro-2`):** runs the service through `scripts/serve.sh` on `127.0.0.1:8765`, published tailnet-only at `https://macbook-pro-2.tailaedfae.ts.net`. Flutter 3.47.4, Claude Code 2.1.295 and Tectonic for the CV. There is no LaunchAgent, so a reboot stops the service. The Agents sidebar switches the Mac's live Claude login between Personal and Work (ERPK).
- **Devices:** an Android 14 emulator for testing and the user's Pixel 10 Pro on the same tailnet.
- **Mail:** applications arrive in the user's personal Gmail, read through the claude.ai connector. In the 12 Oct conversations the connector was on another mailbox.
- **Repository:** local git with no remote. All work is on branch `claude-ranking-app-updates`, not merged into `main`.
- **CV source:** `~/Documents/cv-refactor/latex/cv.tex` on `plushcv.cls`. cv-refactor is another cs session's repo. `cv/` here holds the PDF the app downloads.
- **Other agents:** a ChatGPT (Codex) agent edits the same working tree. Its browser version of the app (`web/`, `lib/adaptive.dart`, the `*_io`/`*_stub` files) is still uncommitted.

## Key Discoveries

- **Ranking and the Claude page need opposite Claude Code setups.** Ranking runs isolated: an empty folder, no tools, no MCP and no user settings. `--bare` can't be used, because it accepts only API keys. The Claude page needs the user's full setup. `claude -p --permission-mode auto --permission-prompts none` loads settings, hooks and connectors, keeps the auto-mode classifier, and refuses anything that would wait on a prompt. The classifier blocked a `bypassPermissions` probe, which settled the design.
- **Credentials in this shell:** the secrets CLI `ags` became `code-sessions`, which had quietly left Adzuna without keys. The shell also exports an invalid `ANTHROPIC_API_KEY`, so every Claude call the service makes strips it.
- **Why the Gmail sync failed (10 Oct):** the 22:25 sweep on 9 Oct ran while the live login was Work, and the refusal used up the day's attempt. A login refusal now retries every ten minutes.
- **Why the URL returned 502 (11 Oct):** the Mac had rebooted. Tailscale Serve kept proxying to a dead port, because nothing restarts the service. Restarting it also fired the overdue Gmail sweep at once, which is why jobs appeared as applied right after.
- **Dismissals never reached the server (12 Oct):** dismissals lived only on the phone, so Claude's 40-slot shortlist was spent on roles the app then hid.
- **Background search died on the first failed poll (12 Oct):** Android freezes or cuts the network of a backgrounded app, so the next poll threw and the search ended. The run id wasn't stored, so nothing could resume it.
- **The CV PDF partly failed to parse (12 Oct):** in pypdf and `pdftotext -raw`, every Source Sans Pro run lost its word spaces ("BogdanGherghina", "April2022"). pypdf missed 12 of 19 key phrases, including every date. `WordSpace=1.3` on those fonts fixes it, and `\XeTeXinterwordspaceshaping` segfaults Tectonic. A single `\defaultfontfeatures[…]{WordSpace=1.3}` line does the same job, but only with the font-name macros expanded first. Unexpanded, it silently does nothing.
- **What the application history says (12 Oct):** 22 applications from 2 to 12 Oct had produced 3 rejections, no screens and 19 silences. That's too few for outcome statistics. The 16 postings a subagent found told more. About 8 applications failed on things no CV fixes: Poland-only, on-site in SF, accounting credentials, Russian, a closed listing, a duplicate. React was the gap that came up most, required by 6 postings.
- **The review was mostly right about the CV, not about the history (12 Oct).** Re-running its git counts in the work repo showed the user's own feature commits on Secrets Manager (`8273c75ddf`, May 2026), where the review had seen only tests. Matching commits on `--author=bogdan` also catches another Bogdan in that repo. SES had only a test commit and S3 none, so SES left the CV. Two review fixes didn't fit the one-page layout: moving the location into the contact line (91 pt free, about 162 pt needed) and restoring the faculty line (it wraps to two lines, and dropping Git and pm2 frees none).
- **No GitHub remote, so `/fix-review` has no PR to read.** Local reviews come from `/roast-local` as a `REVIEW.md` in its worktree. The first `/fix-review` run stopped at its preflight for that reason.
- **A second agent shares the tree.** None of its changes show until `git status` and file times are compared with your own edits. To commit only your own hunks, build each file from HEAD plus your edits, stage it with `git hash-object -w` and `git update-index`, and test that snapshot alone.

## Changes Made

**9 Oct: a working app on the phone (committed `26e5130` to `0a8dbae`)**
- Fixed four emulator display bugs. `serve.sh` holds `caffeinate`, and Tailscale Serve publishes the service.
- **Claude ranking:** Claude ranks the top 40 keyword matches with cached verdicts and a keyword fallback. The other agent added Claude or Codex with a Personal or Work subscription, never API-key billing.
- **In-app updates** through `scripts/build_apk.sh` and a private install receiver, which replaced a design that failed a security review.
- **Applied jobs:** stored in `backend/applied.json` and dropped before ranking. Companies imported from Gmail use match modes (Proxify `badge`, Jobgether `role`). Application tracking adds status history, notes, follow-up dates, email trails and statistics. The other agent added a daily read-only Gmail sync.
- **CV download** to the phone's Downloads.
- **Claude page:** a chat with Claude Code on the Mac in auto mode. The `engine-dropdown` feature (a "Returned by" filter) also landed.

**10 Oct (committed `eb0b059`, then uncommitted)**
- A wrong Claude login now retries the Gmail sync every ten minutes. The Applied tab shows a green, red or grey refresh mark with the refresh time (`eb0b059`).
- The Claude page accepts photos (up to 5, sniffed and stored at 0600) and runs `claude-opus-5-5` at xhigh effort. Uncommitted, in build 29860692.

**11 Oct:** restarted the service after the reboot. No code changed.

**12 Oct, app (uncommitted)**
- The app sends the latest 2,000 dismissed ids with each search. The service ranks dismissed roles last and keeps them out of Claude's shortlist (build 29863129).
- A background search now waits while the app is hidden, then resumes on return or relaunch from a stored run id. It gives up after three misses while on screen (build 29863142).

**12 Oct, CV (applied to cv-refactor, not committed)**
- **Draft B** (dry run) combined the PDF parsing fix with facts the user confirmed: the "Senior Backend Engineer" headline, 15,000 players, on-call, AWS, PR reviews, and "Remote from Bucharest (EET)". It dropped the faculty line to stay on one page.
- **Review:** a `/roast-local` grumpy review (Fable 5.1) of Draft B passed it with concerns. Each finding was checked against the draft. Three needed the user's answer: list only S3 and Secrets Manager, write "15,000 daily active players", and call on-call a shared rotation.
- **Draft C** fixed the rest, one build and probe run per change:
  - the seven pasted `WordSpace` options became one font-defaults line;
  - "and AWS" left the stack line, so it no longer reads as hosting;
  - the root-cause wording went back to the original;
  - the pull-request clause moved out of the AI list;
  - "and rewards" came back.

  It is one page, with the same layout as Draft B, and all 28 probe phrases extract in pypdf, pdfminer and `pdftotext -raw`. The review's location and faculty suggestions, the headline and the summary wording were declined with reasons.
- **Applied.** The 9 Oct CV is saved as `cv.v11.*` and `plushcv.v11.cls`. Draft C is now `latex/cv.tex` and `plushcv.cls`, rebuilt with `cv.png`. The PDF moved into `cv/`, so the app's download serves it without a restart. `Bogdan-Gherghina-CV.txt` was hand-edited to match.

## Key Files & Outputs

| Commit | What |
|---|---|
| `eb0b059` | Gmail login retry and the refresh mark (10 Oct) |
| `0a8dbae`, `0b44a03` | README: each feature keeps its checks in its own section |
| `568e7c8` | `engine-dropdown` merged (`19f9589`) |
| `af0319c` | The other agent's ranking subscriptions, Gmail sync and daily refresh |
| `dd4e335`, `fc3d6b4`, `7f8704a` | The Claude page |
| `2a4c169` | Application tracking and statistics |
| `3b4d519` | CV download |
| `bb31a07`, `a18d803` | Applied jobs and company match modes |
| `754bb95` | Claude ranking, in-app updates, untethered setup |
| `26e5130`, `4eb4e1d` | The app and its first retest (merged into `main`) |

- **Uncommitted app work:**
  - photos and the model setting: `backend/claude_chat.py`, `backend/service.py`, `lib/claude_chat.dart`;
  - dismissed roles: `lib/models.dart`, `service.py`;
  - background search: `lib/api.dart`, `lib/main.dart`, `test/background_search_test.dart`;
  - plus the other agent's browser version.
- **CV, live:**
  - `~/Documents/cv-refactor/latex/cv.tex`, `plushcv.cls`, `cv.pdf` and `cv.png`;
  - `~/Documents/cv-refactor/Bogdan-Gherghina-CV.txt`;
  - `cv/Bogdan-Gherghina-CV.pdf` here.
- **CV, previous version:** `latex/cv.v11.tex/.pdf/.txt` and `plushcv.v11.cls`.
- **Review snapshot:** `~/.claude/roast-worktrees/jobs-manager/claude-ranking-app-updates-20261012-151715` (branch `roast/claude-ranking-app-updates-20261012-151715`), with the findings in its `REVIEW.md`.
- **Memory updated 12 Oct:**
  - `user_work_facts.md`: daily active players, shared rotation, S3 and Secrets Manager only;
  - `project_cv_pdf_text.md`: the one-line fix, now applied;
  - `project_fieldwork.md`: the steps for applying a CV change, and no remote;
  - also `user_no_react.md`, `feedback_cv_no_fieldwork.md`, and the wrong-mailbox note in `reference_gmail_connector.md`.
- **Kept only on the Mac (gitignored):**
  - `backend/applied.json` (22 entries), `chats.json`, `chat-images/`, `profile.md`;
  - the Gmail sync config and state;
  - `cv/` and `artifacts/fieldwork.apk`.

## Outcome

The app is in daily use. `/app` offers build 29863142, which carries everything up to the background search, including the other agent's uncommitted browser work. The new CV is live: the phone's CV button downloads it, and cv-refactor builds it. It's one page, and the text-extraction defect is gone.

Not done:
- the 10–12 Oct app changes are uncommitted;
- the branch isn't merged or pushed;
- cv-refactor's CV changes aren't committed there, because that repo has other uncommitted work;
- the `engine-dropdown` worktree isn't retired, because its own session records are uncommitted;
- background search and photos haven't been tried on a device;
- the review worktree is still on disk.

## Notes for Future Reference

- **Changing the CV again:** follow the steps in `project_fieldwork.md`:
  1. save the current files as v12;
  2. copy in `cv.tex` and `plushcv.cls` together and run `latex/build.sh`;
  3. regenerate `cv.png`;
  4. `mv` the PDF into `cv/`;
  5. hand-edit the `.txt`.

  Check text extraction (name and dates), not only the page count. Keep Fieldwork, agent-harness and ags off the CV, never claim React, and never add SES, EC2 or CCU. Task #2 would make `build.sh` enforce these rules.
- **Review cleanup:** `git worktree remove ~/.claude/roast-worktrees/jobs-manager/claude-ranking-app-updates-20261012-151715 && git branch -D roast/claude-ranking-app-updates-20261012-151715`. The review covered only the CV; the code on the branch hasn't been reviewed.
- **After a reboot:** start the service with `nohup scripts/serve.sh >> backend/service.log 2>&1 < /dev/null &`. A LaunchAgent was offered and not built.
- **Restarting from a Claude page reply** kills that reply. Use a detached script that waits for the reply's `claude` process to exit.
- **Gmail:** the sync follows the Mac's live login and retries while Work is active. If the connector here answers "not found" for known thread ids, it's on the wrong mailbox.
- **Another agent works here.** Compare `git status` with your own edits before committing, restarting or building, and commit its work only when the user asks.
- **"Acrobat Reader"** means the installed Adobe Acrobat app in `/Applications/Adobe Acrobat DC`. Open drafts there as separate copies.
- **Leftovers:**
  - remove the `/fieldwork` Tailscale path and its port-8790 server;
  - task #1 (an installer guard test) and task #2 (CV build guards) are open;
  - an earlier copy of the access token was emailed, so consider rotating it.
