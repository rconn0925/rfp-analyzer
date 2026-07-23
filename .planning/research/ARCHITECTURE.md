# Architecture Research

**Domain:** AI document-intelligence pipeline — federal RFP analysis / compliance matrix generation
**Researched:** 2026-07-22
**Confidence:** MEDIUM-HIGH (pipeline patterns are well-established and verified against multiple current sources; SAM.gov API specifics verified against official GSA docs; some implementation details are training-data-informed and flagged)

## Standard Architecture

Systems in this class (RFP shredders, contract analyzers, regulatory extraction tools) converge on the same shape: a **staged, checkpointed pipeline** run by an async worker, with a thin web layer that submits jobs and polls status. The pipeline itself — not the web app — is the product. Commercial RFP shredding tools (GovEagle, Sweetspot, RFP Extract) all follow intake → parse → extract → cross-map → matrix, with human review layered on top; this project deliberately omits the review layer for v1.

### System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                          WEB LAYER                                 │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────────┐     │
│  │  Upload UI   │  │ Progress View │  │ Matrix View + Export│     │
│  │ (multi-file) │  │ (poll status) │  │ (table + .xlsx/.csv)│     │
│  └──────┬───────┘  └──────┬────────┘  └─────────┬───────────┘     │
├─────────┴─────────────────┴─────────────────────┴──────────────────┤
│                       API SERVICE (Railway service #1)             │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌────────────────────┐  │
│  │ Intake    │ │ Job Status│ │ Export   │ │ Demo Mode          │  │
│  │ endpoints │ │ endpoint  │ │ endpoint │ │ (serves snapshots, │  │
│  │ + SAM.gov │ │ (polled)  │ │ (xlsx/   │ │  never calls LLM)  │  │
│  │ fetch     │ │           │ │  csv)    │ │                    │  │
│  └─────┬─────┘ └─────┬─────┘ └────┬─────┘ └────────┬───────────┘  │
│        │ enqueue job │ read       │ read           │ read          │
├────────┴─────────────┴────────────┴────────────────┴───────────────┤
│                    POSTGRES (Railway service #2)                   │
│   jobs/runs · documents · parsed artifacts · requirements ·        │
│   cross-refs · outline · profiles · judgments · demo snapshots     │
├────────────────────────────────────────────────────────────────────┤
│                   WORKER SERVICE (Railway service #3)              │
│              claims jobs from Postgres queue, runs:                │
│                                                                    │
│  ┌────────┐ ┌────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ ┌──────┐ │
│  │ Parse  │→│ Chunk  │→│ Extract │→│ Cross- │→│ Outline│→│Judge │ │
│  │ (PDF→  │ │(section│ │ (LLM,   │ │ ref    │ │ map    │ │(LLM  │ │
│  │ struct)│ │ -aware)│ │ per-    │ │ L↔M↔C  │ │ (from  │ │ vs   │ │
│  │        │ │        │ │ chunk)  │ │ (LLM)  │ │ Sec L) │ │profile)│
│  └────────┘ └────────┘ └─────────┘ └────────┘ └────────┘ └──────┘ │
│       each stage writes its output artifact + progress to Postgres │
├────────────────────────────────────────────────────────────────────┤
│                        EXTERNAL SERVICES                           │
│   LLM API (Anthropic/OpenAI) · SAM.gov Opportunities API v2        │
└────────────────────────────────────────────────────────────────────┘
```

Three Railway services total: **API**, **worker**, **Postgres**. This is Railway's documented SaaS-backend pattern (API + Postgres + workers over private networking). No Redis for v1 — use a Postgres-backed job queue (see Pattern 4) to cut one service and one failure mode.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Intake | Accept multi-file uploads (base + amendments + attachments); fetch packages from SAM.gov; classify files (base solicitation / SF30 amendment / attachment); create `rfp_package` + `document` rows; enqueue pipeline job | FastAPI multipart upload; SAM.gov Get Opportunities API v2 (`resourceLinks` field gives attachment download URLs) |
| Parser | PDF/Word → structured text with **page numbers and heading hierarchy preserved**; OCR fallback for scanned pages | PyMuPDF/PyMuPDF4LLM fast path (milliseconds/page, no ML models); Docling as OCR/layout fallback for scanned or messy PDFs |
| Section mapper | Detect UCF structure (Sections A–M, or SOW/PWS in attachments); build a section tree per document | Regex/heading heuristics for "SECTION L", "L.4.2", etc. + a cheap LLM pass to label ambiguous documents |
| Chunker | Split at section boundaries; every chunk carries a provenance envelope `{doc_id, section_path, page_start, page_end}` | Pure function over the parsed document model; no embeddings needed |
| Extractor | Per-chunk structured LLM calls → requirement records (verbatim text, section ref, page, type, binding level) with schema validation; then a dedupe/merge pass | LLM tool-use / JSON schema output; Pydantic validation; map-reduce over chunks |
| Cross-referencer | L↔M↔C linking, gap and orphan detection — operates on **extracted requirement sets**, not raw documents | LLM matching over compact requirement summaries (fits in one or few calls once shredded) |
| Outline mapper | Derive proposal volume/section outline from Section L instructions; assign every requirement an outline address | LLM pass over Section L requirements → outline tree; then assignment pass |
| Compliance judge | Per requirement vs. stored capabilities profile → status + rationale + cited profile evidence | LLM calls batched by outline section; profile passed as structured context |
| Matrix assembler / Export | Join requirements + cross-refs + outline + judgments into the matrix; render .xlsx/.csv | SQL view/query + openpyxl or XlsxWriter; export generated on demand from DB, never stored as the source of truth |
| Job orchestrator | Stage sequencing, checkpointing, resume-from-stage, progress %, token/cost accounting, failure capture | Jobs table in Postgres (`FOR UPDATE SKIP LOCKED` claim); worker loop; each stage idempotent |
| Demo mode | Serve a precomputed snapshot of the sample RFP run; optionally replay stage events with delays; **zero LLM calls on the public demo path** | Snapshot rows flagged `is_demo`; replay reads persisted stage timeline |

## Recommended Project Structure

Backend-centric layout (Python assumed; adjust to STACK.md's final call). The critical decision is that **the pipeline is a plain library with no knowledge of HTTP or jobs** — the API and worker are thin shells around it.

```
rfp-analyzer/
├── pipeline/                 # Pure pipeline library — no FastAPI, no queue imports
│   ├── models.py             # Pydantic domain models (Requirement, Chunk, Judgment...)
│   ├── intake/               # File classification, SAM.gov client
│   ├── parsing/              # PDF/Word → ParsedDocument (pages, blocks, headings)
│   ├── sectioning/           # UCF section detection, section tree
│   ├── chunking/             # Section-aware chunking + provenance envelopes
│   ├── extraction/           # Per-chunk LLM extraction, merge/dedupe
│   ├── crossref/             # L↔M↔C mapping, gap/orphan detection
│   ├── outline/              # Section L → proposal outline, requirement assignment
│   ├── judgment/             # Compliance judgment vs. capability profile
│   ├── export/               # Matrix assembly, xlsx/csv rendering
│   └── llm/                  # Provider client, structured-output helpers,
│                             #   retry, token/cost accounting
├── app/                      # API service (FastAPI)
│   ├── routes/               # intake, jobs, matrix, export, demo
│   ├── db/                   # SQLAlchemy models, migrations (Alembic)
│   └── limits.py             # rate limiting, budget guards
├── worker/                   # Worker service
│   ├── runner.py             # job claim loop (SKIP LOCKED), stage dispatcher
│   └── stages.py             # stage registry: name → pipeline fn + checkpoint I/O
├── web/                      # Frontend (upload, progress, matrix views)
├── fixtures/                 # Demo sample RFP files + fictional company profile
├── evals/                    # Hand-shredded ground truth + extraction scoring
│                             #   (recall/precision on the sample RFP)
└── scripts/                  # run_pipeline_local.py — full pipeline via CLI, no web
```

### Structure Rationale

- **pipeline/ as a pure library:** the single most important boundary. Every stage is `f(input_artifact) → output_artifact`. This lets you build and validate the entire pipeline from `scripts/run_pipeline_local.py` against real RFPs *before any web code exists* — which matches the project's core value ("if the extraction is wrong, nothing else matters").
- **app/ and worker/ as separate deployables sharing pipeline/ + db models:** Railway deploys them as two services from one repo (different start commands). They communicate only through Postgres.
- **evals/:** requirement extraction is the product. A small ground-truth set (one hand-shredded sample RFP) with a recall/precision script is the difference between "seems to work" and "provably works" — and is itself showcase material.
- **fixtures/:** demo content is versioned code, not database-only state, so the demo snapshot can be regenerated deterministically.

## Architectural Patterns

### Pattern 1: Staged Pipeline with Persisted Checkpoints

**What:** The pipeline is a linear sequence of named stages (`parse → section → chunk → extract → crossref → outline → judge → assemble`). Each stage reads its predecessor's artifact from Postgres, writes its own artifact (JSONB or rows), and updates the run's `current_stage` + progress. A failed run resumes from the last completed stage.

**When to use:** Any multi-minute LLM pipeline. Non-negotiable here.

**Trade-offs:** Slightly more plumbing than one big function; in exchange you get resumability (an LLM 500 at minute 6 doesn't cost you minutes 1–5 of paid tokens), per-stage debuggability (inspect exactly what extraction produced before blaming cross-referencing), and free progress reporting. Current extraction-toolkit literature (e.g., DELM) explicitly calls out interruption-safe resumption and provenance/cost tracking as core design requirements.

**Example:**
```python
STAGES = ["parse", "section", "chunk", "extract", "crossref", "outline", "judge", "assemble"]

def run_job(job_id: str):
    run = load_run(job_id)
    for stage in STAGES[STAGES.index(run.current_stage):]:
        artifact_in = load_artifact(job_id, prev(stage))
        artifact_out = STAGE_FNS[stage](artifact_in, ctx=run.context)  # pure pipeline fn
        save_artifact(job_id, stage, artifact_out)                     # checkpoint
        update_progress(job_id, stage=stage, pct=stage_pct(stage))
```

### Pattern 2: Section-Aware Chunking with a Provenance Envelope

**What:** Chunk at detected section boundaries (not fixed token windows). Each chunk is `{text, doc_id, doc_name, section_path: "L.4.2", page_start, page_end, parent_heading}`. Oversized sections split at paragraph boundaries, with the parent heading re-injected into each sub-chunk. Every extracted requirement inherits its chunk's provenance, so section references in the matrix are *carried structurally*, never asked of the LLM ("what page was that on?" is a hallucination invitation).

**When to use:** Any extraction task where the output must cite locations. This is the standard pattern in grounded-extraction tools (Google's LangExtract, hierarchical-chunking RAG pipelines) and it's what makes the "section reference" column of the matrix trustworthy.

**Trade-offs:** Requires decent section detection first — worth it, because federal UCF structure (Sections A–M) is unusually regular, which is exactly why the project scoped to federal-only.

### Pattern 3: Map-Reduce Extraction (Not Whole-Document, Not RAG)

**What:** Extraction is **exhaustive**: every chunk gets an LLM call with a strict output schema ("list every requirement in this text; return verbatim quote + binding keyword + type; return empty list if none"), run with bounded concurrency (map). A merge pass dedupes cross-chunk repeats and normalizes requirement IDs (reduce). Cross-referencing and judgment then run over the *compact extracted set*, which fits in few calls.

**When to use:** High-recall extraction over long documents. A 300-page RFP may technically fit in a 200K–1M context window, but recall degrades on long single-pass extraction ("lost in the middle"), and one giant call gives you no per-section provenance, no partial progress, and an all-or-nothing failure mode.

**Trade-offs:** More calls (higher orchestration effort, though chunk-parallelism makes it *faster* wall-clock than one serial mega-call); dedupe logic needed at section overlaps. Do not reach for embeddings/vector search here — RAG answers "find relevant passages," this problem is "process every passage."

**Example:**
```python
async def extract_all(chunks: list[Chunk]) -> list[Requirement]:
    sem = asyncio.Semaphore(5)                      # concurrency + cost guard
    async def one(chunk):
        async with sem:
            reqs = await llm_extract(chunk.text, schema=RequirementList)  # tool-use/JSON schema
            return [r.with_provenance(chunk) for r in reqs.items]          # structural, not asked
    results = await asyncio.gather(*[one(c) for c in chunks])
    return dedupe_and_number(flatten(results))
```

### Pattern 4: Postgres-Backed Job Queue + Status Polling

**What:** A `jobs` table is the queue. API inserts a row; worker claims with `SELECT ... FOR UPDATE SKIP LOCKED`; frontend polls `GET /jobs/{id}` every ~2s for `{status, current_stage, pct, stage_timeline}`.

**When to use:** Single-worker, minutes-long jobs at showcase scale. Skip Celery/Redis/RabbitMQ for v1 — the jobs table *is also* the progress record and the run history, and it's one fewer Railway service to pay for and operate. Polling beats SSE/WebSockets for v1: trivial on Railway, no connection-lifetime concerns, and 2s granularity is plenty for a stage-level progress bar.

**Trade-offs:** Polling adds a little chatter; Postgres queues are "wrong" at high throughput (irrelevant here). Migration path if it ever matters: swap the claim loop for RQ/Celery + Redis without touching pipeline code — Railway's own guidance is API + Postgres + Redis-queue workers at scale.

### Pattern 5: Demo Snapshot + Replay (Zero-Cost Public Demo)

**What:** The demo sample RFP is processed **once** (locally or via an admin-only trigger) against the fictional company profile; the full run — including the stage-by-stage timeline with timestamps — is persisted and flagged `is_demo`. The public demo has two modes: (a) *instant*: show the finished matrix immediately; (b) *replay*: stream the recorded stage timeline with compressed delays (~30–45s total) so a recruiter watches the pipeline "work." Neither touches the LLM API.

**When to use:** Any public-URL AI showcase. This is the only way a public demo and a fixed budget coexist.

**Trade-offs:** Replay is theater — label it honestly ("replaying a recorded analysis") to keep credibility with technical evaluators; the "run your own RFP" path stays real and sits behind rate limits + budget guard (per-IP limit, queue-depth cap, monthly token ceiling that flips uploads to a waitlist message).

## Data Flow

### Primary Flow: Upload → Matrix

```
User uploads files (or enters SAM.gov solicitation #)
    ↓
API: classify files → rfp_package + document rows → files stored → job enqueued
    ↓                                                    (return job_id immediately)
Worker claims job → for each stage:
    parse:    document files → ParsedDocument{pages, blocks, headings}   → artifact
    section:  ParsedDocuments → section trees (UCF map per doc)          → artifact
    chunk:    section trees → chunks with provenance envelopes           → artifact
    extract:  chunks →(LLM×N, bounded concurrency)→ requirement rows     → DB rows
    crossref: requirements →(LLM)→ link rows + gap/orphan flags          → DB rows
    outline:  Section-L reqs →(LLM)→ outline tree + assignments          → DB rows
    judge:    requirements × capability_profile →(LLM)→ judgment rows    → DB rows
    assemble: mark run complete; matrix now queryable
    ↓ (each stage: progress row updated)
UI polls GET /jobs/{id} → renders stage progress bar
    ↓ on complete
UI: GET /packages/{id}/matrix → table view
UI: GET /packages/{id}/export?fmt=xlsx → openpyxl render from DB → download
```

**Direction rules:** UI → API only (never worker). API → Postgres only (never LLM, never long work in request handlers — the sole exception is the SAM.gov metadata lookup, which is fast; attachment downloads happen in the worker's parse stage). Worker → Postgres + LLM + SAM.gov file downloads. Pipeline library → no I/O ownership; artifacts in, artifacts out (worker owns persistence).

### Core Data Model

```
rfp_package 1─* document (kind: base|amendment|attachment; original file bytes/ref)
rfp_package 1─* pipeline_run (status, current_stage, pct, cost_tokens, error, is_demo)
pipeline_run 1─* stage_artifact (stage name, JSONB payload)     ← checkpoints
rfp_package 1─* requirement (req_id, section_ref, page, verbatim_text,
                             type: L_instruction|M_eval|C_performance|other,
                             binding: shall|must|will|should, confidence)
requirement *─* requirement  via cross_reference (relation: L↔M|L↔C|M↔C; + gap/orphan flags)
rfp_package 1─1 outline_tree (volumes/sections from Section L)
requirement *─1 outline_node (assignment)
capability_profile (versioned JSON: capabilities, certs, past performance)  ← demo ships one fictional profile
requirement × capability_profile → compliance_judgment (status: compliant|partial|gap|unknown,
                                                        rationale, evidence_refs)
MATRIX = query joining requirement + cross_reference + outline + judgment   ← a view, not a table
```

File storage for v1: original uploads as Postgres `bytea` (federal packages are typically tens of MB; both API and worker need access, and Railway volumes attach to a single service). Migration path: S3-compatible object storage (e.g., R2) when packages or traffic grow. (LOW-MEDIUM confidence on this call — revisit in STACK research; the boundary — "documents are stored behind a `FileStore` interface" — matters more than the backend.)

## Suggested Build Order

Dependencies run bottom-up: the matrix is only as good as extraction, and extraction is only as good as parsing/sectioning. Build the pipeline inside-out with a CLI harness, then wrap it in web/jobs, then add showcase layers.

| Order | Component | Depends on | Why this position |
|-------|-----------|------------|-------------------|
| 1 | Domain models + parsing + section mapping (CLI harness, real RFP fixture) | — | Everything downstream consumes ParsedDocument + section tree; federal section detection is the riskiest deterministic piece — prove it first |
| 2 | Chunking + LLM extraction + merge, with evals/ ground truth | 1 | The core value; validate recall on a hand-shredded sample before building anything else |
| 3 | Cross-referencing (L↔M↔C) + outline mapping | 2 | Operates purely on extracted requirements |
| 4 | Capabilities profile schema + compliance judgment | 2 (not 3) | Independent of cross-ref; needs profile design decision |
| 5 | Matrix assembly + Excel/CSV export | 2–4 | First end-to-end deliverable — full pipeline works via CLI |
| 6 | Postgres persistence + job orchestration + worker + progress API | 5 | Wrap the proven library in the async shell |
| 7 | Web UI: upload → progress → matrix → download | 6 | Thin layer over existing endpoints |
| 8 | Demo mode (snapshot + replay) + rate limiting + budget guard + Railway deploy | 7 | Requires a working run to snapshot; gate before the URL goes public |
| 9 | SAM.gov fetch intake | 6 | Differentiator, additive to intake; **request the api.sam.gov API key in week 1** — issuance reportedly takes ~10 business days |

Phase-structure implication for the roadmap: steps 1–5 are "pipeline correctness" phases (CLI-verifiable, eval-driven, likely needing per-phase research on extraction prompting); 6–8 are "productization" phases (standard web patterns, low research need); 9 is an integration phase (external-API risk, MEDIUM research need).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Showcase (demo + occasional real runs) | Everything above as-is; one worker; Postgres queue; demo snapshot absorbs ~all public traffic |
| Small paid product (tens of runs/day) | Add Redis + RQ/Celery, 2+ workers; move files to object storage; per-account budgets; likely add the deferred review/edit UI |
| Beyond | Split parse (CPU-bound) from LLM stages (I/O-bound) into separate worker pools; batch/priority queues |

### Scaling Priorities

1. **First bottleneck: LLM cost/latency per run.** Mitigate from day one via chunk-level concurrency limits, per-run token accounting on the `pipeline_run` row, model tiering (cheap model for section labeling/classification, strong model for extraction and judgment), and checkpointing so retries never re-pay completed stages.
2. **Second bottleneck: worker memory on large scanned PDFs** (OCR path). Mitigate by streaming page-by-page parsing and capping accepted package size.

## Anti-Patterns

### Anti-Pattern 1: Whole-Document Single-Prompt Extraction

**What people do:** Dump the entire RFP into a long-context model, ask for "all requirements as JSON."
**Why it's wrong:** Recall degrades over long contexts and a compliance matrix is a recall product — one missed "shall" is a non-compliant proposal. You also lose page/section provenance, partial progress, and get an all-or-nothing failure on a multi-dollar call.
**Do this instead:** Pattern 3 (map-reduce over section-aware chunks with structural provenance).

### Anti-Pattern 2: Running the Pipeline in the HTTP Request

**What people do:** `POST /analyze` does parsing + N LLM calls inline, frontend spinner for 5 minutes.
**Why it's wrong:** Proxy/platform timeouts, no progress, no resume, redeploys kill in-flight runs.
**Do this instead:** Enqueue-and-poll (Pattern 4); API returns `job_id` in milliseconds.

### Anti-Pattern 3: Storing Only the Final Matrix

**What people do:** Persist just the end result; intermediate stage outputs are ephemeral in-memory data.
**Why it's wrong:** When the matrix is wrong (it will be, during development), you can't tell whether parsing, sectioning, extraction, or judgment failed — and every debugging iteration re-pays the full token bill.
**Do this instead:** Persist every stage artifact (Pattern 1). Stage artifacts are also the raw material for the eval harness and the demo replay.

### Anti-Pattern 4: Embeddings/RAG for Requirement Extraction

**What people do:** Chunk → embed → vector DB → retrieve "relevant" chunks → extract.
**Why it's wrong:** Retrieval is for answering questions over documents; shredding must process *every* chunk exhaustively. A vector store adds infrastructure and, worse, silently caps recall at retrieval quality.
**Do this instead:** Iterate all chunks. (Embeddings may later help cross-referencing candidate-pairing at scale — not needed for v1, where extracted requirement sets are small enough for direct LLM matching.)

### Anti-Pattern 5: Trusting the LLM with Provenance or Free-Text Output

**What people do:** Ask the model "which section/page is this from?"; parse markdown-ish free text into fields.
**Why it's wrong:** Section/page hallucination destroys the matrix's core credibility; free-text parsing breaks constantly.
**Do this instead:** Provenance travels on the chunk envelope (Pattern 2); all LLM calls use structured output / tool-use with schema validation (Pydantic), rejecting and retrying invalid payloads.

### Anti-Pattern 6: Live LLM Calls on the Public Demo Path

**What people do:** Demo button triggers a real pipeline run for every visitor.
**Why it's wrong:** A shared link that gets traffic becomes an uncapped bill; a slow/failed run in front of a recruiter is worse than no demo.
**Do this instead:** Pattern 5 — snapshot + optional replay; real runs gated by rate limits and a hard monthly budget kill-switch.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SAM.gov Get Opportunities API v2 | REST + API key; search by solicitation number → opportunity record; `resourceLinks` array → attachment file download URLs; separate description endpoint returns HTML | Key request reportedly takes ~10 business days — file for it at project start. Do metadata lookup in the API service (fast), file downloads in the worker. Amendments appear as related notices; package assembly logic must merge them. (MEDIUM confidence on exact field behaviors — verify against open.gsa.gov docs during build) |
| LLM provider (Anthropic/OpenAI) | Provider client isolated in `pipeline/llm/`; structured outputs; retries with backoff; per-call token logging rolled up to `pipeline_run.cost_tokens` | Model tiering: cheap/fast model for classification and section labeling; strongest model for extraction and compliance judgment |
| Railway | Monorepo, 3 services (API, worker, Postgres) with distinct start commands; private networking; env-var config | Workers are plain long-running services on Railway (no special job infra); healthcheck the API, not the worker |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Web UI ↔ API | REST + polling | UI never talks to worker or DB |
| API ↔ Worker | Postgres jobs table only (insert / claim / status) | No direct RPC; both stateless against Postgres |
| API & Worker ↔ pipeline/ | Direct library import | Pipeline stays I/O-free (artifacts in/out) so the CLI harness, tests, worker, and evals all drive the same code |
| Pipeline ↔ LLM provider | Only via `pipeline/llm/` client | Single choke point for cost accounting, budget enforcement, model swaps, and record/replay in tests |
| Demo ↔ Pipeline | None at runtime | Demo reads persisted snapshot rows only; snapshots regenerated via admin/CLI trigger |

## Sources

- [SAM.gov Get Opportunities Public API — GSA Open Technology](https://open.gsa.gov/api/get-opportunities-public-api/) — official API, `resourceLinks` for attachments (HIGH)
- [SAM.gov API guide (GovCon API, 2026)](https://govconapi.com/sam-gov-api-guide) — key issuance timing, attachment access patterns (MEDIUM)
- [Railway: Choose Between Cron Jobs, Background Workers, and Queues](https://docs.railway.com/guides/cron-workers-queues) and [Deploy a SaaS Backend with Postgres, Workers, and Webhooks](https://docs.railway.com/guides/saas-backend) — official worker/queue patterns on Railway (HIGH)
- [FastAPI background tasks: BackgroundTasks vs ARQ/Redis](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/), [Handling long-running jobs in FastAPI](https://mrcompiler.medium.com/handling-long-running-jobs-in-fastapi-with-celery-rabbitmq-9c3d72944410) — job-queue tradeoffs (MEDIUM)
- [DELM: Data Extraction with Language Models toolkit (arXiv)](https://arxiv.org/pdf/2509.20617) — staged extraction pipelines, caching, schema validation, resumption (MEDIUM)
- [LangExtract deep dive — grounded extraction with source offsets](https://shubh7.medium.com/a-technical-deep-dive-into-googles-langextract-grounded-visual-and-scalable-information-afb0e7216da0) — provenance-grounded extraction pattern (MEDIUM)
- [Microsoft: reusable pipelines for large semi-structured docs](https://techcommunity.microsoft.com/blog/azurearchitectureblog/from-large-semi-structured-docs-to-actionable-data-reusable-pipelines-with-adi-a/4474054) — chunking with cross-page reference preservation (MEDIUM)
- [PyMuPDF4LLM vs Docling comparison](https://www.file2markdown.ai/blog/pymupdf4llm-vs-docling), [Best open-source PDF-to-Markdown tools 2026](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026) — parser layer options (MEDIUM)
- [Loopio: RFP shredding process](https://loopio.com/blog/rfp-shredding/), [GovEagle: RFP automation for federal contractors](https://www.goveagle.com/blog/rfp-response-automation-federal), [Sweetspot: RFP shredding tools for GovCon](https://www.sweetspot.so/blog/rfp-shredding-tools-government-contractors/) — commercial-tool pipeline shape, L↔M mapping practice (MEDIUM)
- Training-data knowledge of UCF (Sections A–M) solicitation structure, map-reduce extraction, and Postgres `SKIP LOCKED` queues — cross-checked against the above (MEDIUM where not independently verified)

---
*Architecture research for: AI-powered federal RFP compliance matrix generation*
*Researched: 2026-07-22*
