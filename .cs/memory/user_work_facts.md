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
- They chose **"Senior Backend Engineer"** as the CV headline. The job titles stay as held: "Backend Software Engineer (Contractor)" at eRepublik.

**How to apply:** use these in CV edits and application answers instead of asking again. Don't inflate them (no "led", no CCU, no EC2, no SES) without new confirmation. Related: [[user-no-react]], [[project-cv-pdf-text]].
