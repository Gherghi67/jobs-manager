---
name: project-session-home
description: "The jobs-manager session lives only in the code-sessions profile; cs and /branch-out under cs can't find it, so branch out with --launch code-sessions."
metadata:
  node_type: memory
  type: project
  originSessionId: 864a7b96-e569-43a5-b2f5-abdeeacea463
  modified: 2026-11-07T14:00:32.361Z
---

The jobs-manager session's folder is `~/.local/share/code-sessions/home/sessions/jobs-manager`, in the code-sessions profile. The `~/.claude-sessions/jobs-manager` link that the October adoption notes mention no longer exists. Measured with `branch-out context --json` on 2026-11-07: this session resolves as cs (through `CS_BIN`) with sessionsRoot `~/.claude-sessions`, so `baseSessionOk` is false; `branch-out context --session-manager code-sessions --json` finds it.

**How to apply:** run `/branch-out` here with `--launch code-sessions` (the user chose code-sessions for `jobs-manager@cv-tailor` on 2026-11-07), and open features with `code-sessions jobs-manager@<slug>`. Don't recreate the cs link without asking.
