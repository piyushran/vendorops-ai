# VendorOps AI

VendorOps AI is a production-style AI data pipeline for ingesting vendor documents, extracting structured data with an LLM or mock extractor, validating the output, storing results, and generating operational reports.

The initial MVP uses Python, FastAPI, SQLAlchemy, SQLite, Pydantic, pytest, and Docker. The design stays PostgreSQL-ready so the project can grow from a local portfolio build into a credible service architecture.

## Project Goals

- Ingest PDFs, CSVs, text files, and email-like files.
- Extract structured vendor, invoice, and contract data.
- Validate required fields, data types, confidence scores, duplicates, and malformed outputs.
- Store files, jobs, extracted records, validation errors, audit logs, and reports.
- Provide FastAPI endpoints for upload, pipeline runs, job status, records, errors, and reports.
- Generate JSON and CSV reports.
- Include structured logging, retries, error tracking, Docker support, and tests.

## Phase Roadmap

- Phase 0: Project setup.
- Phase 1: FastAPI backend with health check, file upload, and job creation.
- Phase 2: Database layer.
- Phase 3: File parsing.
- Phase 4: LLM extraction with mock fallback.
- Phase 5: Validation layer.
- Phase 6: Pipeline orchestration.
- Phase 7: Reporting.
- Phase 8: Observability.
- Phase 9: Docker and deployment.
- Phase 10: Testing.
- Phase 11: GitHub polish.

## Current Status

Phase 10 is complete:

- Repository structure created.
- Python dependencies defined in `pyproject.toml`.
- Environment template added in `.env.example`.
- `.gitignore` added.
- README skeleton added.
- FastAPI app factory added.
- Health endpoint added.
- File upload endpoint added for `.csv`, `.eml`, `.pdf`, and `.txt`.
- Job creation and job status endpoints added.
- Local file storage added for uploaded files.
- Phase 1 API tests added.
- SQLAlchemy async database layer added.
- SQLite-backed tables added for uploaded files, processing jobs, extracted records, validation errors, extraction errors, audit logs, and generated reports.
- Upload and job endpoints now persist to the database.
- Audit events are created for file uploads and job creation.
- Parser layer added for TXT, CSV, PDF, and EML/email-like files.
- Uploaded files can be parsed through `GET /v1/files/{file_id}/parsed`.
- Strict structured extraction schemas added with Pydantic.
- Mock extractor added so the app works without an API key.
- OpenAI extractor path added for `OPENAI_API_KEY` deployments.
- Extraction endpoint added: `POST /v1/files/{file_id}/extract`.
- Extracted records are persisted in SQLite and exposed through `/v1/records`.
- The React dashboard now uploads, parses, extracts, and displays structured JSON output.
- Validation rules added for required fields, confidence, amounts, line items, and source evidence.
- Validation findings are persisted in `validation_errors`.
- Validation errors API added.
- The dashboard now shows pass/needs-review validation state and finding details.
- Pipeline orchestration service added.
- `POST /v1/jobs/{job_id}/run` added for running queued pipeline jobs.
- File extraction and explicit job execution now share the same orchestration code path.
- JSON and CSV report generation added.
- Generated report metadata is persisted in `generated_reports`.
- Report download endpoint added.
- Dashboard report cards can generate and download real reports.
- Structured JSON logging added with request IDs.
- Request tracing middleware adds `X-Request-ID` to API responses.
- Retry handling added around LLM extraction attempts.
- Extraction and parser failures are persisted in `extraction_errors`.
- Audit log and extraction error APIs added.
- Dashboard observability panel added for recent audit events and extraction failures.
- Backend Dockerfile added for the FastAPI runtime.
- Frontend Dockerfile added for a production Nginx-served React build.
- Docker Compose stack added with persistent SQLite, upload, and report volumes.
- Nginx proxy config added for same-origin `/health` and `/v1` API calls.
- Deployment guide added in `deploy/README.md`.
- Shared pytest fixture added for isolated API/database test contexts.
- End-to-end API integration tests added for upload, parse, extraction, records, reports, audit logs, and error contracts.
- Retry utility tests added for recovery and exhausted attempts.
- Test runner script added for backend linting, backend tests, and frontend build validation.
- Analyst-grade analytics API added at `GET /v1/analytics/dashboard`.
- Executive dashboard added for throughput, validation risk, extraction confidence, retries, blocked jobs, cost, and report usage.
- GitHub Actions CI added for backend lint/tests, frontend build, and Docker Compose validation.
- Production SaaS architecture documented in `docs/PRODUCTION_SAAS_ARCHITECTURE.md`.
- Authentication, seeded demo organization/workspace, bearer sessions, RBAC permissions, and SaaS identity dashboard panel added.
- Strict authenticated RBAC is enforced on business APIs.
- Alembic migrations added for tracked schema evolution.
- Docker Compose now runs the application against PostgreSQL with persistent database storage.
- Storage abstraction added for uploads and generated report artifacts.
- Upload filename sanitization and configurable upload size limits added.
- Pipeline execution now uses background job dispatch instead of blocking API requests.

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Create your local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Run database migrations:

```powershell
.\scripts\run_migrations.ps1
```

## Planned API Examples

Implemented endpoints:

```text
GET  /health
POST /v1/files
GET  /v1/files/{file_id}/parsed
POST /v1/files/{file_id}/extract
POST /v1/jobs
GET  /v1/jobs/{job_id}
POST /v1/jobs/{job_id}/run
GET  /v1/records
GET  /v1/records/{record_id}
GET  /v1/validation-errors
GET  /v1/validation-errors/records/{record_id}
POST /v1/reports
GET  /v1/reports
GET  /v1/reports/{report_id}
GET  /v1/reports/{report_id}/download
GET  /v1/audit-logs
GET  /v1/extraction-errors
GET  /v1/analytics/dashboard
POST /v1/auth/login
GET  /v1/auth/me
```

## Run The API

First change into the project folder:

```powershell
cd "C:\Users\Princ\Documents\Codex\2026-04-24\VendorOps AI"
```

```bash
uvicorn app.api.main:app --reload
```

On Windows PowerShell, you can also use the helper script:

```powershell
.\scripts\run_api.ps1
```

If your shell is not activated, run through the project virtual environment directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Run The Frontend

The premium dashboard UI lives in `frontend/` and uses React, TypeScript, Vite, Tailwind CSS, and Lucide icons.

In local development, Vite proxies `/health` and `/v1` API calls to `http://127.0.0.1:8000`.

Install frontend dependencies:

```powershell
cd "C:\Users\Princ\Documents\Codex\2026-04-24\VendorOps AI\frontend"
npm install
```

Optional frontend environment file:

```powershell
Copy-Item .env.example .env
```

Start the frontend:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

You can also start it from the project root:

```powershell
.\scripts\run_frontend.ps1
```

To launch backend and frontend in two PowerShell windows:

```powershell
.\scripts\run_all.ps1
```

Build the frontend:

```powershell
cd frontend
npm run build
```

## Run With Docker

Build and start the full stack:

```powershell
cd "C:\Users\Princ\Documents\Codex\2026-04-24\VendorOps AI"
docker compose up --build
```

The Compose stack starts PostgreSQL, runs Alembic migrations, then starts the API and frontend.

Open the dashboard:

```text
http://127.0.0.1:5173
```

Open the API docs:

```text
http://127.0.0.1:8000/docs
```

Stop the stack:

```powershell
docker compose down
```

To include a real OpenAI API key, copy `.env.docker.example` to `.env`, set `OPENAI_API_KEY`, and restart Compose. If no API key is set, the mock extractor is used.

## API Examples

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Login and save a bearer token:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@vendorops.ai","password":"VendorOpsDemo123!"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

Upload a file:

```bash
curl -X POST http://127.0.0.1:8000/v1/files \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/sample_invoice.txt"
```

Create a job:

```bash
curl -X POST http://127.0.0.1:8000/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"file_id":"<FILE_ID>","pipeline":"document_extraction"}'
```

Check job status:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/jobs/<JOB_ID>
```

Parse an uploaded file:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/files/<FILE_ID>/parsed
```

Run structured extraction:

```bash
curl -X POST http://127.0.0.1:8000/v1/files/<FILE_ID>/extract \
  -H "Authorization: Bearer $TOKEN"
```

List extracted records:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/records
```

List validation findings:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/validation-errors
```

Run a queued job:

```bash
curl -X POST http://127.0.0.1:8000/v1/jobs/<JOB_ID>/run \
  -H "Authorization: Bearer $TOKEN"
```

Generate a JSON summary report:

```bash
curl -X POST http://127.0.0.1:8000/v1/reports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_type":"summary","format":"json"}'
```

Generate a CSV records report:

```bash
curl -X POST http://127.0.0.1:8000/v1/reports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_type":"records","format":"csv"}'
```

## Planned Architecture

```text
Files / Emails / CSVs
        |
        v
FastAPI Ingestion API
        |
        v
Local Storage + Processing Job
        |
        v
Parser -> Extractor -> Validator
        |
        v
SQLite/PostgreSQL
        |
        v
Reports + API Responses
```

## Database

The MVP defaults to SQLite:

```env
DATABASE_URL=sqlite+aiosqlite:///./vendorops.db
```

Docker and production-style deployments use PostgreSQL:

```env
DATABASE_URL=postgresql+asyncpg://vendorops:vendorops@postgres:5432/vendorops
```

Schema changes are tracked with Alembic migrations:

```powershell
.\scripts\run_migrations.ps1
```

Current tables:

- `uploaded_files`
- `processing_jobs`
- `extracted_records`
- `validation_errors`
- `audit_logs`
- `generated_reports`

## Parser Layer

The parser dispatcher normalizes supported file types into one shape:

- `text`: extracted text for downstream LLM extraction.
- `metadata`: source-specific metadata such as filename, row count, columns, headers, or page count.
- `pages`: PDF page-level text.
- `tables`: CSV rows and columns.

Supported parsers:

- TXT: UTF-8 text extraction.
- CSV: header/row extraction using Python's standard `csv` module.
- EML: subject/from/to/date headers and plain-text body extraction.
- PDF: text extraction using PyMuPDF.

## Storage Layer

VendorOps AI stores uploaded source files and generated reports through a storage abstraction.
The current implementation is local disk storage, configured with:

```env
STORAGE_BACKEND=local
MAX_UPLOAD_SIZE_MB=25
LOCAL_STORAGE_DIR=./storage
REPORTS_DIR=./reports_out
```

The application code now talks to an object-storage interface instead of direct filesystem writes.
That keeps the next production step clear: adding S3, Azure Blob, or GCS adapters without changing
the API, pipeline, parser, or reporting layers.

## LLM Extraction

Phase 4 adds a structured extraction service with two modes:

- Mock mode: used automatically when `OPENAI_API_KEY` is empty. This keeps local development and tests deterministic.
- OpenAI mode: used when `OPENAI_API_KEY` is set. The extractor sends parsed source text to the OpenAI Responses API with a strict JSON schema.

The normalized extraction schema captures:

- record type
- vendor name
- document ID
- document and due dates
- total amount and currency
- summary
- line items
- key terms
- source evidence
- confidence
- review flag

## Validation Layer

Phase 5 validates extracted records before they are treated as business-ready data.

Current checks:

- Required invoice fields: vendor name, document ID, total amount, and currency.
- Required contract fields: vendor name and document ID.
- Confidence threshold below `0.75`.
- Negative total amounts.
- Negative line item amounts.
- Missing source evidence for important extracted fields.

Validation findings are saved to `validation_errors` and returned from the extraction endpoint.

## Pipeline Orchestration

Phase 6 moves the core workflow into a reusable pipeline service:

```text
uploaded file
  -> parser dispatcher
  -> structured extractor
  -> validation rule engine
  -> extracted record persistence
  -> validation error persistence
  -> job status updates
  -> audit events
```

The orchestration service is used by both:

- `POST /v1/files/{file_id}/extract`
- `POST /v1/jobs/{job_id}/run`

These endpoints now return `202 Accepted` with a queued job. A local FastAPI background worker
executes the pipeline with a fresh database session, updates job status, and persists records,
validation findings, audit events, and extraction errors. This keeps route handlers thin and
sets up the next production step: replacing local background tasks with a durable Redis/Celery,
RQ, or cloud queue worker.

## Reporting

Phase 7 generates business-friendly outputs from extracted records and validation findings.

Supported report types:

- `summary`: totals by vendor, counts by record type, validation finding summaries, and record previews.
- `records`: flat extracted-record export.

Supported formats:

- `json`
- `csv`

Generated reports are written to `REPORTS_DIR` and tracked in `generated_reports`.

## Observability

Phase 8 adds production-style operational visibility:

- JSON logs with request IDs, route, status code, and latency.
- `X-Request-ID` response headers for tracing API calls.
- Retry tracking for transient LLM extraction failures.
- Persistent extraction error records for parser and extractor failures.
- Audit log API for file, job, record, validation, report, and error events.

Observability endpoints:

```text
GET /v1/audit-logs?limit=50
GET /v1/extraction-errors?limit=50
```

## Testing

Run the current test suite:

```bash
pytest
```

On Windows PowerShell, run the full local validation suite:

```powershell
.\scripts\run_tests.ps1
```

That script runs:

```text
ruff check .
pytest
npm run build
```

## Resume Positioning

## Durable workers (V1.2)

Jobs move through `queued -> running -> completed` or terminal `failed`. The standalone worker
atomically claims a queued job, assigns an execution ID, and holds a heartbeat lease. If its
process dies, the lease expires and any worker recovers the job. Retryable failures are rescheduled
with persisted exponential backoff; terminal errors remain visible through the job and extraction
error APIs. Extracted records are unique per job so retries do not duplicate the document result.

Run the worker locally, independently from FastAPI:

```bash
python -m app.workers.run
```

Use `WORKER_POLL_INTERVAL_SECONDS`, `WORKER_LEASE_DURATION_SECONDS`,
`WORKER_HEARTBEAT_INTERVAL_SECONDS`, `WORKER_MAX_ATTEMPTS`, `WORKER_RETRY_BASE_SECONDS`, and
`WORKER_RETRY_MAX_SECONDS` to tune it. Docker Compose includes a `worker` service. This
database-backed contract can later accept Redis/Celery/RQ or a cloud queue as a notification layer
without replacing job state, leases, or idempotency controls.

VendorOps AI demonstrates backend engineering, data engineering, AI extraction workflows, structured validation, pipeline reliability, and production-style API design.
