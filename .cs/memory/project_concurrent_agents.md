---
name: project-concurrent-agents
description: "Fieldwork's working tree is edited at the same time by a ChatGPT (Codex) agent, so check for its uncommitted changes before staging, committing, restarting the service or publishing an APK; also how to split interleaved work into separate commits."
metadata:
  node_type: memory
  type: project
  originSessionId: a40bf9f0-d9d9-49e7-a4db-5f507c181cf3
  modified: 2026-10-13T09:20:00.000Z
---

On 2026-10-09 a ChatGPT.app agent (its `node_repl`/`cua-repl` processes have this repo as their cwd) worked in the same working tree as a Claude session. It edited `backend/service.py`, `lib/main.dart`, the README and other files, restarted the service, and published APKs. None of that showed up until `git status` and file times were compared against the session's own edits.

**Why:** a plain `git add` or a whole-file `dart format` mixes its unfinished work into your commit, and a restart or build replaces something it may still rely on.

**How to apply:** before committing, check `git status` for files you didn't touch. To commit only your part, build each shared file from HEAD plus your own edits, write it to the index with `git hash-object -w` and `git update-index --cacheinfo`, and test that snapshot alone (`git checkout-index -a --prefix=<tmp>/`, then run both suites there). To split your own work when two features share files, start from the conversation's cs autosaves: `git log refs/worktree/cs/session/<conversation-id>` lists a full-tree snapshot taken after every Edit or Write (the first one already includes that first edit, so undo it by hand). On 2026-10-13 the earlier feature was staged from that snapshot, tested alone and committed before the newer one. Commit the other agent's work only when the user asks; on 2026-10-09 they did, so a feature could land. The auto-mode classifier refused to stop a service or rebuild an APK that agent owned ("Interfere With Workloads"); hand the user the `!` command instead of working around it. See [[project-fieldwork]].
