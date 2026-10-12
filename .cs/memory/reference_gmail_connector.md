---
name: reference-gmail-connector
description: "Where actor bogdan-gherghina-erepubliklabs-com's job-application emails live (personal Gmail via the claude.ai connector) and the reconnect gotcha: after /mcp re-auth the tools only appear after restarting Claude Code."
metadata:
  node_type: memory
  type: reference
  originSessionId: 33650d22-30ba-4c27-a820-6682d0a50475
  modified: 2026-10-12T12:19:12.145Z
---

Actor bogdan-gherghina-erepubliklabs-com's job-application emails (ATS confirmations and rejections) are in their personal Gmail, gherghinabogdan7@gmail.com, not the @erepubliklabs.com work account. On 2026-10-09 the claude.ai Gmail connector reached that mailbox. Before reading anything, check the `toRecipients` of one recent thread to confirm which mailbox the connector is on.

Gotcha (Claude Code 2.1.295, 2026-10-09): when the connector session expired and `/mcp` re-authenticated it ("Authentication successful"), its tools still did not come back into the running conversation. ToolSearch found none, and a newly spawned subagent didn't have them either. Exiting Claude Code and resuming the conversation (`cs jobs-manager` then `r`) loaded all 30 Gmail tools. Once the connector is live in the conversation, a background subagent can load the Gmail tools through ToolSearch itself: on 2026-10-09 a general-purpose subagent did a read-only sweep (all categories, Sent and Spam) and returned only structured JSON. That keeps bulk email content out of the main context. A `get_thread` on a trashed thread returns "The caller does not have permission"; search with `includeTrash` to verify instead.

Wrong-mailbox symptom (2026-10-12): in a conversation whose session email was the @erepubliklabs.com address, `get_thread` on thread ids stored in `backend/applied.json` returned "Requested entity was not found", and a search for known senders (Voodoo, Modash, Proxify) returned `{}`. The connector was on a different mailbox. Re-link it to the personal account through `/mcp` and restart Claude Code before relying on it. Don't conclude that the emails are gone.

The applications imported from that mailbox are described in [[project-fieldwork]].
