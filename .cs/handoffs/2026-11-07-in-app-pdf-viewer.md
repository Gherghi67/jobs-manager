---
parent: 7fbec536-2d98-419c-a928-6c36fc3766d4
created: 2026-11-07T16:20:50Z
purpose: Start implementing a PDF viewer directly in the Fieldwork app (Android + website) to view the PDFs that CV tailoring creates
status: consumed
consumed_by: 39ccee76-4dfb-455f-8be5-5cfde0c18601
---

# Handoff: in-app PDF viewer for tailored CVs

## 1. Next Step

User's request, verbatim: "start implementing a pdf viewer directly in the app, to view the pdfs that the tailoring creates".

Today, a tailored PDF can only be **downloaded**: on Android it is saved to Downloads and a SnackBar "Open" hands it to another app; on the website it starts a browser download. The goal is to show it inside the app instead.

Do this, in order:

1. Workspace: `/Users/bogdan.gherghina/.local/share/code-sessions/home/sessions/jobs-manager`, branch `claude-ranking-app-updates`. You start with uncommitted work (listed in Current Work), plus this handoff and the narrative, also uncommitted. Don't commit or set any of it aside without asking the user. A ChatGPT/Codex agent sometimes edits the same tree (memory `project_concurrent_agents.md`), so check `git status` for files you didn't touch before editing.
2. Read the current download paths (all `read in source:` this conversation):
   - `lib/tailor.dart:49`: `tailoredPath(id, file)` builds `/tailored/<Company>/<Role>/<file>`. The PDF is `file = 'cv'`.
   - `lib/tailor.dart:150-185`: `downloadTailored(api, id, company, notify)` calls `api.file(tailoredPath(id, 'cv'))`, then `Downloads.save(...)`.
   - `lib/tailor.dart:~266-300`: `CvSheet.row(cv)` (the top-bar CV button's sheet). Tapping a row with `pdf == true` calls `widget.download(cv)`; its menu has "Download PDF", "Read report" and the chat.
   - `lib/tailor.dart:~512-534`: the tailoring chat's header uses `tailor['pdf'] == true` ("ready") and has a `download` callback.
   - `lib/main.dart:735-745` `downloadCv()` (main CV via `api.file('/cv')`), `lib/main.dart:870` `openCv(uri)` → `Downloads.open`.
   - `lib/api.dart:86`: `Future<({Uint8List bytes, String? name})> file(String path)`, an authenticated GET returning bytes.
   - `lib/downloads_native.dart` / `lib/downloads_web.dart`: the `Downloads` class with platform-specific save/open.
   - Service: `backend/service.py` `def tailored(self, path)`: `GET /tailored` returns `{cvs: [...]}`; `GET /tailored/<Company>/<Role>/cv` sends the PDF as `application/pdf` with `Content-Disposition: attachment`; `GET /tailored/<Company>/<Role>/report` returns `{text}`. All need `Authorization: Bearer <token>`.
3. Choose the viewer. Decide this before writing code, and ask the user only if a real trade-off appears:
   - The app is Flutter 3.47.4 (`measured: flutter --version`) with only `web`, `http`, `shared_preferences`, `url_launcher` and `image_picker` as dependencies (`read in source: pubspec.yaml`). It must work on **Android and the website** (one shared client; memory `project_fieldwork.md`).
   - The bytes come from the authenticated `api.file`, so the viewer must take **bytes**, not a URL: the service needs the Bearer token, and the browser can't send it from an `<iframe src>`.
   - Candidates to evaluate (`assumed:`, not checked this conversation): `pdfrx` (PDFium; Android, iOS, desktop and web via WASM, opens from bytes with `PdfViewer.data`), `syncfusion_flutter_pdfviewer` (commercial licence: likely a reason to reject), `pdfx`. On the web, an alternative is a Blob URL plus an `<iframe>`/`HtmlElementView` using the browser's own viewer. Check each package's current version and web support on pub.dev before choosing, and keep `flutter build web --release --no-web-resources-cdn` working: `scripts/build_web.sh` builds without the CDN, and the service serves only files from `build/web` (README).
   - A tailored CV is one A4 page, so a simple zoomable single-page view is enough. Keep "Download PDF" / Save as a secondary action.
4. Wire it in. Tapping a built row in `CvSheet` (and the chat header's ready state) opens the viewer instead of downloading; the menu keeps "Download PDF". The main CV (`/cv`) can use the same viewer.
5. Tests: add widget tests next to `test/tailor_test.dart` (it already fakes the API). Run `flutter analyze`, `flutter test`, and `python3 -m unittest discover -s backend/tests` if the service changes. Expected baseline: 75 Flutter tests and 307 backend tests pass (`measured` this conversation).
6. Deploy only when done and green, and only after checking that nothing is running:
   - Build: `./scripts/build_web.sh`, then `./scripts/build_apk.sh` (publishes `artifacts/fieldwork.apk` + `fieldwork.json` for the in-app update).
   - Restart only if the service changed. Restarting kills a running search or Claude reply, so first check `curl -s -H "Authorization: Bearer $(cat backend/.access-token)" http://127.0.0.1:8765/search/latest` (`running` must be null) and `/claude/chats` (no chat with `running: true`).
   - Then stop the PID from `pgrep -f "jobs-manager/backend/service.py"` and start it with `nohup ./scripts/serve.sh >> backend/service.log 2>&1 < /dev/null & disown`. This needed the sandbox disabled, because the service must reach the keychain and the network.
   - Tell the user to reload the browser tab (Cmd+R): an open Flutter tab keeps the old app until it is reloaded. The website has no service worker and is served `Cache-Control: no-store`.

## 2. Settled and rejected

- Push target is the PUBLIC repo github.com/Gherghi67/jobs-manager, `main` | user picked "Public Gherghi67/jobs-manager" | bogdan-gherghina is the work gh login (eRepublik-Labs org); Gherghi67 is personal.
- Include `.cs/` session notes in commits and pushes | user picked "Include .cs/ notes", and later "go push" pushed the notes | older note versions were already in the history anyway.
- Push without switching the active gh account | Claude | one-off credential helper with `gh auth token --user Gherghi67` (memory `reference_github_remote.md`).
- A recruiter's email address in the narrative was redacted before the first push | Claude | a third party's contact details in a public repo.
- History was not rewritten to scrub the user's own Gmail address or the tailnet hostname | Claude, user consented to public with the mailbox and tailnet warning | rewriting would break cs branches and worktrees.
- `/finish cv-tailor`: commit base notes locally to unblock | user picked "Commit them locally, then finish (Recommended)".
- Commit the feature worktree's notes and merge the base into `cs/cv-tailor` | user: "go commit them" | overrides the default rule against committing another session's records.
- Merge conflicts in `.cs/README.md`, `project_fieldwork.md` and `summary.md` were resolved by keeping both sides | Claude | the summary carries the feature's wrap as its own section.
- The running Claude-chat cap is removed entirely | user: "makeit max_running indefinetely" | only the subscription's usage limits cap parallel chats now.
- Tailored CVs are copied (not moved) to `~/Documents/jobs-manager/cv/tailored/<Company>/<Role>/` | Claude, after user asked "make the server store the final cvs in the tailored folder for every company" and later "move the cvs of the last three chats" | moving breaks the app's list and downloads, and moving a chat's cwd breaks Claude `--resume` (sessions are stored per project folder).
- An export copy is replaced only by a newer AND different file | Claude | a file the user edits in Documents is never overwritten by an older build.
- Restarts wait for idle (no search, no chat replying) in a background loop instead of killing replies | Claude | a restart kills a running Claude reply.
- Flaky `test_service.StopTests.test_setting_it_interrupts_the_child_process_like_ctrl_c` was left unfixed | Claude | it passes alone and in the full suite and fails only under parallel load.

## 3. Conversation-only facts

IDS
- measured: `origin` = https://github.com/Gherghi67/jobs-manager (public), `origin/main` = `585a2a6`, the same as local HEAD of `claude-ranking-app-updates`.
- measured: commits this conversation: `0502116` (hybrid roles + Gmail IMAP + notes), `242889c` and `7049263` (notes), `408aa53` (cv-tailor's notes, in its worktree), `beb2a28` (base merged into `cs/cv-tailor`), `0f20e65` and `a1d9631` (cv-tailor integrates), `585a2a6` (notes). Local `main` is still `4eb4e1d`.
- measured: `cs/cv-tailor` was retired (`retired cv-tailor beb2a28`); 12 ignored build files went to the Trash.
- measured: service PID now `47841` (started 17:49:48 EET); earlier PIDs 39345 → 72157 → 20615 → 47841.
- measured: APK build `29901063` published (`artifacts/fieldwork.json` `version_code`).
- measured: tailoring chats: "Tailor CV · n8n — Senior Product Engineer (TS/NodeJS/Vue)", "Tailor CV · Wiley — Senior JavaScript Engineer", "Tailor CV · In The Pocket — Node.js Back-End Engineer". Folders: `cv/tailored/n8n/Senior_Product_Engineer_TS_NodeJS_Vue`, `cv/tailored/Wiley/Senior_JavaScript_Engineer`, `cv/tailored/In_The_Pocket/Nodejs_Back_End_Engineer`.
- read in source: Acrobat is at `/Applications/Adobe Acrobat DC/Adobe Acrobat.app` (`open -a` with that path worked, sandbox disabled).

READINGS
- measured: 307 backend tests OK (`python3 -m unittest discover -s backend/tests`, ~9 s); 75 Flutter tests passed; `flutter analyze` "No issues found!" (before the backend-only changes).
- measured: `/health` → `{"status": "ok", "adzuna_configured": true, "claude_available": true, "claude_chat": true, "linkedin_available": true, "glassdoor_available": true}`; the tailnet URL returns 200.
- measured: Documents copies, byte-identical to the chat's own: n8n PDF 43368 B + Report.md 12510 B; In The Pocket PDF 42816 B + Report.md 9904 B; Wiley PDF 43022 B + Report.md 10065 B (turn finished 17:56:25, copied automatically by the turn-end export).
- measured: the served `main.dart.js` contains "Tailor CV for this job" (2 matches) on both 127.0.0.1:8765 and the tailnet URL, with `Cache-Control: no-store`; `/flutter_service_worker.js` returns 401 (not served).

ERRORS
- measured: `cs jobs-manager -integrate-feature ...` → "Error: Base session has uncommitted changes; commit them in ... first". Cleared by committing the base notes.
- measured: `cs jobs-manager -retire-feature cv-tailor 7d6b7e6...` → "Error: Worktree has uncommitted changes; commit them in .../jobs-manager@cv-tailor first (cs never commits for you)".
- measured: merging the base INTO the feature ran `.cs/memory/MEMORY.md merge=ours` on the feature side and silently dropped the base's newer index lines; rebuilt by hand.
- measured: `StopTests...ctrl_c` → "AssertionError: 10.004574332851917 not less than 5" while `flutter test` ran in parallel; it passed 3/3 alone.
- measured: `security find-generic-password -s fieldwork-gmail -w` → "The specified item could not be found in the keychain." (user's shell). The Gmail password lives in another item (`imap.gmail.com` or `invoice-script-smtp`).
- measured: reading the keychain with the sandbox disabled was denied by the auto-mode classifier.

USER
- user: "commit everything that is stable and push to my personal github on the main branch"
- user: "is any key there?" / "and there is no claude/codex key there, right/". Answer: no credential found (literal-value and pattern scans, all 29 commits at the time).
- user: "where is the tailor button here?" and then "there is not". Answer: the deploy was missing, then the tab hadn't been reloaded.
- user: "can it open many tailoring sessions in parallel?" then "makeit max_running indefinetely"
- user: "can you also make the server store the final cvs in the tailored folder for every company?"
- user: "move the cvs of the last three chats in the corresponding folder (the chats that came from the app)"
- user: "open the first two in acrobat" (done)
- user interrupted `/wrap` and ran `/rotate and start implementing a pdf viewer directly in the app, to view the pdfs that the tailoring creates`

UNVERIFIED
- assumed: the PDF viewer candidates and their web support listed in Next Step; nothing about them was checked this conversation.
- assumed: the Wiley chat's 17:44 turn ended with questions (so it was not running at the 17:45 restart), not cut off by the restart. It later finished normally and produced the PDF.

## 4. Primary Request and Intent

Build an in-app PDF viewer so the PDFs that CV tailoring produces (`GET /tailored/<Company>/<Role>/cv`) open inside the Fieldwork app on Android and the website, instead of only downloading. Start the implementation; don't just plan it.

## 5. Key Technical Concepts

- One Flutter client (Android + web) and a Python service (`backend/service.py`) on the Mac, reached over Tailscale. Every API call carries the Bearer token (`lib/api.dart`).
- Tailoring: `backend/tailor.py` keeps one folder per job under the session's `cv/tailored/`, each with a Claude page chat (`backend/claude_chat.py`, Opus 5.5 xhigh, auto mode).
- New today: `tailor.export()` / `export_all()` copy each finished PDF (under the main CV's name) and `Report.md` to `JOBS_TAILORED_EXPORT_DIR` (set in `scripts/serve.sh` to `~/Documents/jobs-manager/cv/tailored`), at turn end and at service start.
- No cap on concurrent Claude chats any more (`MAX_RUNNING` removed).

## 6. Files and Code Sections

- `lib/tailor.dart`: `tailoredPath`, `downloadTailored`, `CvSheet` (row tap → download), the chat header's ready state. This is where the viewer hooks in.
- `lib/downloads_native.dart`, `lib/downloads_web.dart`: platform save/open; the conditional-import pattern to copy for a web/native viewer split.
- `lib/api.dart:86`: `file(path)` → `({Uint8List bytes, String? name})`.
- `test/tailor_test.dart`: existing tailoring widget tests with a fake API, to extend.
- `backend/service.py` `tailored()`: the PDF is served with `Content-Disposition: attachment`. That's fine for a bytes-based viewer; change it to `inline` only if a URL-based web viewer is chosen.

## 7. Problem Solving

- The missing Tailor button had two causes: no rebuild after the merge (fixed with build + restart), then a browser tab running the old app (fixed by a reload).
- An unmatched keychain item name and an empty `git grep -F ""` pattern looked like a leak; guard empty patterns.
- The cs merge rules: `MEMORY.md merge=ours` bites when the base is merged into a feature; the narrative and timeline use union.

## 8. Pending Tasks

Native task list, all inherited and still pending (none touched this conversation):
- #1 Add a guard test for the update installer's intent safety
- #2 Add CV build guards in cv-refactor build.sh
- #3 Stop backend tests from launching the real jev agents
- #4 Fix the session README's open and branch-out instructions
- #5 Report the Gmail sync's state in /health
- #6 Stop a search's old Gmail line from reading as a current failure

Also open:
- `/wrap` was interrupted before any pass ran (only `sweep/SKILL.md` was read; no memory, summary, rotation or task-archive pass happened). `.cs/summary.md` is the merged version from the cv-tailor finish, not a fresh wrap. Offer `/wrap` again at a stopping point.
- The flaky StopTests timing test has a fixed 0.5 s wait.
- The uncommitted backend changes (chat cap removal + CV export) are live on the service but not committed or pushed. Ask the user before committing; earlier they asked for commits and pushes explicitly ("commit everything that is stable…", "now push", "go push").

## 9. Current Work

- Uncommitted (`git status`): `README.md`, `backend/claude_chat.py`, `backend/service.py`, `backend/tailor.py`, `backend/tests/test_claude_chat.py`, `backend/tests/test_tailor.py`, `scripts/serve.sh`, plus `.cs/memory/narrative.bogdan-gherghina-erepubliklabs-com.md` and this handoff. They hold the removed chat cap (new test `test_any_number_of_chats_can_answer_at_once`) and the Documents export (4 new `ExportTests`). Both are deployed on service PID 47841.
- The web build and APK 29901063 match HEAD 585a2a6's Dart code; there were no Dart changes after that.
- Nothing is running in the background from this conversation. Context was summarised from memory of this one conversation, not compacted; nothing was cut short.

## Successor report

- `/health` without the token now returns 401; with `Authorization: Bearer` it returns the JSON the handoff quotes. Found by curling it bare during the deploy check.
- README anchor: the website section is `## Website version` (`#website-version`), not `#website`. Found by grepping headings after writing a link.
- Building a test APK without `--build-number` gives versionCode 1, which the emulator refuses as a downgrade. The handoff's build step uses `build_apk.sh`, which sets the number, so this only matters for an unpublished test build. Found from `adb install`'s INSTALL_FAILED_VERSION_DOWNGRADE.
- Otherwise the handoff was accurate: file locations, line ranges, the bytes-not-URL constraint and the test baselines (75 Flutter) all matched.
