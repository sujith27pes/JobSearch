# JobScore

**A recruiter workspace that explains the evidence behind a job match.**

Reading a resume is easy. Comparing it fairly against a job's requirements is harder, especially when candidates describe similar work with different titles and vocabulary. A keyword search can miss relevant experience; a single unexplained score gives the recruiter little reason to trust the result.

JobScore turns a job description into requirements the recruiter can review, compares resumes against those approved requirements, and shows the source text behind each finding. It also helps recruiters revisit eligible past applicants and consider opted-in internal talent. The recruiter makes the hiring decision.

## See it in action

![AI assessment identifying relevant work beyond exact keywords](docs/images/02-contextual-matching.jpg)

In this fictional AI-mode example, Maya's described work supports an incident-response requirement even though that phrase never appears in her resume. Open the [demo gallery](DEMO.md) for source evidence, three-candidate comparison, evidence-gap scenarios, rediscovery and internal mobility.

## What you can do

- **Define what matters.** Review the requirements extracted from a job description, adjust priorities and weights, and approve the final set before assessment starts.
- **Review documented fit.** See requirement-level findings, essential gaps, relevant experience and supporting PDF or DOCX passages.
- **Find overlooked experience.** In AI mode, assess the work described rather than requiring an exact title or keyword. A potential-overlooked-talent indicator points to cases worth reading closely.
- **Compare candidates.** Select two or three candidates and inspect the requirements responsible for their differences.
- **Explore evidence gaps.** Ask what additional supported information could reach a target score. The scenario leaves the official assessment unchanged.
- **Rediscover existing talent.** Search eligible rejected applicants from other jobs and opted-in employees when a job is open to internal talent.
- **Keep decisions traceable.** Record review reasons, reject an applicant explicitly, move a candidate to interview, and track the resulting lifecycle.
- **Manage changing resumes.** Replace a resume without losing the person's source identity, permissions or interview state. Earlier evidence versions remain distinguishable.
- **Follow processing.** Inspect queued work, failures and retries, then download shortlist or assessment reports.
- **Work comfortably.** Use light or dark mode, searchable tables, evidence drawers and a responsive layout.

## Try it in five minutes

Start the application using the instructions below. The workspace starts empty; example jobs and resumes are not inserted automatically.

1. **Create a job.** Add a title and a job description with a few clear requirements.
2. **Confirm the requirements.** Check what was extracted, choose which requirements are essential, and approve the rubric. A rubric is simply the agreed scoring checklist.
3. **Add resumes.** Upload two or three fictional, text-based PDFs or DOCX files. Open Activity to follow processing.
4. **Read the explanation.** Open a candidate, inspect a requirement, and follow its evidence link back to the supplied text.
5. **Compare and review.** Compare candidates, try an evidence-gap scenario, and record a review reason.

To demonstrate rediscovery, reject a fictional current applicant for the original job with a reason. Create another approved job, choose **Search existing talent**, and inspect **Rediscovered**. Matching permission, retention and interview exclusions still apply. Uploading a current applicant does not automatically make them a past applicant.

## How the score works

The interpretation step answers: *What does the resume support for this requirement?* Python then calculates the score from those findings and the approved weights. The model does not choose the final total.

| Finding | Credit | Meaning |
|---|---:|---|
| Supported | Full | The supplied evidence supports the approved condition. |
| Partial | Half | The evidence supports part of the condition. |
| Not evidenced | None | The document does not establish it; this is a question to clarify. |
| Unmet | None | Evidence establishes that the condition is not met. |

For a simple example, give Java a weight of 4, PostgreSQL 3, backend experience 2, and Kubernetes 1. Full Java support contributes 40 points. Partial PostgreSQL support contributes 15, supported backend experience 20, and missing Kubernetes evidence 0. The total is **75**.

The screen also shows **essential requirements** and **evidence coverage** separately. In that example, coverage is 90% because the first three requirements have assessable findings, even though PostgreSQL receives partial credit. Coverage is information availability, not confidence or a probability of hiring success. Approved duration and recency conditions apply additional deterministic date rules.

Changing only weights can reuse the existing interpretation and recalculate points. Changing a requirement, resume version or interpretation method requires the appropriate refresh. Source links make findings inspectable; they do not independently verify a candidate's claims.

## Run locally

You need **Python 3.12 or later** and **Node.js 22.18 or later**. Node is used to build the interface; Python runs the application. The commands assume you are in the repository root.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
Copy-Item .env.example .env
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe run.py
```

Copy the environment template only on first setup; keep an existing `.env` when updating. Once installed, `Start-JobScore.ps1` is a shortcut for starting the application.

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The launcher starts the web server and background worker together. Press **Ctrl+C** to stop both. Keep one worker process running for this release.

### Choose the interpretation mode

The default **offline preview** works without an API key. It uses conservative local rules and is useful for inspecting the workflow. It does not provide general understanding of arbitrary resume language or custom acceptance conditions.

For contextual interpretation, edit your local `.env`:

```dotenv
JOBSCORE_MODE=ai
LLM_BASE_URL=https://YOUR-APPROVED-ENDPOINT/v1
LLM_API_KEY=YOUR_KEY
LLM_MODEL=YOUR_MODEL
```

Use an approved OpenAI-compatible chat-completions endpoint. Restart the launcher after configuration changes. The configured provider receives extracted job and resume text in AI mode. Use fictional documents for a public demonstration unless your organisation has approved that data flow.

NVIDIA endpoints use a shared request gate with conservative pacing, bounded retries and quota cooldowns. Activity includes a connection check that sends no resumes and makes no generation. An optional authenticated command-line test uses a small amount of provider quota:

```powershell
.\.venv\Scripts\python.exe run.py --check-model
.\.venv\Scripts\python.exe run.py --test-model
```

## Resume and talent-pool rules

- **Files:** text-based PDF or DOCX, up to 10 MB per file; PDFs up to 15 pages; extracted text up to 40,000 characters. Scanned PDFs require a text-based replacement because OCR is not included.
- **Local allowance:** up to 30 uploaded profiles and 30 files in a batch. A bad file has its own failure without discarding successfully accepted files.
- **Current applicants:** uploaded to a specific job. For an updated resume, choose the explicit replacement option rather than uploading the person again as a new applicant.
- **Past applicants:** must have rejected status, a valid rejection date, matching permission and unexpired retention. Rediscovery lasts three calendar months after rejection, excluding the cutoff date. Replacing a resume does not restart this window.
- **Internal talent:** requires matching permission, internal visibility and a job open to internal talent.
- **Interviews:** an active interview blocks past-applicant rediscovery. Rejection and interview advancement are explicit recruiter actions with recorded reasons.

Historical and employee imports use the [CSV manifest template](docs/import-manifest.csv). Its row is a fictional format example, not a resume loaded into the application. Filenames must match the upload exactly. Dates use ISO format and booleans accept `true`/`false` or `1`/`0`.

The application checks eligibility again when scheduling, processing, displaying, comparing and exporting results. A cached score cannot keep an expired or excluded profile in the matching list.

## Under the hood

```text
React browser
     | REST requests and progress polling
     v
FastAPI server -------- SQLite records and durable tasks
     |                           ^
     |                           |
     |                     Python worker
     |                           |
     +---- configured model -----+
           gateway in AI mode
```

React and TypeScript provide the interface. FastAPI handles requests and recruiter actions. SQLAlchemy stores jobs, approved rubrics, profile versions, assessments and audit events in SQLite. A separate worker extracts documents and processes saved tasks, with leases and heartbeats for restart recovery.

PDFMiner and python-docx preserve source locations. Pydantic validates structured model responses. The scoring rules live in Python, separately from AI interpretation. File and interpretation caches avoid repeating compatible work.

For a deeper explanation, see the [system design](docs/SYSTEM_DESIGN.md). Developers can explore the running API at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).


Run `npm run build` from `frontend` to check TypeScript and produce the interface. Backend tests and the benchmark use isolated databases; they do not populate the working talent pool.

## Project layout

```text
backend/          API, domain rules, extraction, worker and tests
frontend/         React interface, API types and dependency lockfile
docs/             System design, validation, changelog and import template
PROMPTS.md        Development prompt record and runtime prompts
.env.example      Safe configuration template
run.py            Local API and worker launcher
Start-JobScore.ps1 Windows launcher shortcut
```

Local `.env`, databases, uploaded documents, virtual environments, installed packages and generated build outputs are excluded from Git. Submit the tracked source files; do not attach the entire working folder with private data and credentials.
