---
name: reference-tailscale-service
description: "Tailnet address of the Fieldwork job service and the device names on actor bogdan-gherghina-erepubliklabs-com's tailnet."
metadata:
  node_type: memory
  type: reference
  originSessionId: 09bcf62e-ac7c-4fd0-9d14-2d7c22258362
  modified: 2026-10-11T14:50:00.000Z
---

On the tailnet of actor bogdan-gherghina-erepubliklabs-com (set up 2026-10-09), the Fieldwork service is published with Tailscale Serve at `https://macbook-pro-2.tailaedfae.ts.net`. It is tailnet-only and proxies to `http://127.0.0.1:8765`, and that is the URL the phone app uses. Devices: `macbook-pro-2` (macOS, runs the service) and `pixel-10-pro` (Android). The Mac's Tailscale CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`, from the Homebrew `tailscale-app` cask, which needs sudo, so the user installs it. `tailscale serve status` shows the current mappings.

When the app on the phone reports "Cannot reach the service" while the Mac side is healthy, check `tailscale status` first. On 2026-10-09 it showed `pixel-10-pro` offline: the phone's Tailscale VPN was off, and restarting the phone did not reconnect it. The user has to switch Tailscale on in the app; Android's Always-on VPN setting keeps it connected across reboots.

Taildrop (`tailscale file cp`) to the Pixel stalled with no prompt on the phone, so don't rely on it for getting files there. See [[project-fieldwork]] for the service and update flow.

A **502** from the tailnet URL means nothing is listening on 127.0.0.1:8765. Tailscale Serve keeps its mappings across reboots, but the service has no LaunchAgent: it runs only from `nohup scripts/serve.sh`, so after a Mac reboot it stays down until someone restarts it (first seen 2026-10-11, after the 22:36 reboot on 10 Oct). Restart: `nohup scripts/serve.sh >> backend/service.log 2>&1 < /dev/null &`. An unauthenticated `/health` answering 401 means it is up.
