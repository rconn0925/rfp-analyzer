# Roadmap: RFP Analyzer — Federal Compliance Matrix Generator

## Overview

Build the pipeline inside-out: prove parsing and section detection on hostile real-world federal PDFs first, then make requirement extraction provably accurate with verified references and evals, then layer on the analytical differentiators (cross-mapping, outline, compliance judgment) and practitioner-grade Excel export — all CLI-verifiable as a pure library. Only then wrap the proven pipeline in the async web app, and finally ship the public showcase: hosted demo mode a recruiter can try in 60 seconds, cost hardening, and SAM.gov fetch. Correctness phases (1–3) precede productization (4) and showcase (5) because matrix quality is capped by extraction quality, which is capped by parsing quality.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Parsing & Structure Foundation** - Multi-file federal packages parse into a structural document map with UCF section detection, quality gates, and SF30 identification (pure library + CLI) (completed 2026-07-24)
- [ ] **Phase 2: Requirement Extraction & Grounding** - Every requirement extracted verbatim with verified source references, type/keyword classification, keyword-sweep reconciliation, and golden-set evals
- [ ] **Phase 3: Analysis & Export** - Cross-mapping, proposal outline, compliance judgment, and practitioner-standard Excel/CSV export — full pipeline end-to-end via CLI
- [ ] **Phase 4: Web App & Job Orchestration** - Proven pipeline wrapped in an async web app: upload, background jobs with progress, profile authoring, persistent results
- [ ] **Phase 5: Public Demo, Hardening & SAM.gov Fetch** - Publicly hosted 60-second demo with cost controls, plus SAM.gov solicitation fetch

## Phase Details

### Phase 1: Parsing & Structure Foundation

**Goal**: Real federal RFP packages (multi-file PDF/DOCX) parse into an accurate, navigable document structure that everything downstream can trust
**Depends on**: Nothing (first phase)
**Requirements**: PARS-01, PARS-02
**Success Criteria** (what must be TRUE):

  1. Running the CLI harness on a multi-file federal RFP package (PDFs + DOCX) produces a document map with section hierarchy and page numbers for every file
  2. UCF section boundaries (L, M, C/SOW/PWS, H) are correctly detected on a standard solicitation, and a non-UCF package (e.g., FAR Part 12 combined synopsis) is flagged as non-standard instead of silently mis-sectioned
  3. Low-quality or scanned pages are caught by per-page quality gates and surfaced, never passed through as silent garbage text
  4. SF30 amendment files within a package are identified and labeled as amendments

**Plans:** 6/6 plans complete

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Scaffolding: uv project, document-map schema (Phase 2 contract), public GitHub repo + CI

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — 3-package SAM.gov corpus acquisition + MANIFEST (human-assisted; surfaces SAM.gov API key request)
- [x] 01-03-PLAN.md — Parsing layer: file discovery + hostile-input guards, pdfplumber PDF, python-docx DOCX

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — Per-page quality gates + header/footer stripping (flag-and-surface, no OCR)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-05-PLAN.md — UCF section detection w/ TOC disambiguation, SF form signatures, SF30 ladder, package classification

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-06-PLAN.md — CLI harness (dual output), corpus integration tests, human verification of success criteria

Note: SAM.gov API key request DEFERRED by user decision (2026-07-24). Upload / local-package intake is the product's intake path; the key only gates Phase 5's optional SAM.gov fetch. Phase 5 ships its public demo and hardening on upload intake alone — SAM.gov fetch becomes an optional add-on if a key is obtained later. No phase is blocked on it.

### Phase 2: Requirement Extraction & Grounding

**Goal**: Every requirement in a package is extracted verbatim with provably real source references — measurably, with recall/precision evals as the objective signal
**Depends on**: Phase 1
**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, INTK-03
**Success Criteria** (what must be TRUE):

  1. CLI extraction produces every requirement (shall/must/will/should statements, Section L instructions, Section M criteria, and requirements found in attachments/Sections C/H) as verbatim text with a stable requirement ID, type classification, and binding keyword
  2. Every source reference (document, section/paragraph, page) is computed from the document map and string-match verified against the source — no LLM-generated citation reaches output
  3. A deterministic shall/must/will/should keyword sweep reconciles against AI extraction and surfaces any missed candidate requirements
  4. SF30 amendment change statements appear as their own extracted rows with potentially modified requirements flagged — no silent merging
  5. Extraction recall/precision against a hand-shredded golden-set RFP is measured and reported on every run

**Plans:** 3/7 plans executed

Plans:
**Wave 1**
- [x] 02-01-PLAN.md — Requirement schema + shared normalizer + stable content-hash IDs (foundation contract)

**Wave 2** *(blocked on Wave 1)*
- [x] 02-02-PLAN.md — Verbatim grounding: rapidfuzz string-match verify + computed SourceRef (EXTR-02)
- [x] 02-03-PLAN.md — Section chunker + deterministic keyword sweep/reconcile + SF30 amendment flagging (EXTR-03/04/05, INTK-03)
- [ ] 02-04-PLAN.md — Golden set: agent-drafted + adversarially-validated ground truth for N4008526R0033
- [ ] (02-02 carries a blocking-human rapidfuzz legitimacy gate)

**Wave 3** *(blocked on Wave 2)*
- [ ] 02-05-PLAN.md — Ollama client (num_ctx guard) + prompt + extract orchestration (EXTR-01/02/03)

**Wave 4** *(blocked on Wave 3)*
- [ ] 02-06-PLAN.md — run_extraction pipeline entry + `extract` CLI subcommand + corpus e2e (EXTR-01/04/05, INTK-03)

**Wave 5** *(blocked on Wave 4)*
- [ ] 02-07-PLAN.md — Recall/precision/F1 eval harness + 14b-vs-32b bake-off + per-run reporting (success criterion 5)

### Phase 3: Analysis & Export

**Goal**: An extracted requirement set becomes a complete, judged, exportable compliance matrix — the full pipeline runs end-to-end via CLI on a real federal RFP
**Depends on**: Phase 2
**Requirements**: ANLZ-01, ANLZ-02, ANLZ-04, EXPT-01, EXPT-02, EXPT-03, EXPT-04
**Success Criteria** (what must be TRUE):

  1. Cross-mapping flags every L-without-M, M-without-L, and SOW-without-either gap or orphan across the requirement set
  2. A proposal outline (volumes/sections) is derived from Section L structure and every requirement is mapped to an outline node
  3. Each requirement carries a graded compliance judgment (Fully/Partially/Non-comply plus rationale and confidence) against a stored capabilities profile (fictional demo profile suffices at this stage)
  4. The exported .xlsx contains a compliance matrix sheet with practitioner-standard columns, a cross-reference matrix sheet, and a shred checklist sheet; the matrix is also downloadable as raw CSV
  5. The full pipeline runs CLI end-to-end on a real federal RFP: package in, populated matrix workbook out, no manual steps

**Plans**: TBD

### Phase 4: Web App & Job Orchestration

**Goal**: The proven pipeline library runs as an async web application — upload to download with no manual steps, results that persist
**Depends on**: Phase 3
**Requirements**: INTK-01, ANLZ-03, PIPE-01, PIPE-02, PIPE-03
**Success Criteria** (what must be TRUE):

  1. User can upload a multi-file federal RFP package (PDF/DOCX: base, SF30 amendments, attachments) via the web UI and start an analysis
  2. Analysis runs as an async background job with stage-level progress visible in the UI while it processes
  3. User can author a company capabilities profile by pasting free text in the UI and edit it later
  4. A completed analysis persists — user can return later to view results and re-download Excel/CSV exports without re-running the pipeline
  5. The full flow (upload → processing → populated matrix → download) completes with zero manual intervention

**Plans**: TBD
**UI hint**: yes

### Phase 5: Public Demo, Hardening & SAM.gov Fetch

**Goal**: The app is live at a public URL where a recruiter can experience the full product in ~60 seconds, with API costs bounded and SAM.gov as a second intake path
**Depends on**: Phase 4
**Requirements**: DEMO-01, DEMO-02, DEMO-03, INTK-02
**Success Criteria** (what must be TRUE):

  1. The app is reachable at a stable public URL
  2. An anonymous visitor can experience the full demo (precomputed sample-RFP analysis + fictional company profile, zero live LLM calls) in ~60 seconds
  3. Live (non-demo) processing is protected by per-IP rate limiting and a daily spend kill-switch that bounds public API cost
  4. User can paste a SAM.gov solicitation number or link and the package (notice + attachments) is fetched into the same pipeline, with graceful degradation to upload when fetch fails or quota is exhausted

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Parsing & Structure Foundation | 6/6 | Complete   | 2026-07-24 |
| 2. Requirement Extraction & Grounding | 3/7 | In Progress|  |
| 3. Analysis & Export | 0/TBD | Not started | - |
| 4. Web App & Job Orchestration | 0/TBD | Not started | - |
| 5. Public Demo, Hardening & SAM.gov Fetch | 0/TBD | Not started | - |

---
*Roadmap created: 2026-07-22*
