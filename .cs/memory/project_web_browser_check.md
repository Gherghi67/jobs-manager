---
name: project-web-browser-check
description: "How to try the Fieldwork web build end to end in a real browser without the real token or data: a throwaway in-process service plus a headless Chrome driven over CDP, since the chrome-devtools MCP can be locked."
metadata:
  node_type: memory
  type: project
  originSessionId: 108c9dfe-a009-4cea-9db1-f59877917f90
  modified: 2026-10-15T10:27:49.393Z
---

Found on 2026-10-15 while checking screenshot paste on the Claude page. The chrome-devtools MCP refused to start because its own profile (`~/.cache/chrome-devtools-mcp/chrome-profile`) was already running in another session. Plan for that rather than retrying it.

What worked instead:
- **Service:** a throwaway in-process service from the scratchpad. Set `JOBS_APPLIED_FILE`, `JOBS_SEARCH_FILE`, `JOBS_CHATS_FILE` and `JOBS_JEV_USAGE_FILE` to temp files, `JOBS_CLAUDE_ROOTS` to a temp folder, and `JOBS_LINKEDIN`/`JOBS_GLASSDOOR=off`, all before `import service`. Then set `service.WEB_DIR` to a scratchpad build (`flutter build web --release --no-web-resources-cdn -o <dir>`) and `Handler.token` to a dummy, and serve `ThreadingHTTPServer` on another port. Don't call `service.main()`: it starts the Gmail sync and reads the real token.
- **Login:** pre-seed the dummy token in the page's localStorage as `flutter.token` (JSON-encoded string), plus `flutter.url`, then reload. This keeps the real token out of tool calls; never type it through a browser tool.
- **Browser:** headless Chrome (`--headless=new --remote-debugging-port=… --user-data-dir=<scratch>`) driven by a Node script with Node 22's built-in `WebSocket` (no Python websocket package is installed). Flutter draws on a canvas, so click `flt-semantics-placeholder` first to turn on its accessibility tree. Tooltips then appear as `aria-label`s, and you click an element's rect centre with `Input.dispatchMouseEvent`. Clicking a text field makes Flutter's real `TEXTAREA` the active element.
- Don't put test data on the system clipboard; it overwrites what the user copied. Fire synthetic events (e.g. a `ClipboardEvent` with a `DataTransfer`) at the active element instead.

Widget tests under `flutter test --platform chrome` don't create DOM text fields (text input is mocked), so only this setup exercises the real browser integration.
