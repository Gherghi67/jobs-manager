---
name: user-work-facts
description: "Work facts actor bogdan-gherghina-erepubliklabs-com confirmed on 2026-10-12 for CV and application answers: 15,000 daily active players, shared on-call rotation, AWS S3 + Secrets Manager, reviews PRs, Senior headline"
metadata:
  node_type: memory
  type: user
  originSessionId: db6a88df-e7da-497b-96f9-4f9cac2006e0
  modified: 2026-10-12T12:41:31.302Z
---

Asked on 2026-10-12 for facts the CV lacked, actor bogdan-gherghina-erepubliklabs-com confirmed these about the eRepublik Labs game backend:

- The game has **15,000 daily active players** (the measure was clarified later the same day, when the review asked which 15,000).
- They are on a **shared on-call rotation** for production incidents, not the sole on-call. Write "served on the on-call rotation", not "owned on-call".
- The backend uses **AWS services**; list **S3 and Secrets Manager** only. The work repo `~/Documents/erpk_aolbackend` `package.json` also shows SES (v2), but their only SES commit is a test-coverage one (`3b8851931f`), so they chose to drop it. Their Secrets Manager commits include real feature work (`8273c75ddf`, May 2026). They have no commits on S3 code, but S3 was on their own CV before. `deploy.sh` deploys over ssh to app hosts, so EC2 is unverified; don't claim it or write "built with … AWS".
- They **review teammates' pull requests**. Mentoring or leading people was not claimed.
- On 2026-11-06 they confirmed using **DORA practices** for the backend migration and explicitly requested that wording in the CV. Specific DORA metric tracking and measured delivery outcomes remain unverified.
- They chose **"Senior Backend Engineer"** as the CV headline. The job titles stay as held: "Backend Software Engineer (Contractor)" at eRepublik.

Evidence from the work repo's merged PRs, gathered on 2026-10-15 with `gh pr list --author @me` in `~/Documents/erpk_aolbackend` and now behind the CV's wording:

- **Safe refactoring.** The legacy Pinus framework is being retired with a two-PR flow: characterization specs first, then the refactor with those specs unchanged. Examples: the RPC facade (#445 → #447 with 69 call sites → #458), and ports of the tracking, leaderboard and presets handlers and the AppsFlyer webhooks to NestJS.
- **Coverage.** Statement coverage on the full suite went from 57.99% (2,836 tests, 2026-08-27) to 98.53% (15,461 tests, #379, 2026-09-24).
- **Migration rewards.** The Firstborn token redemption (#393, #426) cut the worst-case claim from 12,889 SQL statements to 4,874.
- **Delivery.** 129 PRs were merged between 2026-07-29 and 2026-10-15, with up to 16 open at once, from parallel worktree sessions.
- **Review.** 127 of those 129 PRs were reviewed only by the `github-actions` AI reviewer. Say "AI code review", never peer or human review.
- **Reliability incidents** behind the CV's reliability bullet: the orphaned-fort `expireForts` error flood (#232; its 15,140 hits per 12 h were measured on **staging**, so don't call it a production flood); `reports_details` enum drift that stored 423,824 production report types as '' (fixed with additive instant ALTERs and a cron that repairs one partition per tick); and AvA BullMQ point chains that fired once and died on a job-id collision.
- **PvP Arena** (May–Jul 2026) is a separate module from the Marauder event and AvA Seasons.
- **Thesis.** The Face Mask Detector was a prototype that worked on uploaded photos and never ran at a venue (confirmed 2026-10-15). Don't describe it as a deployed monitoring system.

Per-feature evidence for the eRepublik bullets (commits, impact, confidence) is in `~/Documents/cv-refactor/workflow-result.json`; check it before asking the user again.

The user wants these figures left off the CV as exact numbers (see [[feedback-cv-style]]); ask before quoting them in an application answer.

**How to apply:** use these in CV edits and application answers instead of asking again. Don't inflate them (no "led", no CCU, no EC2, no SES) without new confirmation. Related: [[user-no-react]], [[project-cv-pdf-text]].

## User confirmations — 2026-11-06 CV review

- The token-redemption feature supported players migrating **from another game**; make the cross-game context explicit.
- Switching Jest to `@swc/jest` made the tests faster while dropping type checking during test execution; the user added a **separate type-checking gate**. No speedup magnitude was supplied.
- The New Relic alternatives comparison used **AI to assess the best options and bots to run simulations**. Earlier evidence describes pricing simulations; no realized production savings or completed rollout is established.

## Twin Harbour application confirmations — 2026-11-06

- User has **no PHP experience**, including study/older projects, but is willing to learn/use it. A tailored CV may say “Open to learning PHP”; do not list PHP as an existing skill.
- For Twin Harbour's Hamburg/Malta hybrid role, the user would consider **Malta only**. They remain based in Bucharest. Do not imply willingness to work hybrid in Hamburg, a firm relocation commitment or a start date.
