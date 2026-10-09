# Fieldwork — Android jobs manager

A personal Android app that combines **Adzuna** and the **remote-job search pipeline from cv-refactor**, with editable options, matching explanations, saved/dismissed jobs, and offline access to the last completed search.

## Install and connect

The recommended ARM64 APK is `artifacts/fieldwork.apk`, compiled in release mode and signed with the local development key for personal installation. It is not configured for Play Store publication. An unoptimized debug APK is also at `artifacts/fieldwork-debug.apk`. The app was built and launched on an Android 14 emulator.

The app uses a small Python service on your computer. Keep that service running while fetching jobs; saved jobs and the last results remain available offline. The phone does not need your Adzuna credentials.

1. Start the service from this directory:
   ```sh
   ./scripts/serve.sh
   ```
   Python 3.10+ is required; there are no third-party Python dependencies. The launcher uses `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` from the environment, or retrieves those exact names from the `wap-ags` secret store documented in cv-refactor. Override the store with `JOBS_SECRETS_SESSION`. Missing credentials leave Adzuna visibly unavailable while remote boards continue.
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

For an emulator, the same `adb reverse` works, or use `http://10.0.2.2:8765`. For untethered use, deploy the service behind HTTPS and enter that URL. Hosting is not provisioned by this project. HTTP is allowed only for localhost and the emulator host; arbitrary LAN HTTP is intentionally not enabled. The default service binds only to localhost. An HTTPS reverse proxy can forward to it. `JOBS_ACCESS_TOKEN` can supply a persistent token instead of the local file.

## Options and behavior

- Defaults from your October 9 cv-refactor preferences: fully remote, Romania/Europe/worldwide eligibility, contracts first, backend/AI/Python/Go focus.
- Presets: Node.js/TypeScript backend; broader backend and AI; gaming with studio boards.
- Custom comma-separated skills replace the preset's core matching terms. They also customize Adzuna and Himalayas queries; other feeds are filtered after collection.
- Enable Adzuna and individual remote boards: Remotive, Remote OK, Himalayas, Jobicy, Working Nomads, We Work Remotely, Arbeitnow, Hacker News. Gaming additionally uses the reference's Greenhouse, Lever, Ashby, SmartRecruiters, Workable, and Teamtailor studio lists.
- Select Adzuna search markets, maximum posting age, confirmed-contract-only, contract preference, remote-only, and eligibility scope.
- Eligibility is inferred from source location fields and selected explicit restrictions, not verified work authorization. Explicit country lists take priority; timezone compatibility alone does not establish Romania eligibility. Confirm restrictions in the original posting.
- Matching uses the reference's weighted keyword rules, excludes unsuitable titles, and explains matched core skills. Scores are points, not percentages or model confidence. No Jev calls or automatic applications are made.
- Deduplication combines equal company/title/location records and retains source attribution. Different location variants remain separate.
- Source failures are shown individually. If all fail, the app keeps its previous results. Successful empty searches replace old results. Saved jobs persist independently of search results; dismissing a job removes it from Saved. Restore returns it to Discover.
- Sources are cached in service memory for one hour to reduce repeated calls; cache clears on service restart. One search runs at a time. Adzuna uses one page per query/country, Himalayas one page per type for up to three queries, and Arbeitnow two pages. This is a bounded search, not exhaustive coverage.
- Searches can take several minutes. The app polls source status. Leaving Options unchanged and retrying while the service is still searching rejoins that run. The service continues if the phone closes; it does not schedule recurring searches.
- App data stays in private Android storage with backup disabled. Service tokens are stored in that private app storage. The service holds fetched listings in memory. No analytics are included.

## Development and checks

Flutter and an Android SDK are required. This workspace was built using Flutter 3.47.4, Android API 36, and Homebrew OpenJDK 21.

```sh
flutter pub get
flutter analyze
flutter test
python3 -m unittest discover -s backend/tests -v
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home flutter build apk --release --target-platform android-arm64
```

The backend tests include the original collector regression suite, preference/eligibility cases, caching, partial failures, and actual local HTTP authentication. HTTP tests need permission to open a localhost socket.

The main implementation is in `lib/`, `backend/service.py`, and `scripts/serve.sh`. `pubspec.lock` pins Flutter dependencies. `backend/vendor/` contains self-contained copies of the reference collectors; `backend/config/` contains their configs. No external reference checkout is needed at runtime.

## Verification (October 9, 2026)

- 110 Python tests and ten Flutter tests passed; `flutter analyze` reported no issues.
- Live Adzuna verification fetched 50 listings. Remotive and Himalayas fetched 63 combined.
- A search initiated in the Android emulator called all three selected sources and displayed 12 matching fully remote roles with Romania/Europe/worldwide eligibility. The other adapters have regression coverage but were not all live-tested in this run.
- A second emulator pass covered connection testing, a live search, save/dismiss/restore, persistence across restart, the results filter, and an unreachable service. The rebuilt APK fixed four display issues found in that pass: raw network exceptions, singular counts ("1 opportunity"), the lowercase Adzuna source name, and the source count shown during a search.
- Screenshots are in `artifacts/`. No physical phone was connected during verification.

## Reference provenance

- `~/Documents/cv-refactor/job-search/`: Adzuna and remote collectors, matching/scoring, search presets, and tests, copied October 9, 2026. Local adaptations relocate config paths and expose individual studio-board failures to the mobile service, and retain Arbeitnow’s actual location rather than implying Europe-wide eligibility. Original files were not changed.
- `~/Documents/cv-refactor/.cs/memory/user_job_search.md`: default search preferences.
- `~/Documents/cv-refactor/.cs/memory/project_adzuna_keys_wap_ags.md`: exact named secret-store lookup.
- `~/Documents/jev-dating/` and the Codex chat “Explore Jev for automatic swipes”: local preference and choice workflow, duplicate handling, and explicit separation between your decisions and model estimates. The app adopts local save/dismiss decisions without importing dating profiles or credentials.

Provider results remain attributed and link to their original listings. See [Adzuna API](https://developer.adzuna.com/overview), [Himalayas API](https://himalayas.app/api), and [Flutter Android build documentation](https://docs.flutter.dev/deployment/android).
