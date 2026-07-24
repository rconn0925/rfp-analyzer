<!-- GSD:project-start source:PROJECT.md -->
## Project

**RFP Analyzer — Federal Compliance Matrix Generator**

A hosted web app that ingests a federal government RFP/solicitation package (uploaded files or fetched from SAM.gov) and automatically produces a fully populated compliance matrix — every requirement extracted with section references, cross-mapped across Sections L, M, and C/SOW/PWS, mapped to a proposal outline, and judged for compliance against a company capabilities profile — exportable to Excel/CSV.

It serves Ross's own business first, doubles as a portfolio showcase for the job hunt (AI/dev employers and the GovCon industry), and is built on a foundation that can become a sellable product.

**Core Value:** Upload a real federal RFP and get back an accurate, fully populated compliance matrix with no manual shredding — if the extraction and matrix are wrong or incomplete, nothing else matters.

### Constraints

- **Hosting**: Must run on a public URL with a low-friction demo — showcase value depends on a recruiter being able to try it in under a minute
- **Domain**: Federal FAR-based solicitations only for v1 — parsing logic targets Section L/M/C (and SOW/PWS) structure
- **Output**: Excel/CSV is the required deliverable format — proposal teams live in spreadsheets
- **Stack**: To be recommended by research — no pre-committed stack
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

> ### ⚠️ STACK UPDATE (2026-07-24): LLM layer is LOCAL, not the Anthropic API
>
> **Decision (Ross):** never use an Anthropic API key. Reason: the subscription
> path is technically impossible and ToS-blocked for a backend/hosted app, and
> per-token API cost is unwanted. **All Claude/Anthropic rows below are SUPERSEDED
> for the LLM layer** — they remain only as original research context.
>
> **The LLM layer (Phase 2 extraction, Phase 3 cross-mapping + compliance judgment) uses:**
> - **Runtime:** Ollama (installed, v0.32.3), serving on `http://localhost:11434`
>   with an OpenAI-compatible `/v1` endpoint and JSON-schema structured outputs via
>   the `format` parameter. Runs on the local **AMD RX 7900 XTX (24 GB VRAM)** via
>   ROCm; Vulkan (llama.cpp/LM Studio) is the fallback if ROCm is unstable on Windows.
> - **Model:** Qwen2.5-32B-Instruct (Q4, quality) with Qwen2.5-14B-Instruct
>   (faster fallback); the Phase 2 recall/precision evals pick the winner. NOT Sonnet 5.
> - **Structured outputs:** SURVIVES — Ollama JSON-schema `format` keeps the Phase 1
>   Pydantic contract. Do NOT use `client.messages.parse()`.
> - **Citations:** the Citations API is gone, but the grounding design never trusted
>   LLM citations — page refs are computed from the Phase 1 document map and
>   string-match verified. No capability lost. This is now mandatory, not optional.
> - **Files API / Batch API:** N/A (local, no upload limits, no per-token cost).
> - **Demo (Phase 5):** precompute the demo RFP with the local model once, serve the
>   cached result at $0. A local model cannot serve a public multi-user demo live.
>
> **Unchanged and still authoritative:** Python 3.12 / FastAPI / Uvicorn / pdfplumber /
> python-docx / XlsxWriter / Pydantic / SQLAlchemy+Postgres / RQ+Redis / React+Vite /
> Railway / R2 — only the model-inference client changes. `anthropic`, `tenacity`
> (for API 429s) and the Batch/Files/Citations rows are the parts that no longer apply.
> Full rationale in agent memory: `local-llm-stack-decision`, `no-api-key-use-claude-subscription`.

## Big-Picture Decision: Python Backend, Not Node
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Backend language | Document-AI ecosystem; Anthropic SDK first-class support |
| FastAPI | 0.139.2 | Backend web framework | Async, Pydantic-native (shares models with LLM extraction schemas), auto OpenAPI docs, the standard for Python AI apps |
| Uvicorn | 0.51.0 | ASGI server | FastAPI's standard server; works on Railway with `--host 0.0.0.0 --port $PORT` |
| anthropic (Python SDK) | 0.118.0 | Claude API client | Official SDK; `client.messages.parse(output_format=PydanticModel)` gives schema-guaranteed extraction (structured outputs is GA, no beta header) |
| Claude Sonnet 5 | `claude-sonnet-5` | Primary extraction/judgment model | 1M-token context (whole RFP sections fit in one call), 128k max output, $3/$15 per MTok ($2/$10 intro pricing through Aug 31, 2026) — the cost/intelligence sweet spot for high-volume extraction |
| PostgreSQL | 16+ (Railway managed) | Database | Requirements, cross-mappings, jobs, capability profiles are relational; Railway one-click provisioning |
| SQLAlchemy | 2.0.51 | ORM | Standard Python ORM, 2.0 API; pairs with Alembic migrations |
| RQ (Redis Queue) | 2.10.0 | Background job processing | Pipeline runs are 5–15 min multi-call LLM jobs — must run in a worker, not a request handler. RQ is the simplest battle-tested option; Celery is overkill for one queue |
| Redis | 7.x (Railway managed) | Queue backend + rate limiting | Required by RQ; doubles as demo-mode rate limiter store |
| React | 19.2.x | Frontend UI | Standard; portfolio-credible |
| Vite | 8.1.x | Frontend build | SPA build served as static files by FastAPI — one deployable web service, no CORS config |
| Tailwind CSS | 4.3.x | Styling | Fast polish for demo; pairs with shadcn/ui components |
### Document Processing
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pdfplumber | 0.11.10 | Local PDF text extraction with layout info | Section boundary detection (find "SECTION L", "SECTION M", SF30 blocks), page-to-text mapping, pre-chunking before Claude calls. MIT license — safe for the sellable-product future |
| python-docx | 1.2.0 | Word (.docx) parsing | Amendments/attachments delivered as .docx; extract paragraphs/tables to text |
| Claude native PDF + Citations | API feature (GA) | Layout-aware requirement extraction | The heavy lifting: send PDF (base64 or Files API `file_id`) with `citations: {enabled: true}`; responses include `page_location` citations with 1-indexed page ranges — feeds the matrix's section-reference column directly |
| Anthropic Files API | API feature | Upload large PDFs once, reference by `file_id` | Keeps request payloads under the 32MB limit across multi-pass extraction |
| XlsxWriter | 3.2.9 | Excel export | Write-only, fastest, richest formatting (frozen panes, autofilter, conditional formatting, column widths) — everything a compliance matrix export needs. CSV via stdlib `csv` |
| Docling | 2.114.0 | Upgrade path for gnarly tables/scanned PDFs | Only if accuracy testing shows pdfplumber + Claude misses table-heavy attachments. It's MIT but 5–30x slower and ships 1–2GB of model weights — a real burden on Railway. Defer until proven necessary |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic | 2.13.x | Schemas everywhere | Requirement/matrix models double as FastAPI response models and `messages.parse()` output schemas |
| Alembic | 1.18.5 | DB migrations | From day 1 — schema will evolve fast |
| psycopg[binary] | 3.2.x | Postgres driver | SQLAlchemy 2.0's recommended modern driver |
| httpx | 0.28.1 | SAM.gov API calls, attachment downloads | Async-capable, timeouts/retries |
| boto3 | 1.43.x | S3-compatible client for Cloudflare R2 | Uploaded RFP files + generated exports need storage both web and worker can reach |
| tenacity | latest | Retry with backoff | Claude API 429/529s and SAM.gov flakiness during multi-call pipelines |
| @tanstack/react-query | 5.101.x | Frontend job-status polling | Upload → poll status → download flow is its exact use case |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Python package/env management | Fast, lockfile-based; Railway's Railpack detects `uv.lock` |
| ruff | Lint + format | Single tool replaces black/flake8/isort |
| pytest | Testing | Golden-file tests against sample RFP extractions are the core quality gate |
| Railway CLI / MCP | Deployment | Multi-service: web (FastAPI + built SPA), worker (RQ), Postgres, Redis |
## Architecture-Relevant API Facts (verified 2026-07-22)
- **Structured outputs: GA.** `output_config.format` with JSON schema, or `strict: true` tools. Grammar-constrained — guaranteed valid JSON. No `minimum`/`maximum`/`minLength` constraints, no recursive schemas. First call per schema pays grammar-compilation latency; cached 24h.
- **PDF support:** 32MB max request; 600 pages max per request at 1M context (100 pages if context window under 1M). Each page processed as text + image (~1,500–3,000 tokens/page typical). Dense pages can blow context before page limits — chunk by section, not whole-package.
- **Citations:** GA on all active models. PDFs cite as `page_location` with 1-indexed `start_page_number`/`end_page_number`. **Scanned/image-only PDFs are not citable** (no extractable text) — detect these and fail gracefully or OCR first.
- **Validate in phase research:** whether citations and structured outputs combine in a single call. Safe design: extraction pass with citations enabled (free-form or tool-use), then a cheap structuring pass — or carry page refs through tool-use inputs.
- **Batch API:** 50% discount, up to 300k output tokens with beta header — ideal for precomputing demo-mode results and any non-interactive reprocessing.
- **Model tiering:** Sonnet 5 for extraction and L↔M↔C cross-mapping; Haiku 4.5 (`claude-haiku-4-5`, $1/$5) for cheap classification passes (shall/must/will triage); Opus 4.8 (`claude-opus-4-8`, $5/$25) only if compliance-judgment quality demands it.
- Endpoint: `https://api.sam.gov/opportunities/v2/search` (use v2; v1 is legacy). Separate description endpoint; attachments via `resourceLinks` URLs in search results, with API key appended to download.
- Auth: personal API key, requested from the SAM.gov Account Details page (requires SAM.gov account with login.gov).
- **Rate limits (MEDIUM confidence — official docs say "limited by role" without numbers; multiple secondary sources agree):** non-federal key without a role ≈ **10 requests/day**; non-federal with an entity role ≈ 1,000/day.
- **Design consequence:** 10/day is brutally low. Cache every SAM.gov response and downloaded attachment in Postgres/R2; never re-fetch; demo mode must use a preloaded package, never a live fetch. Treat SAM.gov fetch as a differentiator feature with hard caching, not a hot path.
- Deploy via GitHub repo; Railpack detects Python (`uv.lock`/`requirements.txt`). Two services from one repo with different start commands: web (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and worker (`rq worker --url $REDIS_URL`).
- Postgres and Redis are one-click managed services with injected env vars (`DATABASE_URL`, `REDIS_URL`).
- **Volumes mount to a single service only** — web and worker can't share one, which is why R2 object storage is recommended for files.
- Generate a public domain in service Networking settings for the demo URL.
## File Storage: Cloudflare R2
| Choice | Why |
|--------|-----|
| Cloudflare R2 (S3-compatible, via boto3) | Web service receives uploads; worker reads them; export files downloaded later — needs shared storage. R2: 10GB free tier, zero egress fees, standard S3 API. Railway volumes don't work across services |
## Installation
# Backend (uv)
# Frontend
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI + Vite SPA | Next.js 16 full-stack | If the pipeline were JS — but Python doc-parsing wins; don't split brains across two backends |
| pdfplumber + Claude native PDF | Docling (2.114.0) | Table-heavy attachments where Claude's native PDF reading proves insufficient; accept slower processing + 1–2GB model weights |
| pdfplumber | PyMuPDF 1.28 / pymupdf4llm | Faster and excellent layout output, **but AGPL-3.0** — fine for a pure open-source portfolio, a landmine for the "sellable product" goal. Only use if you'll buy the commercial license |
| RQ + Redis | Procrastinate 3.9 (Postgres-native queue) | If you want to drop the Redis service entirely; smaller community, but removes one moving part |
| RQ + Redis | Celery 5.6 | Only with multiple queues/complex routing/scheduled workflows — none needed here |
| XlsxWriter | openpyxl 3.1.5 | Only if you need to *read* an Excel template and fill it; XlsxWriter is write-only |
| Sonnet 5 | Opus 4.8 for compliance judgment | If judgment accuracy against capability profiles is weak at Sonnet tier |
| R2 | Railway volume | Only if you collapse to a single service running web + in-process jobs (not recommended for 5–15 min pipelines) |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LangChain / LlamaIndex | Unnecessary abstraction for a fixed, known pipeline; obscures prompts, complicates debugging, churns APIs. Your pipeline is deterministic stages, not agentic retrieval | Direct anthropic SDK + Pydantic schemas per stage |
| PyMuPDF (fitz) | AGPL-3.0 copyleft conflicts with sellable-product ambitions | pdfplumber (MIT), Docling (MIT) |
| AWS Textract / Azure Document Intelligence | Extra vendor, per-page cost, and Claude's native PDF ingestion with page citations already covers layout-aware reading | Claude PDF + citations |
| Celery | Config-heavy for a single-queue app; slows iteration | RQ |
| FastAPI `BackgroundTasks` for the pipeline | Runs in the web process — deploys/restarts kill 15-minute jobs, no retry, no status persistence | RQ worker + job table in Postgres |
| .doc (legacy Word) parsing libraries | Fragile; python-docx doesn't support .doc at all | Reject .doc uploads with a clear message (or convert via LibreOffice headless later) |
| MongoDB | Requirements ↔ sections ↔ mappings ↔ judgments are relational joins | Postgres |
| SAM.gov web scraping | ToS risk, brittle; official API exists | Opportunities API v2 with aggressive caching |
| Sending whole multi-hundred-page packages in one Claude call | Dense pages can exhaust even 1M context; failure modes are opaque | Section-level chunking (pdfplumber finds boundaries), one extraction call per section |
## Stack Patterns by Variant
- Precompute the demo RFP's full pipeline output via the Batch API (50% off) and serve cached results — a recruiter's 60-second demo should cost $0 in inference
- Rate-limit live uploads (Redis counter, e.g., N pipelines/day for anonymous users) and cap upload size/page count
- Swap the local text layer from pdfplumber to Docling for attachment files only (SOW pricing tables, CDRL lists); keep Claude citations as the extraction engine
- Register an entity to reach the 1,000/day tier, or ship SAM.gov fetch as "paste a SAM.gov link → we fetch once and cache forever"
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastapi 0.139.x | pydantic 2.13.x | FastAPI requires Pydantic v2; do not pin v1 |
| anthropic 0.118.0 | pydantic 2.x | `messages.parse()` accepts Pydantic v2 models directly |
| sqlalchemy 2.0.51 | psycopg 3.2.x | Use `postgresql+psycopg://` URL scheme (Railway's `DATABASE_URL` defaults to `postgresql://` — rewrite at startup) |
| rq 2.10 | redis-py 5.x/6.x | RQ 2.x dropped Python <3.8; fine on 3.12 |
| vite 8.x | react 19.2.x | Use `@vitejs/plugin-react`; Tailwind 4 uses the `@tailwindcss/vite` plugin (no PostCSS config) |
| Claude structured outputs | claude-sonnet-5, claude-haiku-4-5, claude-opus-4-8 | GA on all current models; no beta headers |
## Sources
- https://platform.claude.com/docs/en/about-claude/models/overview — model IDs, pricing, context windows (HIGH)
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs — GA status, schema limits, `messages.parse()` (HIGH)
- https://platform.claude.com/docs/en/build-with-claude/citations — PDF `page_location` citations, scanned-PDF limitation (HIGH)
- https://platform.claude.com/docs/en/build-with-claude/pdf-support — 32MB / 600-page limits, Files API guidance (HIGH)
- https://open.gsa.gov/api/get-opportunities-public-api/ — v2 endpoint, API key auth, resourceLinks (HIGH); exact per-role rate limits not published there
- SAM.gov rate-limit specifics: govconapi.com, boringdataplatform.com, DoD System Account User Guide — 10/day no-role, 1,000/day with role (MEDIUM — multiple secondary sources agree)
- PyPI JSON API (2026-07-22) — all Python package versions verified (HIGH)
- npm registry (2026-07-22) — react 19.2.8, vite 8.1.5, tailwindcss 4.3.3, next 16.2.11 (HIGH)
- https://docs.railway.com/guides/fastapi — Railway FastAPI deployment basics (MEDIUM; multi-service/worker patterns from Railway platform knowledge, verify at setup)
- PDF parser comparisons: pymupdf.io DocLayNet benchmark, unstract.com 2026 evaluation, file2markdown PyMuPDF4LLM-vs-Docling (MEDIUM — informed the "Claude does layout, local lib does segmentation" strategy)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
