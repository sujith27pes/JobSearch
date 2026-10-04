# JobScore

Latest fixes (4 October 2026): see `docs/CHANGES-2026-10-04.md` for the complete change log and validation. Restart the launcher and refresh the browser to load the update. Authored jobs now appear by default; explicit requests can wait behind existing queue work, with worker concurrency still bounded.

Sample data has been removed from the workspace. Startup no longer creates example jobs or resumes, including when an older environment sets `JOBSCORE_SEED=1`. New workspaces start empty. Fictional fixtures remain confined to automated tests and the isolated benchmark.

A working local recruiter workspace built with React, TypeScript, FastAPI and SQLite. The original Streamlit prototype in Downloads was used as a reference and was not modified. No API key or private environment file was copied.

## Open the application

The prepared application is served at **http://127.0.0.1:8000** while the API and worker are running.

Use the **Light / Dark** switch in the top bar to change the appearance. It follows your system theme until you choose a mode, then remembers your choice in this browser.

On this machine, run `Start-JobScore.ps1` from this folder to launch both processes and open the browser. It uses the installed `.venv` and compiled frontend. Stop with Ctrl+C.

For a fresh checkout (Python 3.12+, Node 22.18+ or 24 recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe run.py
```

The native Vite config loader avoids unnecessary config bundling. The launcher binds to localhost only. If port 8000 is already occupied, stop the earlier JobScore process first.

## What is implemented

- React enterprise workspace: jobs, overview, source-specific matches, detail dialogs, source drawers, comparisons, rubric editor, talent library and processing history.
- Isolated test fixtures covering 30 fictional profiles and three engineering jobs; these are not added to the workspace.
- Immutable approved rubrics, normalized deterministic scoring, separate essential status and evidence coverage.
- Contextual and project-combination interpretation through an optional AI endpoint; a clearly labelled limited offline preview works without credentials.
- Evidence IDs validated against stored source passages; PDF page/text block and DOCX paragraph/table-cell locations.
- Reusable extractions and cached interpretations. Weight-only edits perform arithmetic without new model calls.
- Relevant experience intervals, consistency checks and last-evidenced dates where available.
- Rediscovery eligibility on every match, detail, comparison and export request; no stale cached result bypass.
- Internal matching only for visible opted-in employees and internally open jobs.
- Gap scenarios, smallest combinations of up to three criteria, human review reasons and interview-stage removal.
- Restart-safe upload/extraction and assessment tasks, leases, heartbeats, one concurrent task in AI mode (at most two in practice mode), per-file failures and retries.
- Source manifests, profile suppression, source corrections, new profile versions, deletion of derived records and cache entries.
- CSV, HTML and JSON exports with output escaping.
- Generated OpenAPI frontend types and automated domain/integration tests.

## Your updated rediscovery rule

To reject a current applicant, open their candidate details and select **Your review → Reject for this job**, enter a reason, then click **Reject candidate**. This records the rejection date, closes the application for the original job, and moves the profile to past applicants without deleting its resume. In another job, choose **Search existing talent → Rediscovered**. Matching permission, retention and interview exclusions still apply. Repeating rejection or updating the resume does not restart the eligibility window. For rediscovered and internal candidates, **Not shortlisted** records the review decision without changing their source lifecycle.

Only applications with `application_status=rejected` and a valid `rejected_at` qualify. The window is **three calendar months after the rejection date**, end-exclusive. For example, a 28 June rejection stops qualifying on 28 September; a 31 January rejection stops qualifying on 30 April. Refreshing a resume does not reset this clock.

Approved, interviewing, hired and withdrawn applications do not qualify. The candidate review action **Approve and move to interview** immediately blocks rediscovery across jobs. Stale imports cannot clear the local active-interview flag. Profile expiry removes the application from matching; it does not destructively delete audit history. Retention expiry is an additional independent exclusion.

The isolated test fixtures include four excluded historical profiles: expired rediscovery, interview, revoked matching permission, and retention expiry. The benchmark checks **26** eligible profiles, including **8** rediscovered profiles; the workspace contains only your own data.

## Offline demonstration and AI mode

The default `JOBSCORE_MODE=demo` uses conservative, deterministic term/context rules. It is a transparent demonstration, not a trained hiring model. Complex acceptance-condition semantics require AI mode and human evaluation. The demo does not guess relevant skill duration from whole-job tenure.

To use an approved OpenAI-compatible endpoint, copy `.env.example` to `.env` and configure:

```text
JOBSCORE_MODE=ai
JOBSCORE_SEED=0
LLM_BASE_URL=https://YOUR-APPROVED-ENDPOINT/v1
LLM_API_KEY=YOUR_KEY
LLM_MODEL=YOUR_MODEL
LLM_INPUT_PRICE_PER_MILLION=0
LLM_OUTPUT_PRICE_PER_MILLION=0
```

The launcher loads `.env` into the process environment. Running uvicorn/worker separately requires setting their environment yourself. Both must use the same mode and model. Never commit `.env`.

The configured NVIDIA Nemotron 3 Ultra 550B endpoint passed a fictional end-to-end check: JD extraction, resume extraction and responsibility-first assessment (3 requests, 3,444 tokens). General semantic quality, document variation and latency still require evaluation before a real-data pilot. Pricing is **unavailable** unless configured; zero-cost operation in demo mode means no model requests, not proof of production savings.

Use synthetic data until your organisation approves the data flow. Extraction sends document passages to the configured model endpoint. No source-system connection, live Taleo access, email outreach, or manager notification is implemented or simulated as live.

## Importing resumes

Open a job and choose **Upload resumes**. Supported: text-based PDF/DOCX, 10 MB each, at most 15 PDF pages, 40,000 extracted characters. Scanned PDFs are explicitly rejected; there is no silent truncation.

Historical and employee imports require the CSV manifest described in `docs/import-manifest.csv`. The filename must exactly match the uploaded file. Also supply `application_status` and `rejected_at` for rejected applications. Employees require `internal_visibility=true`. Date fields are ISO dates. Booleans accept true/false or 1/0.

Imports return queued items immediately. The worker extracts, validates and then queues affected approved jobs. Failures remain visible in Processing. Raw upload files are removed after successful extraction; exact source passages remain in SQLite. Failed upload files remain available for retry and are deleted with their profile.

The workspace allows 30 uploaded profiles. Add your own job descriptions and resumes; sample-data controls have been removed from the interface.

## Development

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# Terminal 2
.\.venv\Scripts\python.exe -m backend.worker
# Terminal 3
cd frontend
npm run dev
```

Vite runs on port 5173 and proxies `/api` to FastAPI. A compiled frontend is also served by FastAPI. API docs: http://127.0.0.1:8000/docs.

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m backend.benchmark
cd frontend
npm run build
```

The tests and benchmark use separate temporary databases, not the app's live workspace. `docs/benchmark-results.json` describes the synthetic check and its limits.

## Design and readiness

See `docs/SYSTEM_DESIGN.md` for architecture, service contracts and cache semantics. See `docs/DELIVERY_STATUS.md` for verified behavior and production gaps.

This is a local hackathon application, not a production-authorised hiring system. Server-configured pool restrictions are not a substitute for SSO. Do not expose this localhost build to a network or use it for autonomous hiring decisions.

## Recruiter workflow update

Confirm requirements → Add resumes → Review candidates. Advanced scoring and source-import controls are collapsed by default. Confirming requirements assesses current applicants; searching historical/internal talent is an explicit option to avoid unexpected AI batches. Missing evidence is labelled Needs clarification, not confirmed lack of ability. Old assessments offer Update this assessment; updated results replace the old entry in the candidate list while retaining stored history. Restart the backend and worker after updating code.

## Finding interview-stage candidates

Open Interviews in the sidebar. Moving a candidate to interview opens this list automatically and records the job, date and review reason. Past applicants leave Rediscovered but remain in interview tracking while permissions and retention allow access. Older moves appear too; if their job cannot be unambiguously recovered, Job not recorded is shown.


## Bug fixes and recruiter insights — 2 October 2026

The seven reported failures are fixed: separator-only JD lines are ignored; recency and duration use a saved evaluation date; uploads offer safe replacement and identical-file reuse; three-candidate comparisons show all three pairs; missing profile snapshots are skipped; shared extraction caches survive deletion of one owner; ingestion claims start at parsing. Queue order is explicit, and record updates preserve creation timestamps.

**Update a resume:** open its job, choose **Add resumes**, then select the candidate under **Replace an existing candidate’s resume**. Upload one PDF/DOCX. This creates a profile version while preserving permissions and interview stage. An identical file uploaded to the same job reuses the existing candidate. A changed file with an existing filename requires an explicit replacement choice. Different names/files cannot reliably establish identity; do not upload an update as a new applicant. Names alone are never used to merge people. Source-managed profiles are updated through their authorised manifest IDs.

**New candidate insights:** open a candidate. In **Job fit**, expand **When were these skills evidenced?** or **Could this candidate fit another role?**. In **Work history**, inspect title transitions, literal promotion claims, dated promotion intervals and short completed roles. Scope claims link to supplied evidence; title changes are not classified automatically as promotions. Short-tenure context means at least three completed roles under 18 months, ending within five years; ongoing roles are excluded. No career or tenure signal changes the score.

**Other jobs:** the recruiter explicitly requests up to three other approved, eligible roles. These requests use the same cached engine and bounded queue. Results display essential gaps as well as score. Current applicants remain attached to their original job; no new application, interview move or outreach occurs. Scores against different rubrics are leads for review, not interchangeable measures of candidate quality.

**Monitoring:** the sidebar shows distributions by talent pool, unresolved essentials, stale assessments, evidence coverage and retained monthly history across requisitions. Samples are excluded by default. Means are withheld for fewer than five observations. This is assessment monitoring, not a protected-group adverse-impact analysis. Demographic data collection and a validated fairness study are outside this release.

### NVIDIA Nemotron free-endpoint configuration

Keep your existing API key in `.env`; it was not modified. These defaults are applied automatically for `integrate.api.nvidia.com`:

```text
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=nvidia/nemotron-3-ultra-550b-a55b
LLM_REQUESTS_PER_MINUTE=5
LLM_TIMEOUT_SECONDS=180
LLM_QUEUE_TIMEOUT_SECONDS=240
LLM_MAX_OUTPUT_TOKENS=6000
LLM_REASONING_EFFORT=none
```

The endpoint receives `stream=false` and `reasoning_effort=none`. JSON is validated locally; fenced JSON is supported, but truncated/incomplete output is never saved as an assessment. The API process and worker share a database-backed request gate, so there is one NVIDIA request in flight and at least 12 seconds between request starts. Short 429 delays are respected; a long or exhausted 429 activates a shared cooldown that prevents follow-on network requests. Provider quotas and outages cannot be guaranteed by the application. Five requests/minute is our conservative limit, not NVIDIA's published quota. Higher reasoning settings may need more output tokens and time.

NVIDIA references: [model inference API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer), [model card](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard).

After updating this folder, stop the existing launcher with Ctrl+C, then run `.\.venv\Scripts\python.exe run.py`. Refresh the browser. No database reset is needed. Scores from earlier prompt versions display an update action. Monthly recency/duration refreshes run while the worker is active and cached interpretations exist.

Other-role results include requirement-level evidence links. Choose the jobs using the checkboxes before starting a search; unselected jobs have not been assessed.

## Connection troubleshooting — 3 October 2026

Open **Activity → Check AI connection** to check DNS and HTTPS reachability from the API process. It sends no resumes and makes no model generation. A successful reachability check does not validate your API key or quota.

From PowerShell in the JobScore folder, these commands load your `.env` and exit after the check:

```powershell
# Network check, no model tokens
.\.venv\Scripts\python.exe run.py --check-model
# Optional authenticated test: a tiny CONNECTED reply, no resumes
.\.venv\Scripts\python.exe run.py --test-model
```

The authenticated test uses a small amount of provider quota. It passed with the configured NVIDIA model on 3 October 2026: HTTP 200, 32 tokens. This confirms connectivity and authentication at that time; the exact cause of earlier generic connection failures remains unverified.

Connection failures now distinguish DNS, certificate verification, network permission, proxy and refused connections when the underlying exception supplies that cause. Windows uses its approved system certificate roots. If IT supplies a PEM bundle, set `LLM_CA_BUNDLE` to its path; certificate verification always stays enabled. Do not disable TLS verification.

Stop your running launcher with **Ctrl+C**, then start the updated code:

```powershell
.\.venv\Scripts\python.exe run.py
```

Refresh the browser. In **Activity**, retry the latest failed resumes after connectivity is restored. Saved failures are not automatically retried. The default table shows only current attempts; **Show all attempt history** reveals older attempts without offering an obsolete retry. No database reset or API key replacement is required.
