---
name: feedback-resolve-finish-blockers
description: "When /finish is blocked by base dirt or a merge conflict, the user wants Claude to clear it from the base rather than hand it to the feature conversation; feature worktree files stay untouched."
metadata:
  node_type: memory
  type: feedback
  originSessionId: a40bf9f0-d9d9-49e7-a4db-5f507c181cf3
  modified: 2026-10-09T17:32:07.000Z
---

On 2026-10-09, when `/finish engine-dropdown` was blocked, the user answered "commit them there and then finish" (base dirt) and, after a suggestion to resolve a README conflict in the feature conversation, "you do this".

**Why:** they want `/finish` to complete in one place, not bounce between sessions.

**How to apply:** clear blockers from the base. Commit base-side work when the user asks. Resolve a conflict by rewriting the base's own conflicting lines so the feature's commit merges cleanly; for example, moving a README note out of the shared spot let `cs -integrate-feature` land without touching the feature branch. Still never edit the feature worktree, never commit or discard another session's uncommitted records (retirement waits for them), and never work around a cs refusal. See [[project-concurrent-agents]].
