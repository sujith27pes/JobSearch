# Changelog

This record summarises the implemented changes. Validation evidence and limitations are maintained separately in [VALIDATION.md](VALIDATION.md).

## Live AI demo and duration correction — 9 October 2026

- Calculated general experience across source-linked full role periods in Python instead of accepting the model's month arithmetic. Shorter project estimates remain separate and overlapping roles are merged.
- Replaced duration explanations with the computed period and approved requirement; versioned the interpretation method so earlier results request reassessment.
- Aligned date-only eligibility and scoring with local rejection/import dates, fixing same-day rejection immediately after local midnight. Audit timestamps remain UTC.
- Added regression coverage for wrong model arithmetic, overlapping periods, incomplete dates, shorter projects, skill tenure and the local/UTC midnight boundary.
- Captured seven authentic AI-mode demo screenshots using fictional candidates in an isolated database, added a captioned gallery, and linked the contextual-matching example from the README.

## Submission preparation — 8 October 2026

- Rewrote the README around the problem, recruiter workflow, score explanation and reproducible setup.
- Added a development prompt record with provenance labels and exact runtime templates.
- Added the missing safe environment template and expanded generated/private-file exclusions.
- Consolidated overlapping delivery notes, retained the architecture reference, and removed build/test caches.
- Rechecked the backend suite, synthetic benchmark and frontend compilation/build.

## Workspace and recruiter improvements — 4 October 2026

- Removed bundled jobs/profiles from the working workspace and disabled automatic startup seeding. Isolated test fixtures remain available to the test suite and benchmark.
- Added explicit rejection with a reason, original-job provenance and preserved rejection dates. Rejected profiles can qualify for other jobs under the existing rediscovery rules.
- Added a keyboard-accessible light/dark switch, system preference support, saved browser preference and theme coverage across screens.
- Corrected active-run reuse so a request is satisfied only when the run includes the requested eligible profile versions.
- Allowed authorised requests to queue behind other work; kept bounded worker concurrency and duplicate-exploration protection.
- Added per-file upload savepoints, stricter manifest validation, deletion/run reconciliation and current-attempt retry checks.
- Fixed draft revision tracking, unsaved-edit preservation, overlap acknowledgement, comparison selection and stale dialog state.
- Kept fast polling during ingestion and added launcher startup/health/process cleanup checks.

## Connectivity and processing history — 3 October 2026

- Added explicit provider reachability diagnostics and an optional small authenticated test.
- Added sanitised DNS, certificate, proxy and network failure explanations with verified TLS.
- Separated older failed attempts from actionable current attempts; prevented retrying superseded inputs.

## Matching reliability and recruiter insights — 2 October 2026

- Added resume replacement and identical-upload reuse without name-based identity merging.
- Preserved shared extraction caches and local interview metadata during source updates.
- Added saved evaluation dates, conservative duration/recency handling and monthly arithmetic refreshes.
- Added all-pairs differences for three-candidate comparison, dedicated interview tracking, descriptive career context, skill freshness, explicit other-role exploration and pool monitoring.
- Added shared NVIDIA request pacing, quota cooldowns and truncated-response rejection.

## Initial recruiter workflow — 1 October 2026

- Introduced plain-language starting guidance, requirement priorities and simpler current-applicant uploads.
- Added responsibility-first interpretation, versioned caches and individual reassessment.
- Made Activity and missing-evidence states easier to understand.
