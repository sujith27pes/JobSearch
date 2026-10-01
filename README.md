# JobScore

A working local recruiter workspace built with React, TypeScript, FastAPI and SQLite. The original Streamlit prototype in Downloads was used as a reference and was not modified. No API key or private environment file was copied.

## Open the application

The prepared application is served at **http://127.0.0.1:8000** while the API and worker are running.

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
- 30 explicitly synthetic profiles: 10 current applicants, 12 historical applications, 8 employees; three engineering jobs.
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

Only applications with `application_status=rejected` and a valid `rejected_at` qualify. The window is **three calendar months after the rejection date**, end-exclusive. For example, a 28 June rejection stops qualifying on 28 September; a 31 January rejection stops qualifying on 30 April. Refreshing a resume does not reset this clock.

Approved, interviewing, hired and withdrawn applications do not qualify. The candidate review action **Approve and move to interview** immediately blocks rediscovery across jobs. Stale imports cannot clear the local active-interview flag. Profile expiry removes the application from matching; it does not destructively delete audit history. Retention expiry is an additional independent exclusion.

The demo deliberately includes four excluded historical profiles: expired rediscovery, interview, revoked matching permission, and retention expiry. Therefore the first job normally has **26** eligible profiles, including **8** rediscovered profiles.

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

The configured Groq endpoint passed two fictional responsibility-first experience tests. General semantic quality, document variation and latency still require evaluation before a real-data pilot. Pricing is **unavailable** unless configured; zero-cost operation in demo mode means no model requests, not proof of production savings.

Use synthetic data until your organisation approves the data flow. Extraction sends document passages to the configured model endpoint. No source-system connection, live Taleo access, email outreach, or manager notification is implemented or simulated as live.

## Importing resumes

Open a job and choose **Upload resumes**. Supported: text-based PDF/DOCX, 10 MB each, at most 15 PDF pages, 40,000 extracted characters. Scanned PDFs are explicitly rejected; there is no silent truncation.

Historical and employee imports require the CSV manifest described in `docs/import-manifest.csv`. The filename must exactly match the uploaded file. Also supply `application_status` and `rejected_at` for rejected applications. Employees require `internal_visibility=true`. Date fields are ISO dates. Booleans accept true/false or 1/0.

Imports return queued items immediately. The worker extracts, validates and then queues affected approved jobs. Failures remain visible in Processing. Raw upload files are removed after successful extraction; exact source passages remain in SQLite. Failed upload files remain available for retry and are deleted with their profile.

The workspace allows 30 uploaded profiles in addition to fictional sample profiles. Samples do not consume the upload allowance. Example jobs are hidden by default; enable Show example jobs to practise.

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
