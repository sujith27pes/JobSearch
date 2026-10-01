# JobScore system design

## Runtime

React uses TanStack Query for server state, TanStack Table for candidate sorting, React Router for navigation, and locally owned shadcn-style Radix components for dialogs/buttons. Tailwind and custom CSS implement the enterprise visual system.

FastAPI owns scores, eligibility, versions and state changes. SQLAlchemy stores typed record families in an indexed JSON document repository. Record IDs are primary keys, kinds are indexed, and mapper version checks detect concurrent writes. This intentionally small schema avoids a graph database. A production migration should introduce explicit relational tables, database constraints and Alembic migrations before scale-out.

A separate Python worker uses a persisted queue with transactional claims, a 180-second lease, one-second heartbeats, one worker thread in AI mode, up to two in practice mode, and recovery of expired leases. A single worker process is supported in this release. SQLite WAL enables readers while work is processed. All processes must share one data directory and model configuration.

## Data flow

1. Job creation extracts criteria into a draft; no scoring before approval.
2. Approval stores an immutable rubric snapshot. The recruiter UI defaults to this job’s current applicants; historical/internal pools are an explicit opt-in or subsequent search.
3. Upload acceptance stores an opaque-named document and pending profile. Identity is source type plus source record ID, not name or file hash.
4. The worker parses the upload, validates limits, extracts facts, and validates source IDs.
5. Successful extraction removes the raw upload, saves a profile version, and queues refresh records for applicable jobs.
6. The matching worker checks current eligibility again, resolves an interpretation cache, and assesses if required.
7. Pure scoring code calculates credit, coverage, essentials, contributions, hidden-gem labels and summaries.
8. A final eligibility/version check precedes persistence. API reads recheck eligibility, so a cached result cannot keep an expired application in rediscovery.
9. Human review records reasons. Interview advancement blocks rediscovery. Corrections create a new profile version and invalidate visible old results until refreshed.

## Boundaries

- `schemas.py`: Pydantic request and structured model-output contracts.
- `domain.py`: scoring, calendar expiry, interval union, baseline matching and scenarios.
- `intelligence.py`: document extraction, model gateway and labelled offline interpreter.
- `ingestion.py`: restart-safe upload extraction.
- `services.py`: eligibility-aware matching, cache reuse, refreshes and result composition.
- `worker.py`: persisted queue execution, claims and recovery.
- `main.py`: HTTP, permission boundaries, review, reports and static frontend serving.
- `store.py`: transactions, optimistic concurrency and audit events.

## Interpretation versus calculation

The model returns criterion statuses, explanations and source IDs. It never returns an official aggregate score. Positive and explicitly negative assessments need resolvable evidence. Criterion IDs must match the rubric exactly once. Referenced role IDs must resolve. Claimed duration cannot exceed source-linked dated intervals.

Weight-normalized scoring and scenario arithmetic are deterministic. Unknown evidence receives zero documented credit with an explicit unknown label. Evidence coverage counts assessable criteria separately. Role suitability is never a probability of success, and there is no automatic rejection threshold.

Valid source references do not establish semantic entailment. Humans must still assess whether the cited text actually supports the conclusion. The demo heuristic does not claim to understand arbitrary custom acceptance conditions.

## Cache keys

- Extraction: SHA-256 file content, interpreter mode, model and prompt version.
- Interpretation: profile version, rubric content excluding weight/enabled state, mode/model/prompt version.
- Final assessment: profile version, approved rubric version, mode/model/prompt version.

Changing weights preserves interpretation. Changing requirements does not. Deleting a profile removes its versions, assessments, review data, pending tasks, interpretation cache and relevant extraction cache. Events retain only opaque record IDs and action metadata.

## Three-month rediscovery

Eligibility is evaluated at request and worker time. The cutoff is rejection date plus three calendar months, clamped to the final valid day of the destination month. The cutoff date itself is excluded. Re-uploading a CV does not restart the rejection clock.

Only rejected applications qualify. The active interview flag blocks rediscovery across roles. Moving to interview is a human action with a reason, not an AI action. Retention and matching permissions remain independent controls. Expiry hides profiles from matching; it is not represented as evidence of having found another job.

## API contracts

OpenAPI is generated from FastAPI and checked into `frontend/openapi.json`. Frontend request types are generated in `frontend/src/api-schema.d.ts`. App-specific read views also use flexible result types; further hardening should define response models for every read endpoint.

Draft, approval, correction and review mutations require expected revision identifiers. Imports and match runs accept idempotency keys. Errors use HTTP 404/403/409/410/422 with a safe description. Model response bodies and raw documents are not exposed through error logs.

## Production migration

Before a real-data pilot: add OIDC, requisition-scoped user permissions, encrypted object storage, retention deletion jobs, structured relational schema/migrations, source-adapter identity policy, strong idempotency reservations, transactional token-budget reservation, and company-managed secret injection. Replace SQLite transaction syntax with PostgreSQL row locking before multiple worker processes.

An approved read-only Taleo adapter should map source lifecycle events into the import contract. An authoritative rejection-to-interview update must suppress every related historical application for the same verified person. This release enforces the lifecycle within its source identity records; cross-source person resolution is not guessed.

Large-pool budgeted batches of 100 are a production extension, not exposed by this local build with a 30 uploaded-profile allowance. Do not claim the demo evaluates an entire enterprise ATS at production scale.

## Recruiter usability and interpretation revision

Assessment prompt version jobscore-2.2-responsibility-first evaluates dated duties regardless of title. Cache keys include the prompt version. The latest current-method assessment replaces older entries in candidate listings while stored records remain available. Existing records carry a needs_reassessment flag and offer a one-profile reassessment endpoint. Missing duration is unresolved, not explicit failure.

Operational heartbeats update lease fields atomically without incrementing business revisions; they cannot overwrite terminal task status. A task exception is contained by the worker. Groq 429 responses honour short Retry-After windows and produce a plain quota message when retries are exhausted.
