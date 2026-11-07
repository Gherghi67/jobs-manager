# Fieldwork — jobs manager for Android and web

A personal Android and web app that combines **Adzuna**, **LinkedIn** (through the jev-ultrafast browser agent) and the **remote-job search pipeline from cv-refactor**, with editable options, matching explanations, saved/dismissed jobs, and offline access to the last completed search.

## Install and connect

The recommended ARM64 APK is `artifacts/fieldwork.apk`, compiled in release mode and signed with the local development key for personal installation. It is not configured for Play Store publication. An unoptimized debug APK is also at `artifacts/fieldwork-debug.apk`. The app was built and launched on an Android 14 emulator.

The app uses a small Python service on your computer. Keep that service running while fetching jobs; saved jobs and the last results remain available offline. The phone does not need your Adzuna credentials.

1. Start the service from this directory:
   ```sh
   ./scripts/serve.sh
   ```
   Python 3.10+ is required; there are no third-party Python dependencies. The launcher uses `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` from the environment, or retrieves those exact names from the `wap-ags` secret store documented in cv-refactor. Override the store with `JOBS_SECRETS_SESSION`. Missing credentials leave Adzuna visibly unavailable while remote boards continue. On macOS the launcher runs `caffeinate` for as long as the service is up, so the Mac does not idle-sleep; locking the screen is fine, but closing a MacBook lid still sleeps it unless it is on power with an external display.
2. Connect an Android phone by USB with USB debugging enabled, then run:
   ```sh
   adb install -r artifacts/fieldwork.apk
   adb reverse tcp:8765 tcp:8765
   ```
   On this Mac, `adb` is at `~/Library/Android/sdk/platform-tools/adb`.
3. Open **Fieldwork → Options**, leave the service URL as `http://127.0.0.1:8765`, and paste the token from `backend/.access-token`. The service creates that file with owner-only permissions; do not share it or commit it. On macOS, copy it without printing it:
   ```sh
   pbcopy < backend/.access-token
   ```
4. Tap **Test connection**, then **Save options → Find opportunities**.

For an emulator, the same `adb reverse` works, or use `http://10.0.2.2:8765`. HTTP is allowed only for localhost and the emulator host; arbitrary LAN HTTP is intentionally not enabled. The default service binds only to localhost. `JOBS_ACCESS_TOKEN` can supply a persistent token instead of the local file.

### Without the cable (Tailscale Serve)

Tailscale Serve gives the Mac's service a private HTTPS address that only your own Tailscale devices can reach. The app needs no changes, but the Mac must be awake and running `./scripts/serve.sh` for new searches.

1. Install Tailscale on the Mac (`brew install --cask tailscale-app` or the Mac App Store) and on the phone (Google Play), and sign in to the same account on both.
2. In the Tailscale admin console under **DNS**, enable MagicDNS and HTTPS Certificates. `tailscale serve` prints a link to this page if it is still off.
3. On the Mac, publish the service once. The setting survives restarts:
   ```sh
   tailscale serve --bg 8765
   ```
   With the app-store or standalone Mac app, the CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. `tailscale serve status` shows the address, `https://<mac-name>.<tailnet>.ts.net`; `tailscale serve reset` removes it. Do not use `tailscale funnel`, which makes the service public.
4. In **Fieldwork → Options**, set the service URL to that `https://….ts.net` address, keep the same token, and tap **Test connection**. Tailscale must be connected on the phone.

## Website version

The website uses the same Flutter features and Python service as the Android app. Build it once, then start (or restart) the service:

```sh
./scripts/build_web.sh
./scripts/serve.sh
```

Open `http://127.0.0.1:8765/` on the Mac, or the existing private Tailscale HTTPS address on any connected device. In **Search options → Connect your service**, paste the same token from `backend/.access-token`, then **Test connection → Save options**. The browser uses the address that served the page; it needs no separate API URL or CORS configuration. Neither the token nor any personal data is included in the website build. The public shell loads without a token, but all API data, the CV, and Claude commands still require it.

- Wide windows use a sidebar; narrow windows keep bottom navigation. Search, source filters, AI ranking, saved/dismissed roles, application tracking and statistics, and Claude chat reuse the Android implementation. **Refresh applications** in the top bar supports desktop refresh without a pull gesture.
- Applications, Gmail sync and chats are shared through the service. Saved/dismissed roles, settings, the access token and cached search results are stored separately in each browser's local storage. They are not imported from the phone. Localhost and the Tailscale address also have separate browser storage; use one address consistently. Clearing site data removes the browser's local copy.
- A CV opens in the browser's own PDF viewer inside the page. The app fetches the PDF with the token and hands it to an `<iframe>` as a Blob address, because an `<iframe>` pointing at the service can't send the token. Browsers without a built-in viewer, such as Chrome on Android, show a message instead. **Download PDF** downloads through the browser, and its download settings determine the destination and whether duplicate names are renamed. Android's APK installer is omitted on the web; reload the page after a new web build.
- Keep the Mac and service running for website loading and online features. Cached results can still be read if a loaded page loses its connection; this version does not install an offline service worker. Flutter's rendering assets are served locally.
- Build output is gitignored under `build/web`. The service serves only web entry files and asset directories from that folder, with path traversal and symlink escape checks. Changes to the Flutter UI need a rebuild; changes to the Python service need a restart. The website remains private to your tailnet under the existing Tailscale Serve configuration.

Checks: Flutter analysis, the native Flutter regression suite, Chrome tests for responsive layout, web options, ranking, daily refresh and chat, and backend tests including static-file isolation and API authentication pass. The release build was also exercised in a browser with synthetic jobs for connection, search, saving and persistence across reloads.

## App updates

**Options → App updates → Check for app update** asks the service for the build in `artifacts/fieldwork.apk`. If that build is newer than the installed one, **Install build N** downloads it with the access token, checks its SHA-256 against the service, and hands it to Android's package installer. Confirm Android's "update this app" dialog, then open Fieldwork again. Saved jobs and settings are kept.

- Publish a build with `./scripts/build_apk.sh`. It builds the release APK with the build number set to minutes since 1970, so every build is newer than the last. It writes `artifacts/fieldwork.apk` and `artifacts/fieldwork.json`. The running service picks both up without a restart.
- The first time, Android asks you to allow Fieldwork to install apps. Fieldwork opens that setting; switch it on, come back and tap Install again.
- Builds from before this feature (build 1) cannot update themselves. Install one updater build manually first.
- `GET /app` reports the published build. `GET /app/fieldwork.apk` serves it. Both need the access token. The APK contains no credentials or tokens.
- The installer's result goes to `InstallStatusReceiver`, which is not exported. Other apps cannot fake it. The receiver only acts on install sessions Fieldwork created. It only opens Android's own install confirmation (`CONFIRM_INSTALL`), with any file-access grants removed.

## Your CV

The document icon in the top bar, next to the options icon, opens **Your CVs**. Tapping **Your CV** shows your CV from the service in the app's PDF viewer. The download icon beside it, or **Download PDF** in the viewer, saves it to the phone's **Downloads** folder, so job application forms can attach it from there. The snackbar's **Open** hands it to the phone's PDF app. The same sheet lists CVs tailored to single jobs (see [Tailor your CV](#tailor-your-cv)), which open in the same viewer.

- **Viewer:** on Android, `PdfPages.kt` draws each page with Android's own `PdfRenderer` at twice the screen's width in pixels (1,200–2,400, at most 20 pages), and the app shows the pages with pinch to zoom. The website uses the browser's viewer (see [Website version](#website-version)). No PDF package is added to the app. **Download PDF** saves the PDF already on screen without fetching it again, and a PDF Android can't draw (for example, a password-protected one) can still be saved.
- The service serves the newest PDF in `cv/` at the repository root. Git ignores that folder because the CV carries your contact details. `JOBS_CV_DIR` points elsewhere. The file keeps its name on the phone, so name it the way recruiters should see it. On October 9, 2026, `Bogdan-Gherghina-CV.pdf` was moved there from `~/Documents/cv-refactor/`.
- To update the CV, replace the PDF in `cv/`; no restart is needed. cv-refactor's `latex/build.sh` still writes its output to `~/Documents/cv-refactor/Bogdan-Gherghina-CV.pdf`, so copy a rebuilt CV into `cv/` yourself.
- Saving again replaces the copy Fieldwork saved before rather than adding "CV (1).pdf". If another app already put a file with that name in Downloads, Android saves Fieldwork's copy under a numbered name, and the snackbar shows that name.
- `GET /cv` returns the PDF with its file name and needs the access token. Saving uses Android's MediaStore, so it needs no storage permission. It requires Android 10 or newer; older phones get a message instead.
- **Checked** (November 7, 2026): on the emulator (Android 14, Pixel 7 image, a release build pointed at a temporary service with copies of the CVs), tapping the Wiley tailored CV in **Your CVs** showed its page drawn by `PdfRenderer`, sharp and centred, and **Download PDF** saved it to Downloads. In headless Chrome 156, the website showed the same CV in Chrome's PDF viewer inside the page (`navigator.pdfViewerEnabled` true, an `<iframe>` with a `blob:` address), and going back removed the `<iframe>`.

## AI ranking and subscriptions

In **Options → Ranking**, turn on **Let AI rank the top roles**, choose **Claude Code** or **Codex**, then choose **Personal** or **Work** and tap **Save options**. The choice is saved on the phone and applies to the next search. It only changes job ranking; chats keep their existing login. **Check ranking accounts** reports whether each selected login is available on the service computer. It does not spend a model request or check remaining quota.

The service sends the top 40 keyword matches to the chosen CLI under its subscription login. Each search carries the phone's latest 2,000 dismissed listing ids. Those roles skip the ranking step and come back last, unranked, so the Dismissed tab can still list and restore them. The CLI returns a 0–100 fit, apply/maybe/skip, Romania eligibility, reasons and concerns. Cards and details name the engine that actually ranked the listing, including saved results from earlier searches. The ranking summary names the subscription too. If the selected login is unavailable or hits a limit, keyword results still appear with an explanation; the service never switches to another subscription automatically.

- **Claude:** by default, uses saved logins from the local Agents sidebar account store: `Personal` for Personal, and `Work` or the existing `ERPK` nickname for Work. `JOBS_CLAUDE_PERSONAL_ACCOUNT` and `JOBS_CLAUDE_WORK_ACCOUNT` override the aliases or stored account IDs. Alternatively, `JOBS_CLAUDE_PERSONAL_TOKEN_FILE` and `JOBS_CLAUDE_WORK_TOKEN_FILE` can point to private files holding subscription tokens from `claude setup-token`. Credentials stay on the computer and never enter the phone's settings. Expired saved logins must be renewed on the computer.
- **Codex:** uses `JOBS_CODEX_PERSONAL_HOME` and `JOBS_CODEX_WORK_HOME` for separate signed-in CLI folders. Without these settings, the default `~/.codex/auth.json` is accepted only when its ChatGPT plan matches the selected Personal or Work category. API-key logins are rejected. This integration uses Codex file credential storage.
- To set up a separate Codex Work login, run `env CODEX_HOME="$HOME/.codex-work" codex -c 'cli_auth_credentials_store="file"' login`, sign into the work account/workspace, then start the service with `JOBS_CODEX_WORK_HOME="$HOME/.codex-work" ./scripts/serve.sh`. The same pattern works for Personal with a separate folder. Explicit home mappings identify the intended account, so verify which workspace you sign into. See [Codex authentication](https://learn.chatgpt.com/docs/auth).
- The current machine has Claude Personal, Claude Work and Codex Personal logins available. Codex Work requires a separate login to be configured.
- `JOBS_AI_MODEL` (Claude, default `opus`), `JOBS_CODEX_MODEL` (Codex, default its CLI model), `JOBS_AI_EFFORT` (default `medium`) and `JOBS_AI_LIMIT` (default `40`) tune ranking. Descriptions are cut to 1,500 characters per listing.
- Your profile is read from `backend/profile.md`, which git ignores. `JOBS_PROFILE_FILE` points elsewhere. Without a profile, the engine uses the app's preferences only.
- Ranking runs in an empty temporary folder. Claude has no tools, MCP servers, user settings, hooks or saved session. Codex ignores user config and rules, uses read-only execution with shell, apps, plugins, hooks and web search disabled, and does not persist its session. Inherited API keys and provider-routing variables are removed from ranking processes.
- Verdict caches are separated by engine, subscription, account identity, model, profile and preferences. Changing the selection cannot reuse another account's rankings. Source-fetch caches remain shared.
- Your profile and listings are sent to the selected provider. Eligibility is inferred from listing text; confirm it with the employer.
- `GET /ranking/accounts` returns the four engine/subscription combinations and public status messages. It requires the service access token and never returns credentials.

## Applied jobs

Tap the check icon on a card, or **Mark as applied** in a role's details, once you have applied. The service records the role in `backend/applied.json`, which git ignores, and every later search leaves it out before Claude ranks anything. Claude therefore never scores or shows it again. The **Applied** tab lists what you marked, newest first, with the date. Tap the filled check, or **Mark as not applied** in the details, to undo.

- A new listing counts as already applied when it has the same listing id, the same URL, or the same company and job title, on any board and in any location. Discover shows "Left out N roles you already applied to." after a search.
- Marking a role as applied removes it from Saved and Dismissed. Marking needs the service; the phone keeps a copy of the list so the Applied tab still shows it offline.
- The service stores each role's listing details, Claude's take, and up to 6,000 characters of its description, so you can still read it after the posting is taken down. The file is readable only by your user (0600). Set `JOBS_APPLIED_FILE` to keep it elsewhere.
- Company entries cover one company. Post `{"scope": "company", "company": "…", "title": "…", "applied_at": "<ISO date>", "note": "…"}` to `/applied`. Company names are compared without case, punctuation or legal suffixes, so "Proxify AB" matches "Proxify". On October 9, 2026, the 15 companies from the application confirmations in the personal Gmail (October 2–9) were imported this way.
- Each company entry has a `match` setting, changed with the **Hide all / Hide role / Badge** switch on its card in the Applied tab or with `PATCH /applied/<id>` `{"match": …}`:
  - `company` (the default) hides every role at the company.
  - `role` hides only roles with the entry's title. It needs a title, and suits aggregators such as Jobgether, which post for many employers.
  - `badge` keeps the company's roles visible with an "Applied at … · date" pill and puts them after all other roles. It suits talent pools such as Proxify, where you are already in their pipeline but still want to see good matches.
- Listings from searches before this change carry no company tag, so company entries take effect on them after the next search.
- `GET /applied` lists them, `POST /applied` adds a role, and `DELETE /applied/<id>` removes one. All three need the access token.

### Tracking and statistics

Tap any card in the Applied tab to open everything kept about that application:

- **Status:** Applied, Screening, Assessment, Interview, Offer, Rejected, No reply or Withdrawn. Every change is kept in a dated history that notes whether it came from the app or from an email. A status dated earlier than the current one, such as one from an older email, fills in the history without replacing the current status.
- **Follow up:** a date. The stats panel counts follow-ups that are due, and the card shows "Follow up due". There are no phone notifications.
- **Details:** link to the posting, location, salary or rate, contract type, where you applied (the ATS or platform) and notes of up to 4,000 characters. Company entries also take a role title.
- **Emails:** the trail of confirmations, rejections and other messages, newest first, with the sender's domain. Entries saved before this feature had the confirmation subject as `note`; the service turns it into the first email.

Each card shows its status, the follow-up date and the channel. The top of the Applied tab shows **Your applications**, computed on the phone from the list, so it also works offline. It has four numbers: applications, the last 7 days, how many heard back (any reply, including rejections) and the median wait for a first reply. Below them are applications per week for 8 weeks, current statuses, where you applied, and a rough role family from the title (AI / ML, lead or founding, full-stack, backend). **Hide charts** collapses it.

`PATCH /applied/<id>` takes any of `status` (with optional `status_at` and `source`: `app` or `email`), `notes`, `follow_up` (`YYYY-MM-DD` or empty), `url`, `location`, `salary`, `type`, `channel`, `emails` (a list of `{date, kind, from, subject}` to add; repeats are skipped), plus `title` and `match` for company entries. It returns the updated entry, 400 with a readable message for invalid values, and 404 for an unknown id.

On October 9, 2026, statuses were filled in from the personal Gmail (September 27 – October 9). Voodoo (October 8) and Modash (October 9) sent rejections, and nothing else had replied yet. Each entry received its channel and email trail, Modash its location, and Jobgether its contract type. One more application was added: TeamQuest (AI-Augmented Developer, Fullstack), sent through SOLID.Jobs on October 2. None of the confirmations linked the actual posting, so the links are empty.

## Talk to Claude

The speech-bubble icon in the top bar opens a chat with Claude Code on the computer that runs the service. Each message runs `claude -p` in the chat's folder and continues that chat's Claude Code session, with your settings, CLAUDE.md files, hooks and MCP connectors (Gmail included). Replies stream into the page while Claude works. Each command or file Claude touches appears as a one-line row, and **Stop** ends the reply along with any commands it started.

- **Permissions:** auto mode, as at the desk. The classifier blocks risky actions, which appear as "Blocked by auto mode" rows. Anything that would wait for a permission prompt is refused, because nobody is at the terminal. Permission checks are never switched off.
- **Model:** Opus 5.5 (`claude-opus-5-5`) at `xhigh` effort. `JOBS_CHAT_MODEL` and `JOBS_CHAT_EFFORT` change them; the empty chat page shows which are in use.
- **Photos:** the photo button next to the message box adds up to five photos from the gallery or the camera, and a photo can be sent without text. The phone shrinks each one to at most 2048 px (JPEG quality 85) before upload; the service accepts JPEG, PNG, GIF and WebP up to 3.75 MB each, checking the file's own bytes rather than its label. Claude receives the photos as images, as if pasted into Claude Code, and the message also names where each copy is saved, so Claude can move or attach the file. Copies live in gitignored `backend/chat-images/<chat>/` (mode 600) and go when the chat is deleted. Tap a sent photo to see it full screen. On the website, a screenshot or image pasted into the page (Cmd+V or Ctrl+V) is attached the same way (`lib/paste_web.dart`); a paste that also carries text goes into the message box instead. A pasted image over 2048 px on either side or over 3.75 MB is redrawn at most 2048 px as a PNG, or as a JPEG (quality 85) if the PNG is still too large. Checked on October 15, 2026 in headless Chrome against the release web build: with the message box focused, a pasted 3024×1964 PNG appeared as a thumbnail.
- **Folders:** a new chat works in `~/Documents` or one of its visible subfolders; the app remembers the last choice. `JOBS_CLAUDE_ROOTS` (paths separated by `:`) changes the roots.
- **History:** chats live in gitignored `backend/chats.json` (mode 600). **Chats** reopens or deletes one; deleting leaves Claude Code's own session files alone. The page opens on the latest chat. A reply that was running when the service stopped shows as interrupted.
- **Limits:** one reply at a time per chat (any number of chats can answer at once; only the subscription's usage limits cap them), 30 minutes per reply, 20,000 characters and five photos per message. When Claude Code warns that a subscription limit is near, the reply shows how much is used and when it resets.
- **Security:** the service access token now lets whoever holds it run commands on this computer, within auto mode's limits. The service listens on `127.0.0.1` and is published only on the tailnet. Start the service with `JOBS_CLAUDE_CHAT=off` to switch the page off (the API then answers 403).

The API: `GET /claude/folders` (with the model and effort), `GET /claude/chats`, `GET /claude/chats/<id>?from=<turn>` (turns from that index, which the app polls every second while Claude works), `POST /claude/chats` with `{cwd, text, images}`, `POST /claude/chats/<id>/messages` with `{text, images}` (409 while a reply is running; `images` is an optional list of base64 files), `GET /claude/chats/<id>/images/<name>`, `POST /claude/chats/<id>/stop` and `DELETE /claude/chats/<id>`. The service sends each message to `claude -p` as one stream-json message on stdin (`--input-format stream-json`).

**Verified** (October 9, 2026) live on a temporary service instance (the running service had the page switched off): a new chat in `~/Documents` ran Bash in auto mode and answered in 11 seconds on Opus with the subscription login. A second message resumed the same session and remembered the answer. The chat list and delete worked. On the emulator (Android 14, build 29859435, through the restarted service), the page opened from the top bar, a message ran `pwd` in auto mode, and the reply, its Bash rows and a weekly-limit note appeared. Not yet tried on the phone.

**Photos verified** (October 10, 2026) live on a temporary service instance with the full Claude Code setup: a chat sent with a red test image ran on `claude-opus-5-5` at `xhigh`, answered "solid red" and named the saved copy's path. The image route returned the same bytes, and deleting the chat removed its folder. A direct `claude -p --resume` check showed the image stays in the session for later messages. Build 29860692 carries the photo button; it has not been tried on a device yet.

## Tailor your CV

**Tailor CV for this job**, in a job's details, has Claude build a one-page CV for that role with the `resume-tailoring` skill. **Your CVs → Tailor for a posting** does the same for a pasted job link or posting text. After a confirmation, the app opens a [Claude page](#talk-to-claude) chat that runs on the computer with the service. Claude reads the posting, the master CV and the saved CV rules. It asks its gap questions in the chat, and you answer there. Then it builds the PDF and a report. A bar above the chat offers **View tailored CV** and **Read report** once the PDF exists. **Your CVs** lists every tailored CV: tap one to view its PDF in the app (going back returns to the list), or use its menu to view or download the PDF, read the report or reopen the chat.

- **Where the files go:** `cv/tailored/<Company>/<Role>/` beside the main CV (gitignored, with `JOBS_TAILORED_DIR` overriding), with short ASCII folder names such as `In_The_Pocket/Nodejs_Back_End_Engineer`. The service creates the folder and starts the chat in it. Claude leaves `cv.tex`, the class copy, the PDF, `preview.png`, `Report.md`, `Changes.diff` and `extracted.txt` there. `job.json` records the job and the chat. A pasted posting has no company or role yet, so that chat starts in `cv/tailored/`, Claude creates the folder, and the service links the chat to the first new PDF that appears there.
- **Your copy:** when a tailoring reply finishes with a PDF in its folder, and once at service start, the service copies the PDF (under the main CV's file name) and `Report.md` into the same `<Company>/<Role>` folder under `JOBS_TAILORED_EXPORT_DIR`, which `scripts/serve.sh` sets to `~/Documents/jobs-manager/cv/tailored` (an empty value turns it off). A copy is replaced only by a newer, different build, so a file you change there is kept. The chats keep working in the service's own folder, because a chat moved to another folder can't resume its Claude session.
- **Same name as the main CV:** the tailored PDF keeps the main CV's file name, because recruiters see it. Saving one replaces the copy of that name that Fieldwork saved in Downloads earlier.
- **One chat per role:** tapping **Tailor CV** again for the same company and title reopens that role's chat. After the chat is deleted, a new run builds on the PDF already in the folder.
- **Rules for Claude:** every turn appends tailoring rules to the Claude page's phone prompt (`backend/tailor.py`, `system_prompt`): use the skill and its `latex-output.md`, work in that folder, never touch the master CV, its class, `latex/build.sh` or the main CV in `cv/`, ask gap questions as a short numbered list and wait, and skip DOCX and the library update. Because `cv/` sits inside the cs session folder, Claude Code also loads that session's `CLAUDE.local.md` and memory settings there, so the rules also tell it to ignore the session-notes protocol, save no memory entries and write nothing outside the CV folder. The posting goes inside `<posting>` tags, marked as data from a job site and never instructions. It runs with the Claude page's settings: auto mode, `claude-opus-5-5` at `xhigh`, and the computer's live Claude login. `JOBS_CLAUDE_CHAT=off` switches tailoring off too (403).
- **API:** `POST /tailor` with `{job}` (the job's `title`, `company`, `location`, `url`, `type`, `salary`, `posted`, `source` and `description`, the last cut to 12,000 characters) or `{posting}` (at most 20,000 characters) returns `{chat, existing}`: 202 for a new chat, or 200 with the chat already tailoring that role. `GET /tailored` lists the folders. `GET /tailored/<Company>/<Role>/cv` returns the PDF, and `GET /tailored/<Company>/<Role>/report` returns `{text}` from `Report.md`. Chats from `GET /claude/chats/<id>` carry `tailor: {id, company, title, url, pdf, report}`. Folder names must be plain ASCII names, and a file that links outside `cv/tailored/` is never served.

**Verified** (November 7, 2026) on a temporary service instance from the feature branch, with a scratch CV folder and chats file. `POST /tailor` for In The Pocket's Node.js Back-End Engineer listing started a chat in `In_The_Pocket/Nodejs_Back_End_Engineer`. On `claude-opus-5-5`, the first turn (171 s) loaded the skill, read the CV rules, the master and the earlier tailored reports, checked the work repository and the company, then asked four numbered questions. After a test reply that allowed no new claims, the second turn (118 s) built a one-page PDF with full text extraction, plus `Report.md`, `Changes.diff`, `extracted.txt` and `preview.png`, all in that folder. The chat then reported `pdf: true` and `report: true`. `GET /tailored` listed the folder with its chat. The PDF download matched the file byte for byte and kept the main CV's name. No file outside the folder changed. Widget tests cover the app side; it has not been tried on a device yet.

## LinkedIn (jev-ultrafast browser agent)

Every search also asks LinkedIn Jobs, after the other sources, because it takes about 30 seconds. The [jev-ultrafast](../jev-ultrafast) browser agent types the search in your signed-in LinkedIn, and code reads the listed jobs. Those roles then go through the same ranking, applied-job and dismissal rules as every other source.

**Setup.** The service runs `backend/linkedin_jev.py` with jev-ultrafast's own Python (`~/Documents/jev-ultrafast/.venv/bin/python`; `JOBS_JEV_DIR` points elsewhere), in that folder. jev reads its own `.env` there: the TypeSafe key and `TEXT_MODEL_PROVIDER=codex`. The service passes none of its credentials. Every variable whose name contains KEY, TOKEN, SECRET, PASSWORD, CREDENTIAL or ADZUNA is removed from the agent's environment. Chrome must be running with remote debugging allowed at `chrome://inspect/#remote-debugging`. Chrome asks "Allow remote debugging?" each time browser-harness makes a new connection. A window of the Chrome profile signed in to LinkedIn must be open. Problems appear on the LinkedIn source line, and the other sources continue.

**What it does.**
- **Opens a tab in the signed-in profile.** The runner finds that profile by the presence of its LinkedIn session cookie and never reads the value. Chrome's DevTools protocol opens new tabs only in Chrome's default profile, so the tab is opened from a visible tab of the signed-in profile, the way a link opens one. It appears in that window during the search and closes afterwards.
- **The tab opens on the search, and Jev confirms it.** The query is your keywords (up to three, joined with OR) or the preset's (`backend engineer` for broad), plus `remote` when Remote only is on. The location is Romania (`JOBS_LINKEDIN_LOCATION`). Since October 2026 LinkedIn's search page is `/jobs/search-results/`, with one "Descrieți jobul dorit" (Describe the job you want) box and the location as a button. The page takes the location only from `geoId` (`GEO_IDS` in `linkedin.py`; Romania is 106670623), and a typed search reuses the location last searched on the account. So the tab starts at `/jobs/search-results/?keywords=…&geoId=106670623`, and the agent only types the search if the box does not hold it. The agent sets no LinkedIn filters, because in the 12 Oct trials it lost its way in the filter menus. Remote and age come from each job's details instead.
- **Code checks every action the agent chooses, before it runs.** Refused, matched on English and Romanian labels: Apply and Easy Apply, Save, dismissing a job, Share, Message, Follow, Connect, job alerts and every switch, job preferences, settings and sign-out. The run also stops if the tab leaves `linkedin.com/jobs`. Limits are 16 executed actions, 40 model decisions and 150 seconds.
- **Code waits for each page to settle.** Before every decision it waits until jev's page marker holds still for a second; LinkedIn keeps re-rendering for about four seconds after each load. If the same target is reported covered twice, code presses Escape, which closes LinkedIn's suggestion list. A fourth stale result in a row stops the run.
- **Checks the result.** After the agent says it is done, code checks that the page is a `/jobs/search` or `/jobs/search-results` page for the requested keywords in Romania. Another `geoId` is an error, not a warning. Job ids come from the cards' `job-card-component-ref-<id>` keys on the new page, or from the older page's `data-occludable-job-id`.
- **Reads up to 25 listed jobs.** It uses the JSON endpoint LinkedIn's own job page calls, which returns English title, company, location, workplace type, listing date, employment type and description even though the profile's interface is Romanian. The workplace type is appended to the location, for example "EMEA (Remote)", so the remote and eligibility rules apply.

**Cost and limits.**
- An uncached search makes about three TypeSafe requests on jev's key and one Codex request on your ChatGPT sign-in, for the typed keywords.
- **Options → Job sources** shows the usage under the LinkedIn and Glassdoor switches: the last agent run's site and TypeSafe requests, input tokens and cost, then the last 30 days and all time. The runner adds each run's usage to its result, including failed runs that reached the agent; stale decisions count, because each one is a request. The service keeps it in gitignored `backend/jev-usage.json` (`JOBS_JEV_USAGE_FILE`; the last 500 runs plus running totals) and serves it at `GET /jev/usage` (`/linkedin/usage` stays for older builds). Each run records its site, and the totals cover both sites. TypeSafe reports tokens, not dollars, and its docs publish no price, so dollars are estimated at $0.042 per million input tokens (output is free), the rate third-party listings gave in October 2026. Set `JOBS_JEV_PRICE` if that changes. Field text through Codex runs on the subscription, so it has no dollar cost; through an API, OpenRouter's reported `cost` is added. A run killed by the 240-second backstop records nothing.
- Results are cached for an hour, like other sources. A cached result runs no agent and costs nothing.
- LinkedIn's terms forbid automated access. This uses your own account at personal volume, but LinkedIn can still restrict accounts it flags.

**Switching it off.** Turn off **Options → Job sources → LinkedIn** (on by default; saved on the phone), or set `JOBS_LINKEDIN=off` on the service. LinkedIn alone counts as an enabled source. `/health` reports `linkedin_available`, and **Test connection** says whether the LinkedIn agent is ready. Build 29863531 has the switch and the summary line "Adzuna + LinkedIn + 8 remote boards"; checked on the emulator, and `test/ranking_options_test.dart` covers it.

**Diagnosis.** Run it by hand with the request printed by `linkedin.request` plus a `goal`:

```sh
cd ~/Documents/jev-ultrafast && .venv/bin/python -I ~/Documents/jobs-manager/backend/linkedin_jev.py < request.json
```

The printed JSON adds `decided` (each decision) and `trace` (each executed action).

**Checked on 12 Oct 2026.** The live run typed `backend engineer remote` and clicked Search. That took 2 actions and 3 model decisions, 31 seconds in all, and returned 25 jobs. Through the service's own path, with LinkedIn as the only source and AI ranking off, 12 of the 25 passed ranking: all remote, open to Romania and posted in the last 30 days. Proxify's role came last with its applied badge. A repeat search came from the cache in 0.1 s. `backend/tests/test_linkedin.py` covers the guard, the goal, the result check, the subprocess contract and the agent loop, all with fakes.

**Checked on 22 Oct 2026, after LinkedIn's new search page.** Before the fix, the agent typed into the new box, found the location button covered twice and gave up ("could not complete the LinkedIn search"). Starting on the search URL, the run took one decision (DONE) and no actions, and returned 25 jobs in Romania with no warnings.

## Glassdoor (jev-ultrafast browser agent)

Glassdoor has no public API, and its job listings now come from Indeed. Every search also asks Glassdoor, after LinkedIn, the same way: the jev-ultrafast agent types the search, and code reads the jobs. It adds about a minute, most of it spent reading each role's page.

**Setup.** As for LinkedIn: the same jev-ultrafast install and `.env`, Chrome with remote debugging allowed, and a window of the Chrome profile signed in to LinkedIn. Glassdoor runs in that profile too (on 12 Oct it was also signed in to Glassdoor), because the runner finds the job-hunting profile by its LinkedIn session cookie. The service runs `backend/glassdoor_jev.py`. The shared parts live in `backend/jev.py` (service side: the subprocess contract, the environment scrub and the usage count) and `backend/jev_runner.py` (in jev's virtualenv: the profile tab, the settle wait and the checked agent loop).

**What it does.**
- **Jev types the search** at `glassdoor.com/Job`: the first of your keywords (Glassdoor's title field takes one phrase, not LinkedIn's OR) or the preset's, plus `remote` when Remote only is on, in Romania. Picking Romania from the location suggestions runs the search, so code ends the run as soon as the tab shows the requested search page. Otherwise the agent kept looking for a Search button that was covered.
- **Code checks every action before it runs.** Refused: Apply and Easy Apply, Save, Hide and Not interested, Share, Message, Follow, job alerts, reviews and salaries (the "give to get" wall), Tailor my resume and resume uploads, AI insights, "Let employers find and reach out to you", Glassdoor Recruiter, profile, preferences, settings and sign-out, plus every switch and checkbox. The run stops if the tab leaves `glassdoor.com/Job`. The limits are LinkedIn's: 16 actions, 40 decisions, 150 seconds.
- **Checks the result** from the search page's URL, `/Job/romania-backend-engineer-remote-jobs-SRCH_IL.0,7_IN203_KO8,31.htm`. Its `IL` and `KO` spans name the location and keyword parts of the slug, and both must match the request. The slug keeps the keywords' case and punctuation (`romania-Node.js-backend-remote-…`). Until 22 Oct 2026 the check accepted only lowercase letters, so the backend preset failed with "ended on a page that does not show the requested search" even on the right page. The fixed run took 4 actions and returned 23 jobs.
- **Reads up to 25 listed jobs.** For each card it fetches the role's Glassdoor page inside the signed-in tab, about 1 s each with a 0.3 s pause, and reads the page's schema.org `JobPosting`: title, company, location, posting date, employment type, description, whether it is remote (`TELECOMMUTE`), and where applicants may live. For remote roles, that country list becomes an explicit restriction, as Himalayas' does, so a US-only remote role is dropped and a Romania one kept. If Glassdoor refuses detail reads, the rest keep only their card (title, company, location, salary), and the source line says so.

**Cost.** About three TypeSafe requests (roughly 15,000 input tokens, about $0.0006 at the estimated rate) and two Codex requests per uncached search. These are counted in the same usage log as LinkedIn and tagged `glassdoor`. Results are cached for an hour. Glassdoor's terms also forbid automated access; this is your own account at personal volume.

**Switching it off.** **Options → Job sources → Glassdoor** (on by default), or `JOBS_GLASSDOOR=off` on the service. Glassdoor alone counts as an enabled source. `/health` reports `glassdoor_available`, and **Test connection** says whether the Glassdoor agent is ready.

**Diagnosis.** Same as LinkedIn, with the request from `glassdoor.request`:

```sh
cd ~/Documents/jev-ultrafast && .venv/bin/python -I ~/Documents/jobs-manager/backend/glassdoor_jev.py < request.json
```

**Checked on 12 Oct 2026.** The first live run typed the keyword and the location and picked Romania, which ran the search. It then stopped at the agent's fourth stale "Search", which led to the search-page stop above. The second run took 3 actions, 3 decisions, 54 s and returned 25 jobs, all with descriptions and dates. Through the restarted service, a Glassdoor-only search with AI ranking off took 57 s: 25 fetched, 2 hidden as already applied (Modash, Resourceful Talent Group), 9 shown, all located in Romania and posted within 30 days. `backend/tests/test_glassdoor.py` covers the guard, the request and goal, the URL check, the JobPosting conversion, the subprocess contract and the engine order. The LinkedIn tests now run the shared loop.

## Options and behavior

- Defaults from your October 9 cv-refactor preferences: fully remote, Romania/Europe/worldwide eligibility, contracts first, backend/AI/Python/Go focus. Since 7 November, hybrid roles in Romania and Malta as well.
- Presets: Node.js/TypeScript backend; broader backend and AI; gaming with studio boards.
- Custom comma-separated skills replace the preset's core matching terms. They also customize Adzuna and Himalayas queries; other feeds are filtered after collection.
- LinkedIn is on by default (see above). Enable Adzuna and individual remote boards: Remotive, Remote OK, Himalayas, Jobicy, Working Nomads, Arbeitnow, Hacker News. Gaming additionally uses the reference's Greenhouse, Lever, Ashby, SmartRecruiters, Workable, and Teamtailor studio lists.
- Select Adzuna search markets, maximum posting age, confirmed-contract-only, contract preference, remote-only, and eligibility scope.
- **Hybrid roles in Romania and Malta** come beside the remote ones (both on by default; the chips under **Fully remote only** switch each country off). See the next section.
- Eligibility is inferred from source location fields and selected explicit restrictions, not verified work authorization. Explicit country lists take priority; timezone compatibility alone does not establish Romania eligibility. Confirm restrictions in the original posting.
- Matching uses the reference's weighted keyword rules, excludes unsuitable titles, and explains matched core skills. Scores are points, not percentages or model confidence. Only the LinkedIn source uses Jev, to type the search; nothing applies to jobs automatically.
- Deduplication combines equal company/title/location records and retains source attribution. Different location variants remain separate.
- The **Returned by** dropdown under the results search narrows Discover, Saved and Dismissed to the roles one source returned, listing each source with its count in the current view, most first. A role merged from several sources counts for each of them. The choice holds across tabs until you pick **All sources**; it is not saved between launches. The Applied tab has no source filter. Checked on the emulator (build 29859420): with the 79 cached roles, the menu listed We Work Remotely 29, Jobicy 24, Hacker News 10, Remotive 7, Himalayas 5 and Working Nomads 4. Adzuna, Remote OK and Arbeitnow had no roles in that result set, so they were not listed. Choosing Jobicy showed 24 opportunities, each marked "Jobs by Jobicy".
- Source failures are shown individually. If all fail, the app keeps its previous results. Successful empty searches replace old results. Saved jobs persist independently of search results; dismissing a job removes it from Saved. Restore returns it to Discover. Applied jobs are stored on the service (see above).
- Sources are cached in service memory for one hour to reduce repeated calls; cache clears on service restart. One search runs at a time. Adzuna uses one page per query/country, Himalayas one page per type for up to three queries, and Arbeitnow two pages. This is a bounded search, not exhaustive coverage.
- Searches can take several minutes. The app polls source status. Starting a search with unchanged Options while the service is still searching rejoins that run. The service continues if the phone closes; it does not schedule recurring searches.
- Searches belong to the service, not to a device. The service saves the last finished search in `backend/search.json` (gitignored, owner-only; `JOBS_SEARCH_FILE` overrides), so the phone and every browser show the same results, and a service restart keeps them. A search where every source failed doesn't replace it. Each device keeps a copy so the results still show offline; **Cached** means the copy wasn't confirmed with the service yet.
- Only **Find opportunities** starts a search. Pulling down on Discover, Saved or Dismissed, reloading the website, coming back to the app and launching it only ask the service for its latest search (`GET /search/latest`). If one is running, from this device or another, the app follows its progress; otherwise it shows the last finished one. `?have=<updated_at>` leaves the results out when the device already has them.
- **Cancel search** under the progress bar stops the running search (`POST /search/<id>/cancel`). The service interrupts the browser agent or Claude/Codex ranking call it's waiting on the way Ctrl+C would, so the agent still closes its tab and records its usage. Anything that ignores the interrupt is killed after 10 seconds. A remote-board fetch already in flight finishes first, and then the search stops. The last finished search stays, and a new search can start right away. A search cancelled on another device stops here too.
- In the background, Android pauses the app or cuts its network, so a failed poll waits for the app to come back instead of ending the search. On screen, it gives up after three failed polls in a row. The search carries on on the service, and the next resume or launch follows it again. Verified in `test/background_search_test.dart`.
- App data stays in private Android storage with backup disabled. Service tokens are stored in that private app storage. The service holds fetched listings in memory and saves only the last finished search's results. No analytics are included.

## Hybrid roles in Romania and Malta

Added on 7 November 2026 at the user's request: besides the remote, Romania-eligible roles, a search keeps hybrid roles based in Romania or Malta. The search option is `hybrid`, a list of `romania` and `malta`; app builds older than 29900922 don't send it, so the service uses both.

- **Where they come from.** After its remote search, LinkedIn searches once more per country, for the same keywords plus `hybrid`: Malta first, then Romania, so the account's last searched LinkedIn location stays Romania. Malta's `geoId` is 100961908, checked against LinkedIn's public job search. Glassdoor adds the Romania search only, because Glassdoor lists no jobs in Malta: on 7 Nov 2026 its Malta page (`IN166`) was empty even for "software engineer". Every other source's roles go through the same rule, so a hybrid role in Bucharest from a remote board is kept too. The source list shows each extra search as, for example, "LinkedIn · hybrid in Malta".
- **What counts as hybrid.** The workplace type LinkedIn gives (`(Hybrid)`, `(On-site)`, `(Remote)` after the location) decides. Without one, the title or location must say hybrid (not "hybrid cloud" or "hybrid app"), or the description must describe hybrid work: "hybrid work model", "hybrid (2 days in office)", "Work model: Hybrid", "regim hibrid" and similar. Only the location places the role: Romania by the country or its main cities (Bucharest and Ilfov, Cluj, Iași, Timișoara, Brașov and others), Malta by the country or its business towns (Valletta, Sliema, St Julian's, Gżira, Birkirkara and others). On-site roles and hybrid roles elsewhere are still dropped.
- **How they show.** Their eligibility is `hybrid-romania` or `hybrid-malta`, shown as "Hybrid · Romania" or "Hybrid · Malta", and they rank with the remote, eligible roles. Remote-only and eligibility apply to remote roles only; age, score, contract and applied rules apply to all. The AI ranking is told that hybrid roles in these countries are wanted and that Malta's need not be hireable from Romania; details for a Malta hybrid role leave out the AI's "open to Romania" line.
- **Cost.** About 20–30 s per LinkedIn country and a minute for Glassdoor's Romania search, plus their Jev tokens.

**Checked on 7 Nov 2026.** Live through the new code, LinkedIn's Malta search returned 25 roles in 26 s (18 tagged hybrid) and 8 passed ranking, among them Betsson, Twin Harbour Interactive and Catena Media; Romania's returned 25 in 19 s and 17 passed. Glassdoor's Romania hybrid search returned 25 in 49 s and 11 passed; its Malta page returned none. 286 backend and 66 Flutter tests pass. The website and APK 29900922 were published and the service restarted; no full search ran.

## Development and checks

Flutter and an Android SDK are required. This workspace was built using Flutter 3.47.4, Android API 36, and Homebrew OpenJDK 21.

```sh
flutter pub get
flutter analyze
flutter test
python3 -m unittest discover -s backend/tests -v   # never calls Claude; the AI step uses a fake runner
./scripts/build_apk.sh   # release APK + artifacts/fieldwork.json for in-app updates
```

The backend tests include the original collector regression suite, preference/eligibility cases, caching, partial failures, and actual local HTTP authentication. HTTP tests need permission to open a localhost socket.

Record a feature's checks in that feature's own section, and leave test totals out: the suites report their own counts. Parallel branches that each added a note at the top of **Verification**, or updated one shared totals line, kept conflicting in this file.

The main implementation is in `lib/`, `backend/service.py`, `backend/ai_pick.py`, `backend/claude_chat.py` (the Claude page), `backend/linkedin.py` and `backend/linkedin_jev.py` (LinkedIn), `backend/glassdoor.py` and `backend/glassdoor_jev.py` (Glassdoor), `backend/jev.py` and `backend/jev_runner.py` (what the two browser-agent sources share), `android/app/src/main/kotlin/…/` (`MainActivity.kt` and `InstallStatusReceiver.kt`, the update installer; `Downloads.kt`, which saves the CV; `PdfPages.kt`, which draws PDF pages for the viewer), and `scripts/`. `pubspec.lock` pins Flutter dependencies. `backend/vendor/` contains self-contained copies of the reference collectors; `backend/config/` contains their configs. No external reference checkout is needed at runtime.

## Verification (October 9, 2026)

- Application tracking: a dry run of the Gmail import against a copy of `applied.json` on a temporary instance exposed two migration bugs, both fixed and tested: old entries without `match`, and a duplicate of the migrated confirmation email. A second run changed nothing. The real list then held 16 entries, all with a channel and 2 rejected, Proxify still a badge entry and Jobgether still role-only. On the emulator (build 29859344), the stats matched the data (16 applications, 2 heard back, a 3-day median first reply), and a follow-up date set in the sheet reached the service and was cleared again.
- CV download, emulator (Android 14, build 29859312): `GET /cv` returned the 43,366-byte PDF locally and through the Tailscale address, and 401 without the token. The top-bar button saved `Bogdan-Gherghina-CV.pdf` to Downloads, byte-identical to `cv/`. **Open** showed it in the Drive PDF viewer. A second tap replaced the same file instead of adding a copy.
- Applied jobs, live: on a separate service instance, a Remotive + Himalayas search returned 11 roles. After the first was marked as applied, the same search returned 10 with one left out, and after it was unmarked, 11 again. On the emulator (build 29859265), the check icon moved a role from Discover (79 → 78) to the Applied tab on the real service, and unmarking it there brought Discover back to 79 and emptied the service's list. Both `GET` and `DELETE /applied` also worked through the Tailscale address.
- In-app update, emulator: build 29859242 reported "You have the latest build". After build 29859244 was published, the button offered it and opened the "Install unknown apps" setting once. It then downloaded and verified the build and showed Android's update dialog. After confirming, the device reported versionCode 29859244, and saved results and options were intact. After moving install results to the non-exported receiver, a second pass updated 29859248 → 29859249 the same way, with no logcat crashes or blocked activity launches.
- Claude ranking, live: a default search through the Tailscale address fetched 1,794 listings from nine sources in about 100 seconds. Opus then ranked the top 40 in about 50 seconds on the subscription login, and 79 roles were returned. An emulator search with the same options reused the cached verdicts and finished in 15 seconds. It showed the Claude pills, the top reason on each card, Claude's take in the details sheet and the status line, with no logcat errors.
- Live Adzuna verification fetched 50 listings. Remotive and Himalayas fetched 63 combined.
- A search initiated in the Android emulator called all three selected sources and displayed 12 matching fully remote roles with Romania/Europe/worldwide eligibility. The other adapters have regression coverage but were not all live-tested in this run.
- A second emulator pass covered connection testing, a live search, save/dismiss/restore, persistence across restart, the results filter, and an unreachable service. The rebuilt APK fixed four display issues found in that pass: raw network exceptions, singular counts ("1 opportunity"), the lowercase Adzuna source name, and the source count shown during a search.
- A clean-install retest of the committed APK used the default options and live-tested Adzuna and all eight remote boards: Adzuna 600, Remote OK 414, Jobicy 269, We Work Remotely 142, Hacker News 127, Himalayas 96, Arbeitnow 63, Working Nomads 54 and Remotive 34 listings, giving 80 matching roles in under two minutes. The gaming preset's studio boards were not live-tested.
- Screenshots are in `artifacts/`. No physical phone was connected during verification.

## Reference provenance

- `~/Documents/cv-refactor/job-search/`: Adzuna and remote collectors, matching/scoring, search presets, and tests, copied October 9, 2026. Local adaptations relocate config paths and expose individual studio-board failures to the mobile service, and retain Arbeitnow’s actual location rather than implying Europe-wide eligibility. Original files were not changed.
- `~/Documents/cv-refactor/.cs/memory/user_job_search.md`: default search preferences.
- `~/Documents/cv-refactor/.cs/memory/project_adzuna_keys_wap_ags.md`: exact named secret-store lookup.
- `~/Documents/jev-dating/` and the Codex chat “Explore Jev for automatic swipes”: local preference and choice workflow, duplicate handling, and explicit separation between your decisions and model estimates. The app adopts local save/dismiss decisions without importing dating profiles or credentials.

Provider results remain attributed and link to their original listings. See [Adzuna API](https://developer.adzuna.com/overview), [Himalayas API](https://himalayas.app/api), and [Flutter Android build documentation](https://docs.flutter.dev/deployment/android).

## Daily Gmail sync

The service runs a read-only Gmail sweep every 24 hours, even when the phone is closed. `scripts/sync_gmail.sh` asks the running service to run if due; it cannot force additional subscription requests. The scheduler starts with `scripts/serve.sh`, catches up when the server returns after downtime, and records attempts before contacting the model so restarts or failures cannot create a quota loop. Keep the server running and the Mac awake.

**How it reads Gmail** (since 22 Oct 2026). The service reads the mailbox itself over IMAP with a Google app password, then has the engine and subscription picked in the app's options (Claude or Codex, Personal or Work) sort the emails. That engine is signed in the way ranking is, never with an API key and never through the Mac's live Claude login, so switching the Mac to Work no longer stops the sync. A search uses its own pick; the daily run uses the last search's. Before this, Claude read Gmail through its claude.ai connector, which only the Mac's live Personal login could reach.
- **Setup, once.** Turn on 2-Step Verification for the Google account, create an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), and save it in the login keychain as a password item named `fieldwork-gmail`: `security add-generic-password -s fieldwork-gmail -a your-mailbox@gmail.com -w` (it prompts for the value). `scripts/serve.sh` reads that item at startup (`JOBS_GMAIL_KEYCHAIN_ITEM` names another one; an `imap.gmail.com` internet password also works, and so does the `invoice-script-smtp` item, the same mailbox's app password used by the invoice script) and passes it to the service as `JOBS_GMAIL_APP_PASSWORD`, and the service takes it out of its environment at startup so no child process (the Claude page, ranking, the browser agents) inherits it. Restart the service after storing it. Without it, the sync reports that it needs the password and checks again every 10 minutes.
- **What it reads.** Only All Mail and Spam (found by their IMAP special-use flags, so Gmail's display language doesn't matter), opened read-only with EXAMINE and fetched with `BODY.PEEK`, so nothing is marked read, moved or changed. Gmail's own search (`X-GM-RAW`) narrows the window to job-related mail: application words in English and Romanian, or a known applicant-tracking sender (Ashby, Greenhouse, Lever, Workable, Teamtailor and others). At most 400 emails per sweep, 100 per model request.
- **What the model sees and decides.** Each email's folder (Inbox, Sent or Spam), received time, sender, recipient, subject and the first 800 characters of its text, plus the application list's ids, companies and titles. The subject, sender and that preview go to the picked engine's provider, OpenAI when Codex is picked. The model only says which emails are about an application, their kind, the hiring company (the client, not the job board that reposted it), the role and the matching application. Message and thread ids, dates, senders and subjects come from Gmail, never from the model. Gmail's web and API ids are the IMAP ids in hex, so entries imported by the earlier connector sweeps dedupe with these.

**Every search checks Gmail first** (since 22 Oct 2026). The same sweep starts beside the sources, and before the applied roles are left out and Claude ranks, the search waits up to 3 minutes for it, so an application that only reached your inbox is left out of that search. A sweep that started in the last 15 minutes, by a search or the daily schedule, is reused, failed ones included, so repeated searches don't spend a subscription request each. A search's sweep counts as the daily one. It skips the 10-minute retry wait after a missing password or login: when the check can't run, the search goes ahead with the list as it was. A line under the results says what the check found and with which engine, or why it failed (in orange). A sweep still running after the wait finishes in the background for the next search, and cancelling a search doesn't stop it.

Configuration lives in private, gitignored `backend/gmail-sync-config.json`:

```json
{
  "mailbox": "your-personal-mailbox@gmail.com",
  "enabled": true
}
```

Optional `start_after` is an ISO timestamp for the first run. Keys the connector sweeps used (`claude_account_email`, `claude_org_id`, `model`) are ignored. The first sweep ran at **22:25 Europe/Bucharest on October 9, 2026**. Subsequent runs are 24 hours apart. Disabling `enabled` takes effect without a restart.

- The model request is ranking's: no tools, no user or project settings, inherited API keys and billing overrides stripped, and the subscription never switched automatically. If the picked login isn't available on the service computer (for example Codex Work without its own ChatGPT login), the job stops before reading mail. That attempt doesn't count toward the daily schedule, and the job checks again every 10 minutes. Email content is treated as untrusted data.
- The first sweep covers 30 days. Later sweeps start two days before the last successful sweep, catching delayed indexing and outages. A refused password, a failed IMAP read, more than 400 emails or invalid model output leave the list unchanged and report an error.
- **Matching an email to an application.** By the application the model names, else within the same company by thread, then by exact title. A reply whose company has no entry also matches through its thread, or through an earlier email that names the sender about the same role. Job boards and agencies write under another name than the listing's: Micro1's replies belong to a role saved as Xperteez Technology, whose confirmation came from Dover with "Micro1" in the subject. Only replies link across names; a confirmation from a new company starts its own entry.
- **Replies that can't be placed wait instead of blocking the sync** (since 7 Nov 2026). A reply with no matching application (a company that sent no confirmation, an application never recorded), or one that matches several, is set aside with its reason, and the rest of the sweep imports. Until then one such email held back every import: a Micro1 reply stopped the sync from 22 Oct to 7 Nov. Set-aside replies are kept in the state file (headers and classification only, up to 50, for 30 days) and tried again by every sweep, so adding the application in the app is enough; the next check attaches the email. The search's Gmail line and the Applied tab name them.
- Imports preserve manual notes, follow-up dates and company matching preferences. Message IDs prevent duplicates; earlier messages cannot replace newer statuses. A validation pass against an in-memory copy precedes one atomic write, with a private `backend/applied.json.before-gmail` backup. The list retains its existing limit of 100 email summaries per application; full email bodies are not saved by the app. Classification is inferred by the model and should be checked against email when a status looks wrong.
- `GET /applied` includes `gmail_sync` status alongside the list. `GET /gmail-sync` reports the last attempt, last success, next run and any error. Authenticated `POST /gmail-sync` or `./scripts/sync_gmail.sh` starts a due check without waiting for the model. `backend/gmail-sync-state.json` is private and must be retained across restarts.
- The Applied tab's analytics download the saved application list once per 24 hours, on app launch/resume or while open. The fetch timestamp and data are cached across restarts; offline failures retain the last data and retry at most hourly while open. Pull to refresh fetches immediately, without spending an LLM request. A mark beside the status line turns green after a successful refresh with a healthy Gmail sync. It turns red when the refresh or the server's Gmail sync failed, and shows a sync icon while Gmail is being checked. The line also shows when the app last refreshed. Android does not need to run a background Gmail job.

Verification: 186 backend tests and 38 Flutter tests pass; Flutter analysis is clean. Coverage includes daily cadence/restarts, locking, subscription selection, tool restrictions, failure recovery, duplicate imports, atomic writes, authenticated endpoints and daily UI caching. Build 29859405 is published; the active schedule and APK metadata were verified through localhost and the phone’s Tailscale address. The restricted runtime successfully loads the Gmail connector. The first live model check reached the Claude subscription limit; a successful live Gmail import is still pending the scheduled run.
