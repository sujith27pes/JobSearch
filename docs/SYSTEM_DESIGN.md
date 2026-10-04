# JobScore system design

## Runtime

React uses TanStack Query for server state, TanStack Table for candidate sorting, React Router for navigation, and locally owned shadcn-style Radix components for dialogs/buttons. Tailwind and custom CSS implement the enterprise visual system.

FastAPI owns scores, eligibility, versions and state changes. SQLAlchemy stores typed record families in an indexed JSON document repository. Record IDs are primary keys, kinds are indexed, and mapper version checks detect concurrent writes. This intentionally small schema avoids a graph database. A production migration should introduce explicit relational tables, database constraints and Alembic migrations before scale-out.

A separate Python worker uses a persisted queue with transactional claims, a 180-second lease, one-second heartbeats, one worker thread in AI mode, up to two in practice mode, and recovery of expired leases. A single worker process is supported in this release. SQLite WAL enables readers while work is processed. All processes must share one data directory and model configuration.

## Data flow

1. Job creation extracts criteria into a draft; no scoring before approval.
2. Approval stores an immutable rubric snapshot. The recruiter UI defaults to this job’s current applicants; historical/internal pools are an explicit opt-in or subsequent search.
3. Upload acceptance stores an opaque-named document and pending profile. Identity is source type plus source record ID. An explicit replacement reuses that ID; an identical manifest-less file for the same job reuses its existing upload. File hashes never merge identities across sources or jobs, and names never establish identity.
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
- Final assessment: profile version, approved rubric version, mode/model/prompt version, evaluation month. Each record also stores its exact evaluation date.

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


## Evaluation date and monthly refresh

`score(..., today=...)` and `assess_profile(..., today=...)` use the same captured date from the queued task. Date-sensitive calculations are reproducible from saved inputs and that date. Default capture is the deployment calendar date; never compare scores from different dates as if their temporal conditions were identical. Last use may be `present` only when supplied evidence establishes ongoing use. Fixed dates remain fixed; skills are not automatically assumed fresh because the employee remains employed.

Interpretation caches store their evaluation date. A duration is advanced without a model call only if its original supported months exactly matched the source-linked full role intervals and a linked role explicitly ends at `present`. Shorter project-specific duration estimates are held fixed. Calendar refresh records are unique per profile version/rubric/evaluation month, and only current eligible records with an existing current-engine cache are scheduled. This refresh never migrates old-engine evidence or invents new duties. A monthly arithmetic record is added; the previous score stays in history. Worker downtime delays refresh; the UI flags stale date-sensitive assessments.

## Additional interfaces

- `GET /api/monitoring?include_samples=false`: current latest eligible assessments by pool plus retained per-month history. Current eligibility, source permissions and profile versions apply. History labels rubric counts; role/rubric mix may change.
- `GET /api/profiles/{id}/opportunities`: current-version results, pending state and item errors for explicit other-role requests.
- `POST /api/profiles/{id}/opportunities`: at most three recruiter-selected eligible other approved jobs (`job_ids` in the request body), one active exploration per profile version, no application transfer. Requests can wait behind other jobs in the worker queue. Tasks and results use the same engine/cache contract. Results are stored separately as `opportunity_assessment` and never appear as applications to another job.
- Multipart `POST /api/imports` additionally accepts `profile_id` and `profile_revision` for explicit single-file replacement. Stale revisions return 409. Permissions and original interview stage are preserved.
- Comparison returns `pairwise_differences` for every pair among two or three candidates. Contribution deltas retain candidate identities.

`insights.py` contains descriptive context and conservative duration refresh logic. `insights_api.py` exposes monitoring and explicit other-role search. `model_limits.py` coordinates the NVIDIA request gate/cooldown across API and worker. The new frontend views/components are separate from the existing workspace file.

## NVIDIA request safety

One request is allowed in flight per endpoint/model within this shared SQLite workspace. Starts are paced at the configured requests/minute; retries obey Retry-After separately. A persisted lease permits recovery after a terminated request process; a shared quota cooldown prevents repeated requests after a long/exhausted 429. The default NVIDIA read timeout is 180 seconds; the waiting gate has a bounded 240-second timeout. There are at most two transient retries and one schema repair. Reasoning is disabled by default; explicit non-streaming avoids parsing an SSE response as JSON. The token budget remains an actual-usage soft stop, not an exact preflight token reservation or a provider quota promise. Multiple installations/keys and distributed workers require production-grade quota coordination.

Shared extraction entries are removed only when another profile does not reference the document hash. Identity, eligibility, review stage and scores remain separate per profile. No raw provider response, key or resume text is included in error logs.

Future employment periods are capped at the evaluation month for duration arithmetic. Future last-use dates remain unresolved against recency conditions until corrected. Cache deletion covers previous document versions and preserves hashes referenced by other retained profiles.

## Model connection diagnostics

`backend/connection.py` builds a verified TLS context, classifies sanitized transport causes and checks provider reachability. Windows loads system-approved certificate roots; an optional `LLM_CA_BUNDLE` augments them. Verification is never disabled. Assessment requests use the same context. Provider exception bodies, credentials and resume content are not included in diagnostic output.

`POST /api/model-connection/check` performs DNS resolution and an unauthenticated GET to the configured `/models` endpoint only when requested by the recruiter. Any HTTP response proves reachability, not valid credentials, model availability or remaining quota. There is no automatic provider polling. `run.py --check-model` offers the same check; `--test-model` adds one small authenticated generation with a fixed non-resume prompt, at most 64 output tokens, and no retry. DNS resolution follows the operating system's resolver timeout; HTTP requests have bounded timeouts.

Activity groups attempts by profile, job, task kind and exploration scope. Only the newest attempt for the current profile version and job rubric is actionable. Historical failures remain inspectable but cannot be retried against outdated inputs. A successful check does not silently replay failed candidate requests. Run counters describe their original run; attempt history is retained.
