---
name: project-fieldwork
description: Fieldwork Android app scope, reference provenance, service dependency, and Adzuna credential routing.
type: project
---

The user explicitly confirmed that “both sources” means the two cv-refactor pipelines: Adzuna and its collection of remote-job boards. It does not mean Tinder/Bumble or only two job websites. The jev-dating reference supplies the local preference/choice workflow; no dating data or Jev calls belong to this app's current scope.

Fieldwork is a Flutter Android client plus a self-contained Python service. The collectors and configs are copied into `backend/`; the original references are not runtime dependencies. Fetching requires the service; saved jobs and cached results work offline. USB testing uses `adb reverse tcp:8765 tcp:8765`. Untethered hosting has not been provisioned. Android permits plain HTTP only for loopback and the emulator host; hosted connections require HTTPS.

The Adzuna keys belong to the `wap-ags` secret store, not cv-refactor. `scripts/serve.sh` resolves the two exact named credentials with `CS_SECRETS_SESSION=wap-ags`, or uses environment values; `JOBS_SECRETS_SESSION` overrides the store. Merely changing directories is unreliable because an inherited CS_SECRETS_SESSION can select a different store. Never put the credential values or the local service access token into handoff files or APKs.

Romania eligibility is inferred, not a verified hiring guarantee. Explicit country lists override broad labels; timezone compatibility does not establish eligibility. The copied Arbeitnow collector was corrected to retain its actual location rather than add Europe-wide eligibility. Keep those distinctions when changing filters.

The default personal preferences are inherited from cv-refactor's `user_job_search.md`: fully remote, Romania eligible, contracts preferred, broader backend/AI/Python/Go interest. Full implementation and verification details belong in the project README and summary rather than this memory.
