---
name: reference_github_remote
description: "jobs-manager's GitHub remote is the PUBLIC repo Gherghi67/jobs-manager (personal account), pushed as main; the active gh login is the work account, so pushes need the Gherghi67 token passed explicitly."
metadata:
  node_type: memory
  type: reference
  originSessionId: 7fbec536-2d98-419c-a928-6c36fc3766d4
  modified: 2026-11-07T14:37:31.586Z
---

`origin` = https://github.com/Gherghi67/jobs-manager, **public**, created 2026-11-07 at the user's choice, default branch `main`. The first push sent `claude-ranking-app-updates` (0502116) as `main`; local `main` was left at 4eb4e1d.

Two gh logins exist: `bogdan-gherghina` is the work account (member of the eRepublik-Labs org) and is the active one; `Gherghi67` is the personal one. Push without switching the active account:

`git -c credential.helper= -c 'credential.helper=!f() { echo username=Gherghi67; echo "password=$(gh auth token --user Gherghi67)"; }; f' push origin HEAD:main`

and prefix gh calls with `GH_TOKEN="$(gh auth token --user Gherghi67)"`.

**Why it matters:** tracked `.cs/` notes are published with every push. Before committing, check new notes for credentials and for other people's contact details; on 7 Nov a recruiter's email address was redacted from the narrative before the first push. The user's own Gmail address and the Mac's tailnet hostname were already in history and went public with the user's consent.

Related: [[project_fieldwork]], [[project_concurrent_agents]].
