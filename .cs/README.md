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

- Summary: `.cs/summary.md`
- Durable memory index: `.cs/memory/MEMORY.md`
- Configured narrative: `.cs/memory/narrative.bogdan-gherghina-erepubliklabs-com.md`
- Setup and build instructions: `README.md`
