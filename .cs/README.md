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

## Feature: cv-tailor (7 Nov 2026)

Objective: from the phone app and the website, tailor the CV to a job with the resume-tailoring skill. A "Tailor CV" button on a job (or a pasted posting) starts a Claude-page chat on the Mac that asks its gap questions in the chat, builds a one-page tailored PDF and Report.md under the service's `cv/tailored/<Company>/<Role>/`, and the app lists and downloads them.

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

November 7, 2026 (feature worktree `cv-tailor`): built CV tailoring. A "Tailor CV" button on a job, or a pasted posting, starts a Claude page chat that follows the resume-tailoring skill in `cv/tailored/<Company>/<Role>/`. Claude asks its gap questions in the chat, then builds the PDF and `Report.md`, and the app's **Your CVs** sheet downloads them. 275 backend and 72 Flutter tests pass. A live end-to-end run on a temporary instance built and served a one-page PDF. Committed as `5839c84` (with notes in `7d6b7e6`) on `cs/cv-tailor`. Not deployed: it lands through `/finish cv-tailor` once the base's uncommitted work is committed.

- Summary: `.cs/summary.md`
- Durable memory index: `.cs/memory/MEMORY.md`
- Configured narrative: `.cs/memory/narrative.bogdan-gherghina-erepubliklabs-com.md`
- Setup and build instructions: `README.md`
