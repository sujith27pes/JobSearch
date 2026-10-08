# Validation

## Submission checks — 8 October 2026

| Check | Result | What it establishes |
|---|---|---|
| Backend test suite | 115 passed | Specified domain, API, ingestion, lifecycle and recovery behaviours match regression expectations. |
| TypeScript check | Passed | Frontend source satisfies the current compiler configuration. |
| Vite production build | Passed | The frontend can be compiled into distributable assets. |
| Offline synthetic benchmark | 150/150 expected criterion outcomes | The six designed fixture patterns produce the expected rule-based findings. |
| Benchmark source references | No unreferenced assessable claims | Those fixture findings reference supplied evidence. |

The benchmark contains 30 fictional profiles, five criteria and six repeating patterns. It makes no provider requests. Its eligibility count is date-dependent; 26 profiles qualified when this report was checked. Full output is in [benchmark-results.json](benchmark-results.json).

These results do not establish real-world semantic accuracy, fairness, production throughput or provider availability.

## What the tests cover

- Normalised scoring, coverage, essential status, experience intervals, recency and scenario calculations.
- Exact criterion membership, source references and relevant role references.
- Rediscovery expiry, permission/retention controls, internal visibility and interview exclusion.
- Rejection, repeated rejection, original-job exclusion and preservation of local rejection/interview provenance.
- Rubric/profile versions, corrections, cache reuse and shared-cache ownership.
- Per-file ingestion failures, retry eligibility, leases, heartbeat recovery and run reconciliation.
- Comparison, escaped exports, connection diagnostics and launcher failure cleanup.
- Sample cleanup and preventing automatic reseeding.

The tests use isolated data. Fictional fixture creation is not part of application startup.

## Reproduce the checks

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m backend.benchmark
```

From `frontend`:

```powershell
npm run build
```

The frontend script runs `tsc -b` followed by `vite build --configLoader native`. During submission preparation those same tools were invoked directly using the available Node executable because npm was not on the automation shell's PATH.

The backend run reported an upstream Starlette/httpx deprecation warning and a local pytest-cache permission warning. All tests passed. The Vite build reported a non-blocking bundle-size advisory. Neither warning is represented as a clean, warning-free result.

## Earlier integration and browser evidence

Recorded checks on 4 October exercised job creation, rubric edits and approval, fictional DOCX upload, automatic assessment, evidence viewing, interview tracking, small-sample monitoring and three-candidate comparison in an isolated workspace. Follow-up checks exercised rejection followed by rediscovery in another job, theme persistence, keyboard switching and a narrow layout.

A recorded fictional NVIDIA JD/resume/assessment flow completed three requests using 3,163 reported tokens. An earlier tiny authenticated connection test completed with HTTP 200 and 32 reported tokens. These checks were not repeated during submission cleanup; the current user's candidate data was not sent for this validation.

## Remaining evaluation

A real-data pilot needs a representative document corpus, independently labelled criterion findings, evaluation of false support on essentials, and an approved fairness and privacy process. Complex layouts, ambiguous dates and model interpretation can still fail despite valid JSON and resolvable evidence IDs.

This release supports a local single-user workspace and one worker process. Company authentication, enterprise adapters, encrypted persistence, automatic retention erasure, distributed quota coordination and exact token reservations remain deployment work. The health endpoint reports `production_ready=false`.
