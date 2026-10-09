# Fieldwork — Android jobs manager

A personal Android app that combines **Adzuna** and the **remote-job search pipeline from cv-refactor**, with editable options, matching explanations, saved/dismissed jobs, and offline access to the last completed search.

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

## App updates

**Options → App updates → Check for app update** asks the service for the build in `artifacts/fieldwork.apk`. If that build is newer than the installed one, **Install build N** downloads it with the access token, checks its SHA-256 against the service, and hands it to Android's package installer. Confirm Android's "update this app" dialog, then open Fieldwork again. Saved jobs and settings are kept.

- Publish a build with `./scripts/build_apk.sh`. It builds the release APK with the build number set to minutes since 1970, so every build is newer than the last. It writes `artifacts/fieldwork.apk` and `artifacts/fieldwork.json`. The running service picks both up without a restart.
- The first time, Android asks you to allow Fieldwork to install apps. Fieldwork opens that setting; switch it on, come back and tap Install again.
- Builds from before this feature (build 1) cannot update themselves. Install one updater build manually first.
- `GET /app` reports the published build. `GET /app/fieldwork.apk` serves it. Both need the access token. The APK contains no credentials or tokens.
- The installer's result goes to `InstallStatusReceiver`, which is not exported. Other apps cannot fake it. The receiver only acts on install sessions Fieldwork created. It only opens Android's own install confirmation (`CONFIRM_INSTALL`), with any file-access grants removed.

## Your CV

The document icon in the top bar, next to the options icon, saves your CV from the service to the phone's **Downloads** folder, so job application forms can attach it from there. The snackbar's **Open** shows it in the phone's PDF viewer.

- The service serves the newest PDF in `cv/` at the repository root. Git ignores that folder because the CV carries your contact details. `JOBS_CV_DIR` points elsewhere. The file keeps its name on the phone, so name it the way recruiters should see it. On October 9, 2026, `Bogdan-Gherghina-CV.pdf` was moved there from `~/Documents/cv-refactor/`.
- To update the CV, replace the PDF in `cv/`; no restart is needed. cv-refactor's `latex/build.sh` still writes its output to `~/Documents/cv-refactor/Bogdan-Gherghina-CV.pdf`, so copy a rebuilt CV into `cv/` yourself.
- Saving again replaces the copy Fieldwork saved before rather than adding "CV (1).pdf". If another app already put a file with that name in Downloads, Android saves Fieldwork's copy under a numbered name, and the snackbar shows that name.
- `GET /cv` returns the PDF with its file name and needs the access token. Saving uses Android's MediaStore, so it needs no storage permission. It requires Android 10 or newer; older phones get a message instead.

## Claude ranking

With **Let Claude rank the top roles** on (the default), the service sends the top 40 keyword matches to Claude Code on the Mac after fetching. Claude Code runs headless (`claude -p`) under your Claude login, so it uses your Claude subscription, not an API key. Claude returns a 0–100 fit, apply/maybe/skip, its own reading of Romania eligibility, and short reasons and concerns. Ranked roles come first, ordered by verdict and fit. The rest follow in keyword order.

- Claude must be installed and signed in on the Mac (`claude` on the service's `PATH`). **Test connection** reports whether it was found.
- Your profile is read from `backend/profile.md`, which git ignores. `JOBS_PROFILE_FILE` points elsewhere. Without a profile, Claude judges against the app's preferences only.
- `JOBS_AI_MODEL` (default `opus`), `JOBS_AI_EFFORT` (default `medium`) and `JOBS_AI_LIMIT` (default `40`) tune the call. Descriptions are cut to 1,500 characters per listing.
- The call has no tools, MCP servers, user settings, hooks or saved session. It runs in an empty temporary folder. It drops `ANTHROPIC_API_KEY` and Claude Code session variables from its environment, so a key exported in your shell cannot redirect it to API billing.
- Verdicts are cached in service memory per listing, profile and preferences, so a repeated search only sends new listings. A live run of 40 listings with Opus took about 50 seconds.
- If Claude fails (not installed, signed out, usage limit, timeout), the search still completes with keyword ranking, and the app says why.
- Your profile and the listings are sent to Anthropic, as in any Claude conversation. Claude's eligibility reading comes from listing text, like the keyword labels; confirm with the employer.

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

## Options and behavior

- Defaults from your October 9 cv-refactor preferences: fully remote, Romania/Europe/worldwide eligibility, contracts first, backend/AI/Python/Go focus.
- Presets: Node.js/TypeScript backend; broader backend and AI; gaming with studio boards.
- Custom comma-separated skills replace the preset's core matching terms. They also customize Adzuna and Himalayas queries; other feeds are filtered after collection.
- Enable Adzuna and individual remote boards: Remotive, Remote OK, Himalayas, Jobicy, Working Nomads, We Work Remotely, Arbeitnow, Hacker News. Gaming additionally uses the reference's Greenhouse, Lever, Ashby, SmartRecruiters, Workable, and Teamtailor studio lists.
- Select Adzuna search markets, maximum posting age, confirmed-contract-only, contract preference, remote-only, and eligibility scope.
- Eligibility is inferred from source location fields and selected explicit restrictions, not verified work authorization. Explicit country lists take priority; timezone compatibility alone does not establish Romania eligibility. Confirm restrictions in the original posting.
- Matching uses the reference's weighted keyword rules, excludes unsuitable titles, and explains matched core skills. Scores are points, not percentages or model confidence. No Jev calls or automatic applications are made.
- Deduplication combines equal company/title/location records and retains source attribution. Different location variants remain separate.
- Source failures are shown individually. If all fail, the app keeps its previous results. Successful empty searches replace old results. Saved jobs persist independently of search results; dismissing a job removes it from Saved. Restore returns it to Discover. Applied jobs are stored on the service (see above).
- Sources are cached in service memory for one hour to reduce repeated calls; cache clears on service restart. One search runs at a time. Adzuna uses one page per query/country, Himalayas one page per type for up to three queries, and Arbeitnow two pages. This is a bounded search, not exhaustive coverage.
- Searches can take several minutes. The app polls source status. Leaving Options unchanged and retrying while the service is still searching rejoins that run. The service continues if the phone closes; it does not schedule recurring searches.
- App data stays in private Android storage with backup disabled. Service tokens are stored in that private app storage. The service holds fetched listings in memory. No analytics are included.

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

The main implementation is in `lib/`, `backend/service.py`, `backend/ai_pick.py`, `android/app/src/main/kotlin/…/` (`MainActivity.kt` and `InstallStatusReceiver.kt`, the update installer; `Downloads.kt`, which saves the CV), and `scripts/`. `pubspec.lock` pins Flutter dependencies. `backend/vendor/` contains self-contained copies of the reference collectors; `backend/config/` contains their configs. No external reference checkout is needed at runtime.

## Verification (October 9, 2026)

- 141 Python tests and 31 Flutter tests passed; `flutter analyze` reported no issues.
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
