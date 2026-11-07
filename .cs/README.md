---
status: active
created: 2026-10-09
tags: []
aliases: ["jobs-manager"]
---
# Fieldwork / jobs-manager

Local handoff records for the Android jobs-manager project, created by the October 9, 2026 wrap.

Adopted as CS session `jobs-manager` on October 9, 2026. The session link at `~/.claude-sessions/jobs-manager` points to this folder. Open it with `cs jobs-manager`.

Git is initialized on `main`; CS committed its adoption metadata. The original ignore rules still exclude credentials, local session state, and generated artifacts.

## Outcome

October 9, 2026 (first cs conversation): an emulator test found four display problems, which were fixed and tested. The app was committed (`26e5130`) and retested from a clean install with all nine sources live, and the README retest note was committed (`4eb4e1d`). Both commits were merged into `main` by fast-forward; nothing was pushed (no remote).


October 9, 2026 (second cs conversation): set up Tailscale Serve so the phone can reach the service without a cable. `serve.sh` now keeps the Mac awake and finds the renamed secrets CLI. Added Claude ranking on the user's subscription, and in-app updates served by the service, including a fix for the security review's intent-redirection finding. Verified live and on the emulator, then committed as `754bb95` on branch `claude-ranking-app-updates` (not merged, not pushed). The real phone still needs one manual install of build 29859249.

October 9, 2026 (third cs conversation): added Applied jobs. They are stored on the service (`backend/applied.json`) and left out of every search before Claude ranks. The app has an Applied tab and a mark/unmark check. Imported 15 companies from application emails in the personal Gmail (Oct 2–9). Added per-company match modes, with Proxify set to badge and Jobgether to role-only. Moved the emailed access token to Gmail Trash. Verified live and on the emulator, published build 29859296, and committed as `bb31a07` and `a18d803` on `claude-ranking-app-updates` (not merged, not pushed).

October 9, 2026 (fourth cs conversation): moved the CV PDF from cv-refactor into `cv/` (gitignored). Added `GET /cv` and a top-bar button that saves the PDF to the phone's Downloads and opens it. Verified on the emulator and published as build 29859312. Committed as `3b4d519`.

October 9, 2026 (fourth conversation, continued): applied entries now keep a status with dated history, job details, notes, a follow-up date and an email trail, and the Applied tab shows statistics. Statuses were filled in from the personal Gmail: Voodoo and Modash rejected, plus TeamQuest added (16 applications). Published build 29859344. Committed as `2a4c169` on `claude-ranking-app-updates` (not merged, not pushed). Wrapped at 18:50 EEST.

October 9, 2026 (fifth cs conversation): added the Claude page, a chat with Claude Code on the Mac that runs in auto mode in a folder under `~/Documents` (`dd4e335`, `fc3d6b4`). A ChatGPT agent worked in the same tree on ranking subscriptions and a daily Gmail sync; at the user's request that work was committed as `af0319c`. Landed the `engine-dropdown` feature (`568e7c8`) after moving a README note to clear a conflict, and changed the README so each feature keeps its own verification notes (`0a8dbae`). 186 Python and 44 Flutter tests pass. Published build 29859450 and checked it on the emulator. The `engine-dropdown` worktree isn't retired yet: its own session records are uncommitted. Not merged into `main` or pushed.

October 10, 2026 (sixth cs conversation): the Applied page showed "Gmail sync needs attention" because the 9 Oct sweep ran while the Mac's Claude login was Work, and the refusal counted as that day's attempt. A wrong login now retries every 10 minutes instead of waiting a day. The first live import then ran: 22 emails, and Proxify moved to rejected. Added a green or red mark with the last refresh time on the Applied tab. Committed only this conversation's changes as `eb0b059`; the Codex agent's browser version stays uncommitted. Published build 29860579, which includes that uncommitted work at the user's request. 192 Python and 49 Flutter tests pass.

October 10, 2026 (sixth conversation, continued): the Claude page accepts photos and runs Opus 5.5 at xhigh effort (build 29860692). Drafted a Supabase application answer. Uncommitted.

October 11–12, 2026 (seventh conversation): the tailnet 502 came from a reboot, since nothing restarts the service, so it was restarted. Dismissed roles now reach the server and stay out of Claude's shortlist (build 29863129). A search keeps going while the app is in the background and resumes on return or relaunch (build 29863142). Uncommitted.

October 12, 2026 (eighth conversation): a dry run of CV improvements based on the 22 applications and 16 of their postings. It found a PDF parsing defect (Source Sans headings lose their spaces in pypdf) and its fix, and built a one-page draft with the facts the user confirmed and the "Senior Backend Engineer" headline. The draft is in that conversation's scratchpad; cv-refactor and `cv/` are unchanged until the user says "apply". A `/roast-local` grumpy review of the branch (Fable 5.1) runs in its own worktree.

October 12, 2026 (ninth conversation): `/fix-review` found no PR, because the repo has no remote. The local review, which covered only the CV draft, was then checked finding by finding. The user answered three questions: S3 and Secrets Manager only, 15,000 daily active players, and a shared on-call rotation. Draft C fixed the rest and was applied at the user's request. cv-refactor's `latex/cv.tex` and `plushcv.cls` are replaced, with the 9 Oct CV kept as `cv.v11.*`. The rebuilt PDF is in `cv/`, so the app serves it, and the `.txt` was hand-edited to match. It's one page, and all 28 probe phrases extract in three parsers. Not committed in cv-refactor.

October 12, 2026 (tenth cs conversation): searches now also fetch LinkedIn Jobs. The jev-ultrafast browser agent types the search in the Chrome profile signed in to LinkedIn, behind a code guard that refuses applying, saving, messaging and similar controls. Code then reads up to 25 listed jobs from LinkedIn's own job-detail JSON. Live: 2 agent actions, 31–33 s, 25 fetched, 12 kept after ranking. The service was restarted with it (`linkedin_available: true`). Then, at the user's "yes, go", the app got a LinkedIn switch under Job sources and LinkedIn in the search summary. Build 29863531 was published (APK and website) and checked on the emulator. Uncommitted.

October 12, 2026 (eleventh cs conversation, 16:41–17:43): Mastra rejected the user and had sent no confirmation, which would have jammed the daily Gmail sync. Mastra was added to the applied list by hand, with the rejection attached. France can now be picked, because all eight Adzuna markets are selectable (`56ab8d8`). Search options shows what the LinkedIn agent (Jev) costs, estimated from TypeSafe's token counts at $0.042 per million input tokens (`936ea18`). Build 29863576 was published and the service restarted. 232 backend and 61 Flutter tests pass. The Sticker Mule answers are paused, and LinkedIn on a locked Mac is untested.

October 12, 2026 (twelfth cs conversation, 17:45–18:15): Glassdoor has no public API, so searches now also fetch Glassdoor through jev-ultrafast, the way LinkedIn works. It runs in the same Chrome profile behind its own action guard, and code reads each role's schema.org JobPosting. The shared browser-agent code moved into `backend/jev.py` and `backend/jev_runner.py`. Live: 3 agent actions, 54–57 s, 25 fetched, 9 shown after ranking. The app has a Glassdoor switch, and Jev usage covers both sites. Build 29863632 was published and the service restarted. 249 backend and 62 Flutter tests pass. Uncommitted. Wrapped at 21:05 EEST; task #3 tracks `test_ai_pick.py`, which would start the real agents if run alone.

October 13, 2026 (fourteenth cs conversation): searches now belong to the service. It saves the last finished search (`backend/search.json`), and every device shows it through `GET /search/latest`. Pull-to-refresh, launch and resume only reload it; only Find opportunities starts a search. A Cancel search button stops a running search (`POST /search/<id>/cancel`), interrupting a browser agent or ranking call like Ctrl+C. 261 backend and 64 Flutter tests pass. Build 29864703 was published, the service restarted, and cancel was checked on the emulator. Uncommitted.

October 15, 2026 (fifteenth cs conversation): reworked the CV to bring out safe refactoring, delivery and parallel AI sessions, with evidence from the work repo's merged PRs. After the user's feedback (no exact numbers, AI sessions not first, security bullet rejected), Draft H was applied. It leads with the tests-first retirement of the legacy framework, adds the coverage push and the migration-rewards token redemption, and mentions parallel AI sessions only in the summary. The 12 Oct CV is kept as `cv.v12.*`, the rebuilt PDF is in `cv/`, and the `.txt` matches. Not committed in cv-refactor.

October 15, 2026 (sixteenth cs conversation): the website's Claude page dropped pasted screenshots, because Flutter web ignores an image pasted into its text box. A browser paste listener now attaches them like photos from the button, shrinking anything over 2048 px or 3.75 MB. Passed 65 native Flutter tests, 15 Chrome tests and a headless-Chrome check of the release web build on a throwaway service. The web app was rebuilt for the live service. Committed as `399c0c5`; no APK, since Android is unaffected.

October 15, 2026 (seventeenth cs conversation): answered whether Oracle's free tier could host the Claude subscription. It can, and Oracle's docs confirm the free Arm VM is now 2 CPUs and 12 GB, but the LinkedIn and Glassdoor agents couldn't move there. Then `/roast-local` sent the final CV (Draft H) to a Codex grumpy review (`gpt-6-astra` at xhigh) in `~/.claude/roast-worktrees/jobs-manager/claude-ranking-app-updates-20261015-133657`. Its findings will be in that folder's `REVIEW.md`. No code changed.

October 15, 2026 (eighteenth cs conversation): the Codex review of the CV returned "pass with concerns" with ten findings. `/fix-review` found no PR (no remote), so each finding was checked against the PDF, its LaTeX source and the work PRs. The user decided four of them: keep two columns, keep "& AI" but list AI skills last, pair each reliability failure with its fix, and describe the thesis as a photo prototype. Draft I fixed eight findings and declined two that asked for exact figures or a different lead. It was applied at 14:13: Draft H is kept as `cv.v13.*`, the PDF is in `cv/` and served by the app, and the `.txt` and `backend/profile.md` match. Not committed in cv-refactor.

October 15, 2026 (nineteenth cs conversation): searched for an AI skill that writes, reviews and rebuilds CVs, and read the leading candidates' skill files. None fits the two-column LaTeX CV and the no-exact-figures rule. claude-resume-kit comes closest, and ruthless-cv-optimizer is the only single-skill option. The recommendation is a custom `/cv` skill that borrows from both; the user wrapped before deciding. Nothing installed or changed.

October 22, 2026 (twentieth cs conversation):
- **Tailnet URL.** It said "site can't be reached" because the Mac's hostname had become `erp-bogdang-mac` and the tailnet name followed it. The name is pinned back with `tailscale set --hostname=macbook-pro-2`, and the service, down since the October 19 reboot, was restarted.
- **Hosting.** Compared a colleague's hosting suggestions (Hostinger, Raspberry Pi, Hetzner, Oracle) and recommended a box at home on Tailscale. Nothing decided.
- **LinkedIn and Glassdoor.** Both had failed in every search. LinkedIn had moved its job search to a new page, and Glassdoor's address check rejected "Node.js". Both are fixed and verified live (25 and 23 jobs), and all 262 backend tests pass. The service runs the fix. Committed later that day as `465cd88`.

October 22, 2026 (twenty-first cs conversation):
- **Sources and applied roles.** Flosum hadn't been applied to. We Work Remotely is no longer searched (`f8a327d`). A role a job board reposts "on behalf of" an applied company is now hidden, after a SoftServe repost by Undelucram.ro came back (`909864f`).
- **Gmail.** Every search now checks Gmail before leaving out applied roles, with a line under the results (APK 29878140). At the user's request the check then stopped depending on the Mac's Claude login: the service reads the personal mailbox over IMAP and the engine picked in the app sorts the emails. 275 backend and 65 Flutter tests pass. Uncommitted, and waiting on a Google app password in the keychain item `fieldwork-gmail`.


November 6, 2026 (CV review and publication): verified the local REVIEW.md and corrected migration scope and simulated-cost wording. After the user’s revisions, the recurring-scan bullet focuses on NestJS, Redis leases, telemetry and lifecycle tests; the summary explicitly names distributed systems and separates delivery under pressure from parallel AI sessions. Applied the approved main CV, backed up the previous main as cv-refactor/latex/cv.v16.tex/.pdf/.txt, updated its text companion and the app ranking profile, and published the PDF by rename. One-page layout, all 14 bullets, summary extraction and live /cv download verified. Next backup v17. No commits or service restart.

November 7, 2026 (hybrid roles): at the user's request, searches now also keep hybrid roles based in Romania and Malta, beside the remote, Romania-eligible ones. LinkedIn searches each country once more (Malta geoId 100961908); Glassdoor adds Romania only, since it lists no jobs in Malta. The app's Search options have a Romania/Malta chip pair, and cards read "Hybrid · Romania" or "Hybrid · Malta". Live: LinkedIn Malta 25 fetched/8 kept, Romania 25/17, Glassdoor Romania 25/11. 286 backend and 66 Flutter tests pass. Published the website and APK 29900922 and restarted the service; APK 29900954 then fixed a "Fetching null" progress line. Uncommitted.

November 7, 2026 (Gmail sync): the check hadn't imported since 22 Oct: first no app password in the running service, then one Micro1 reply with no matching entry blocking every sweep. Replies now link across company names (same thread, or an earlier email naming the sender about the same role), and an unplaced reply waits and is retried instead of blocking the rest. After a dry run on copies, the live sweep imported 15 emails and set aside 4. APK 29900964 shows set-aside replies on the Applied tab. 291 backend and 68 Flutter tests pass. Uncommitted.

- Summary: `.cs/summary.md`
- Durable memory index: `.cs/memory/MEMORY.md`
- Configured narrative: `.cs/memory/narrative.bogdan-gherghina-erepubliklabs-com.md`
- Setup and build instructions: `README.md`
