---
name: project-hosting-off-laptop
description: "What moving the Fieldwork service off the Mac to a personal server must preserve: the Gmail app password and a ranking login for the Gmail sync, and a signed-in Chrome profile on a home IP for the LinkedIn/Glassdoor agents. Hosting options compared 2026-10-22."
metadata:
  node_type: memory
  type: project
  originSessionId: 9161b7d3-9af6-40f6-97cb-590461031f46
  modified: 2026-10-22T16:02:23.311Z
---

On 2026-10-22 actor bogdan-gherghina-erepubliklabs-com asked about hosting Fieldwork on a personal server, so it stops depending on the laptop. A colleague had suggested Hostinger, a Raspberry Pi at home, Hetzner, and Oracle's free tier. No choice was made. Recommended: a box at home on Tailscale (Pi or used x86 mini PC); Hostinger KVM 2 was the second choice.

Constraints any move must keep:
- **Gmail sync.** Until 2026-10-22 it used the claude.ai Gmail connector, which needs the full `claude` login (setup-token tokens "can only make model requests"). Since then it reads IMAP with a Google app password and sorts with ranking's logins (Claude token or Codex home), so a server needs only the app password plus one ranking login.
- **jev agents (LinkedIn, Glassdoor).** They drive a Chrome profile signed in to LinkedIn. A datacenter IP raises the risk that LinkedIn restricts the account, and ARM Linux had only Chromium (Chrome for ARM64 was announced for Q2 2026 but not confirmed as shipped).
- **Mac-only pieces to port.** These are the Agents sidebar Personal/ERPK account switch, `caffeinate` in `scripts/serve.sh`, and the profile tab opening via a visible window. The service also has no boot unit (see [[reference-tailscale-service]]).

Oracle Always Free A1 dropped to 2 OCPU / 12 GB in 2026. Oracle reclaims an idle instance when p95 CPU, network and memory all stay under 20% over 7 days, which Fieldwork would meet. Hetzner's cloud lines were marked unavailable that day. Re-check prices before acting. See [[project-fieldwork]].

An old Android phone at home was also asked about (2026-10-22). Claude Code runs there only inside a Termux proot-distro Ubuntu (glibc, linux-arm64 binary; community guides, no Android build since v2.1.113, upstream issue anthropics/claude-code#50270). There is no desktop Chrome, so the jev agents can't move. The Android Tailscale app has no Serve, and the Fieldwork app allows plain HTTP only to loopback, so HTTPS needs userspace `tailscaled` in Termux (untested; Android blocks netlink) or a cleartext exception for the tailnet. Android 12+'s phantom-process killer and a battery kept charging 24/7 are the other risks. Ranked below a Pi or an old laptop.
