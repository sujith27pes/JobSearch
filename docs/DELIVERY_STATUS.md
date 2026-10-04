# Delivery status

## Latest verification — 4 October 2026

100 automated tests, TypeScript/Vite production compilation, the 150/150 synthetic scoring benchmark, and browser recruiter workflows pass. The configured NVIDIA endpoint passed authenticated generation and a complete fictional JD/resume/assessment flow (three requests, 3,163 tokens). Tests used isolated databases and no saved candidate data was sent. See `CHANGES-2026-10-04.md` for all edits, validation limits and restart instructions. Older dated entries below describe prior checks.

## Verified in this workspace

- React TypeScript production build passes.
- **71 automated tests pass.** The domain/integration suite covers expiry, status removal, scoring, source references, caches, comparisons, corrections, source permissions, deletion, failed ingestion, worker leases, and safe exports.
- The isolated synthetic benchmark checks 150 criterion outcomes across 30 profiles against predeclared expectations. Results are saved in `benchmark-results.json`. This is a fixture regression check, not proof of AI accuracy or fairness.
- Browser inspection verified jobs, historical candidate filtering, candidate detail, essential-status rendering, selection of two candidates, comparison, and an 80-to-90 gap scenario that leaves the official score at 80. Desktop 1280px and narrow 768px layouts were inspected. The simplified frontend was rebuilt and checked again on 2 October 2026.

## Implemented, requiring deployment-specific validation

- OpenAI-compatible model gateway, schema checks, bounded transient retries, usage accounting and safe errors. Two fictional profiles were tested with the configured Groq endpoint: dated backend duties under Graduate Developer received 48 supported months; the skills/coursework-only case returned unknown duration. This targeted check does not establish general hiring accuracy.
- PDF/DOCX parsing and paragraph/block source references. Complex document-layout quality requires a representative document corpus.
- Configurable pool restrictions. This is a single-user local demo, not authenticated multi-user authorisation.

## Explicitly not production-ready

- No company SSO, live Taleo connection, live employee source, automated outreach or hiring decision.
- No production-scale 100-profile budgeted dispatch, transactional token reservations, distributed worker coordination, encrypted storage, or automated retention erasure.
- No organisational legal compliance claim, independent fairness audit, external identity verification or fraud detection.
- Offline interpretation is a transparent rules preview. AI mode requires measured semantic evaluation before real recruitment.
- Intake permission metadata is trusted locally; an authenticated adapter/admin boundary is required before an enterprise pilot.

## Operational notes

Do not bind the demo API beyond localhost. Keep one worker process. Successful uploaded originals are removed once source text is extracted; failed originals remain for retry until their profile is deleted. The 30 uploaded-profile allowance excludes seeded fictional profiles.

## Recruiter usability revision — 1 October 2026

- Three-step starting guide and explicit next action per job.
- Requirements show plain-language priorities; specialist controls stay collapsed.
- Uploads default to applicants without requiring a manifest.
- Sample candidates have explicit labels; missing evidence has a clarification banner.
- Responsibility-first interpretation instructions, versioned caches, and one-candidate reassessment.
- Browser checked job creation, confirmation, upload dialog, candidate detail, and sample labels in an isolated practice database.
- No real candidate information was sent to the provider during validation.

- Activity uses job names and plain progress labels, with completed history hidden initially.
- Upload dialog resets when reopened. AI-mode queue concurrency is one to reduce free-tier bursts.
- Latest final checks: 71 tests pass, TypeScript/Vite build passes, synthetic benchmark 150/150.

## Interview tracking fix — 2 October 2026

- Interviews is a dedicated sidebar destination, with job, move date, review reason and source.
- Human moves persist the stage and navigate to the interview list. Past applicants stay excluded from rediscovery.
- Existing moves remain visible; job provenance is inferred only when one reviewed job is unambiguous.
- Pool permissions, employee visibility, retention and suppression apply to the interview list.
- Interview metadata survives resume refresh imports.


## Reliability and recruiter insights — 2 October 2026

- All seven reported issues have targeted regression checks. The suite passes 71 tests; TypeScript/Vite production compilation and the 150/150 synthetic fixture benchmark pass.
- A genuine request to the configured NVIDIA Nemotron 3 Ultra 550B endpoint passed a fictional JD/resume/assessment flow: three requests, 3,444 tokens. A Graduate Developer with dated backend duties received full documented credit. This validates this case and connectivity, not general hiring quality.
- Three-candidate differences, resume replacement, identical upload reuse, cache survival, ingestion stages, saved-date scoring, calendar cache refreshes and source restrictions are covered by tests.
- Descriptive title transitions, explicit promotion intervals, short completed-role context, first-class skill freshness, cross-job exploration and aggregate monitoring are implemented.
- Monitoring is not demographic adverse-impact analysis. Promotion and tenure insights neither predict performance/flight risk nor change scores.
- NVIDIA requests use a shared gate, conservative pacing, configurable timeouts, explicit non-streaming and no reasoning by default. Mocked tests cover quota cooldown and truncated output rejection. Free service uptime/quota availability remains external.
- Browser validation used a separate synthetic database; the user's real candidate data and existing running service were not modified by the test session.

## Connection diagnostics and activity history — 3 October 2026

- 83 automated tests pass and the TypeScript/Vite production build passes.
- The configured NVIDIA key/model passed a tiny authenticated live test: HTTP 200, 32 tokens, no resume data. The historical cause of the earlier connection failures is not established by this success.
- Activity includes an explicit no-generation reachability check. Command-line network and optional authenticated generation checks load `.env` without starting the application.
- Safe error messages identify available DNS/TLS/network-permission/proxy/refused-connection causes. Verified TLS uses Windows system roots with optional approved PEM augmentation.
- Older failed attempts move into history after a newer attempt supersedes them. Retry rejects superseded profile/rubric attempts. Existing candidate data and API keys were not reset or replaced.
