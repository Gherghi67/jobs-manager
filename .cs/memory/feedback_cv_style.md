---
name: feedback-cv-style
description: "CV style actor bogdan-gherghina-erepubliklabs-com chose on 2026-10-15: no exact figures in bullets, lead with safe refactoring, AI/parallel-session work never first; two columns kept, AI & ML skills last"
metadata:
  node_type: memory
  type: feedback
  originSessionId: b2d0967b-0084-4e30-8257-7e3d0dce776c
  modified: 2026-10-15T10:03:43.202Z
---

On 2026-10-15 actor bogdan-gherghina-erepubliklabs-com went through Drafts D–H and made the following choices. Draft H was applied, with the 12 Oct version saved as `cv.v12.*`.

- **No exact figures in bullets.** They said "there are too many exact numbers in the CV, please remove them". PR counts, coverage percentages, test counts and SQL statement counts were replaced with wording like "from about half the code to nearly all of it in a month" and "by more than half". They kept "5+ years", "4+" and "15,000 daily active players", which they didn't object to.
- **Parallel AI sessions and PR counts go neither first nor in their own bullet.** They first moved that bullet to last, then deleted it. Parallel sessions appear only in the summary. On November 6, the user approved emphasizing delivery under pressure and multitasking across parallel AI coding sessions in that summary, superseding the requirement to put its refactoring clause first.
- **Lead with safe refactoring.** The first eRepublik bullet is the tests-first, refactor-second retirement of the legacy Pinus framework.
- **After the /roast-local review (Draft I, applied 2026-10-15 14:13):** keep the two-column layout even though poppler's default text mode interleaves the columns; keep the headline's "& AI" but list the AI & ML skills group last, with "Fine-tuning (thesis)"; pair each reliability failure with its fix. Exact figures stayed out even though the reviewer asked for them.
- **The security-fixes bullet was rejected** ("naah, find something else"). It covered SQL injection, the gift-thread exploit and the negative VIP-shop amount. They picked the migration-rewards token redemption bullet instead.

**Why:** they didn't say, beyond calling the earlier versions too in-your-face. Treat it as a preference for understated, descriptive claims over metrics.

**How to apply:** for CV edits and application answers, describe results in words rather than figures, and don't open with AI tooling. When the user asks to replace a bullet, offer several PR-backed options with previews instead of guessing one at a time. The review-agents, fine-tuned triage model and PR-review facts are no longer on the CV; ask before restoring them. Related: [[user-work-facts]], [[user-no-react]], [[feedback-cv-no-fieldwork]], [[project-cv-pdf-text]].

## November 6 wording decisions

- The user rejected the dense Pomelo/Pinus, RPC-isolation and characterization-test lead. They selected plain wording about refactoring the legacy game backend into NestJS services, regression tests before each migration step and protecting existing gameplay, then explicitly added DORA practices.
- Keep Jest/SWC last in the eRepublik experience bullets.
- The user authorized a trial clarity pass using resume-builder plus selected ASD-STE100 rules and focused presentation from i-have-adhd. Shorter statements separate actions from results. The revised pass was subsequently reviewed and approved as the main CV; this does not imply blanket approval of strict STE formatting.

## Later November 6 bullet revisions

- The user rejected the incident-by-incident reliability bullet and asked to emphasize flexibility, superseding the earlier failure/fix-pair preference for that bullet. Latest draft balances feature development with shared production on-call duties across gameplay services, background jobs and database repairs.
- Explicitly say token-redemption users migrated from another game.
- The user rejected dense Jest harness details and the coverage-growth sentence, then requested retaining `@swc/jest` for speed plus the separate type-checking gate. Latest draft preserves expanded coverage and isolated parallel test data.
- Explain AI assessment and bot simulations separately in the New Relic comparison. Do not imply measured production savings.
- These revisions were reviewed and applied to the permanent master, app PDF, text companion and ranking profile on November 6; the previous main is backed up as v16.

## November 6 final review and publication

- User approved naming distributed systems in the summary: “Strongest in distributed systems, concurrency and backend performance.”
- Final delivery wording: “Delivers features under pressure while balancing production support and shifting priorities. Uses parallel AI coding sessions to progress multiple tasks at once.”
- Recurring scans now describe NestJS implementation, Redis leases, telemetry and lifecycle tests; user rejected pairing NestJS with “keeping durable jobs in BullMQ” and the activation-gates jargon.
- Main CV uses component-level migration wording and potentially lower-cost Uptrace wording. The right-column skill-group spacers were reduced from 5pt to 1pt to fit the approved summary; fonts, margins and class are unchanged.

## CV storage and filenames — November 6

- Every tailored CV belongs in a dedicated company folder, with a role subfolder: `~/Documents/jobs-manager/cv/tailored/{Company}/{Role}/`. The user explicitly means the visible **Documents/jobs-manager**, not the hidden code-sessions worktree and not cv-refactor/tailored. This overrides the resume-tailoring skill's older flat `{Company}_{Role}` output convention. Discover tailored sources recursively.
- Every delivered tailored PDF must be named **`Bogdan-Gherghina-CV.pdf`**. Never put the company or role in the PDF filename; use the containing folders for those. Keep source, class/assets, preview and report beside the PDF.
- Approved first example: `~/Documents/jobs-manager/cv/tailored/Twin_Harbour_Interactive/Senior_Nodejs_Developer/`. Copies also remain in cv-refactor/tailored and the hidden session tree; the Documents/jobs-manager copy is the user-facing destination.
- Main CV goes at `~/Documents/jobs-manager/cv/Bogdan-Gherghina-CV.pdf`. Saving a tailored CV must not replace it. For future approved main-CV updates, publish here as well as the service worktree using atomic replacement. The Documents copy was stale on November 6 and was synchronized to the approved master; its older PDF is under `~/Documents/jobs-manager/cv/archive/before-main-sync-20261106-162202/`.
