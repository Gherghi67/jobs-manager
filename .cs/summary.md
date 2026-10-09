# Fieldwork Android jobs app — handoff

## Objective

Build an Android app fetching and filtering jobs using the jev-dating project and cv-refactor session as references. The user confirmed the two sources are **Adzuna and cv-refactor's remote-job-board pipeline**. This implementation was completed on October 9, 2026; this wrap preserves its state. No further feature request is pending.

## Environment

- Workspace: `/Users/bogdan.gherghina/Documents/jobs-manager`.
- No Git repository, branch, commits, or PR exists. There was no previous `.cs` history or timeline; this wrap creates local handoff records without registering a CS session.
- Flutter 3.47.4 / Dart 3.13.3, Android API 36 build toolchain, Homebrew OpenJDK 21. Verified on `Pixel_7_API_34_arm64` emulator (Android 14).
- Backend: Python standard library, Python 3.10+ required.
- At implementation completion the local service was running at `http://127.0.0.1:8765`, with Adzuna configured; emulator `emulator-5554` was running with ADB reverse on port 8765. Check liveness before reuse.
- No `CLAUDE_CODE_SESSION_ID` was present during wrap; do not invent a marker/session ID.

## Key Discoveries

- Job defaults from cv-refactor: fully remote, eligible from Romania, contracts preferred, broader backend/AI/Python/Go interests, with a gaming preset available.
- Adzuna credentials live in the `wap-ags` ags store. The launcher must specify `CS_SECRETS_SESSION` explicitly; changing directory alone is insufficient. No credential values were copied into code or handoff records.
- The jev-dating reference informs local preference/choice handling. This app does not read dating profiles, call Jev, or submit applications.
- A source location or explicit country list is needed for eligibility; a compatible timezone does not establish it. Arbeitnow's inherited generic Europe prefix was removed so narrower locations are retained.

## Changes Made

- Flutter client with Discover, Saved, Dismissed, job-detail, and Options screens; original listing links; match reasons; salaries; attribution; persistent choices and cached results.
- User controls for individual sources, role presets, custom core skills, Adzuna countries, age, remote-only, eligibility scope, contract-only, and contract-first ranking.
- Authenticated asynchronous HTTP service that runs copied reference collectors, reports source progress and failures, merges duplicates by company/title/location, and caches sources for an hour.
- Self-contained copies of the cv-refactor collectors/configs/tests; corrected config locations, studio failure reporting, and Arbeitnow location handling. Original reference files were unchanged.
- Private Android storage with backup disabled. Provider keys stay in the service; app token is separate. HTTP is allowed only for loopback and the emulator host; other deployments need HTTPS.
- Local launcher `scripts/serve.sh`, Android app metadata/icon/network config, tests, and README.

## Key Files & Outputs

- `lib/main.dart`: UI, saved/dismissed state, preferences, search polling.
- `lib/api.dart`, `lib/models.dart`: service client and shared models/defaults.
- `backend/service.py`: API, search engine, filtering, cache.
- `backend/vendor/`, `backend/config/`: reference collectors and presets.
- `scripts/serve.sh`: backend launch and exact named Adzuna credential retrieval.
- `backend/tests/`, `test/`: 110 Python tests and six Flutter tests.
- `artifacts/fieldwork.apk`: recommended optimized ARM64 APK, 18.4 MB build output, signed with the local development key.
- `artifacts/fieldwork-debug.apk`: earlier debug build, approximately 146 MB. Use the optimized APK for installation; the earlier debug build predates the final icon/network-attribute adjustments.
- `artifacts/android-first-launch.png`, `artifacts/android-live-search.png`, `artifacts/android-results.png`: emulator screenshots.
- `README.md`: installation, service connection, limitations, tests, build commands, and provenance.
- `.cs/memory/project_fieldwork.md`: durable decisions; `.cs/memory/narrative.bogdan-gherghina-erepubliklabs-com.md`: task narrative.

## Outcome

The Android app is built and verified. All **110 Python tests + six Flutter tests** passed; `flutter analyze` reported no issues. Live Adzuna fetched 50 listings; Remotive and Himalayas fetched 63 combined. A search initiated inside the emulator used all three selected sources and returned 12 roles matching the remote/Romania filters. The final optimized APK installed and launched successfully, with no Android runtime crash reported.

The remaining collectors were not all live-tested. No physical phone was connected. Eligibility remains a text-based inference to confirm with the employer. This is a personal-install build, not a Play Store publication.

## Notes for Future Reference

- Start fetching with `./scripts/serve.sh`; connect Android using `adb reverse tcp:8765 tcp:8765`, then configure the service URL and the token from `backend/.access-token` inside Options. Never print or commit that token.
- Service credentials use environment variables first, otherwise exact lookups in `wap-ags`; `JOBS_SECRETS_SESSION` overrides the store.
- Fetching requires a running service. Saved jobs and the last completed search remain offline. Hosting and untethered access have not been deployed.
- The emulator was configured for a bounded TypeScript query with Adzuna, Remotive, and Himalayas during verification. Fresh installs use the broader default profile and eight remote boards.
- APK build: `JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home flutter build apk --release --target-platform android-arm64`.
- No new chat or archive was requested by plain wrap. Runtime processes were not intentionally shut down by wrap.

Wrap status: memory and summary saved. `cs -narrative rotate` was attempted once and exited 1: `Error: cs -narrative rotate must be run from inside a cs session`. This directory is not a CS session, so rotation remains unavailable; narrative content is preserved.
