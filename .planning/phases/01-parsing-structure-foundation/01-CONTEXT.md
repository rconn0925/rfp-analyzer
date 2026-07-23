# Phase 1: Parsing & Structure Foundation - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Multi-file federal RFP packages (PDF/DOCX) parse into an accurate, navigable document structure that everything downstream can trust: per-file text with page/heading preservation, a structural document map (section hierarchy + page numbers), UCF section detection (L, M, C/SOW/PWS, H) with honest non-UCF classification, per-page quality gates, and SF30 amendment file identification. Pure Python library + CLI harness — no web code, no LLM extraction (that's Phase 2), no OCR.

</domain>

<decisions>
## Implementation Decisions

User delegated all gray areas to Claude's judgment ("take the wheel"). Decisions below were made against the research corpus (.planning/research/) and are locked unless contradicted by evidence during execution.

### Test Corpus
- **D-01:** Validate against a 3-package minimum real-world corpus, manually downloaded from the SAM.gov website (no API key needed for browsing/downloading attachments):
  1. **Clean full-UCF multi-file services solicitation** — base + at least one SF30 amendment + attachments, moderate size (~100–300 pages total). This is the primary package and should be chosen deliberately: the same package becomes Phase 2's hand-shredded golden set.
  2. **Hostile package** — contains scanned pages (a scanned/rescanned SF30 is the ideal specimen) to exercise quality gates.
  3. **Non-UCF package** — FAR Part 12 combined synopsis/solicitation (SF 1449) to prove honest degradation ("non-standard structure" classification, not garbage sections).
- **D-02:** Corpus PDFs/DOCX are **gitignored** (large binaries in a public repo). Commit a `tests/corpus/MANIFEST.md` documenting each package: SAM.gov notice link, solicitation number, file list with checksums, and why it was selected. Small excerpt fixtures (single pages/sections) may be committed for unit tests.

### Scanned-Page Handling
- **D-03:** **Flag-and-surface only in Phase 1 — no OCR.** Quality gates detect near-empty text layers (scanned-page indicator), gibberish ratio, and repeated header/footer noise (strip headers/footers before downstream use). Per-page quality status is recorded in the document map; low-quality pages are excluded from usable text with an explicit surfaced note (e.g., "pages 45–52: scanned image, no text layer"), never passed through silently.
- **D-04:** Docling (MIT) remains the pre-identified OCR/table fallback, adopted **only on eval evidence** in a later phase — not speculatively.

### CLI Output Format
- **D-05:** The CLI harness emits **both** artifacts per run:
  - **Canonical JSON document map** — Pydantic-schema'd, versioned; this is the pipeline contract Phase 2 consumes. Written to an artifacts directory.
  - **Human-readable section tree report** to stdout — files → package classification (full UCF / partial / non-UCF / unknown) → section hierarchy with page ranges → per-page quality flags → amendment labels. This is how the phase success criteria get eyeballed.
- **D-06:** CLI shape: point it at a package directory, get artifacts out (e.g., `parse <package-dir> --out <artifacts-dir>`). Exact command naming and arg design is Claude's discretion.

### Repo & Scaffolding
- **D-07:** **Public GitHub repo from day 1.** Clean, disciplined commit history is itself showcase evidence (PROJECT.md lists a clean public repo as a core goal). Secrets via env vars only; corpus files gitignored per D-02.
- **D-08:** Tooling from the start: **uv** (env/lockfile), **ruff** (lint+format), **pytest**. GitHub Actions CI running lint + tests from Phase 1 onward.
- **D-09:** Cost-per-run instrumentation **scaffolding** lands in Phase 1 (counters/plumbing in the pipeline library), even though Phase 1 itself makes zero LLM calls — research flags per-run cost as needed early for demo-mode decisions.

### Claude's Discretion
- Section-detection heuristics and pdfplumber tuning (regexes vs. layout signals for "SECTION L" boundaries, SF30 form detection approach)
- JSON document-map schema details (must carry: per-file identity, section hierarchy with page ranges, per-page quality status, amendment labels, package classification)
- Exact quality-gate thresholds (chars/page, gibberish ratio) — tune against the corpus
- Repo layout within the locked constraint that `pipeline/` is a pure library (no HTTP, no queue imports)
- CLI command naming/UX

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Research (stack, architecture, pitfalls — all locked project-level)
- `.planning/research/SUMMARY.md` — resolved stack/architecture decisions (Postgres queue not Redis, R2 files, pdfplumber not PyMuPDF), phase rationale, confidence assessment
- `.planning/research/PITFALLS.md` — Pitfalls 3 (non-UCF assumption) and 4 (parsing garbage cascade) are THE pitfalls this phase exists to prevent; contains warning signs and verification checklists
- `.planning/research/STACK.md` — pinned versions, license constraints (MIT-only parsing layer), what NOT to use
- `.planning/research/ARCHITECTURE.md` — pure-library boundary, staged pipeline artifact model, provenance envelopes
- `.planning/research/FEATURES.md` — downstream matrix column requirements that constrain what the document map must capture

### Project docs
- `.planning/ROADMAP.md` — Phase 1 goal + 4 success criteria (document map, UCF detection + honest non-UCF flagging, quality gates, SF30 identification)
- `.planning/REQUIREMENTS.md` — PARS-01, PARS-02 (this phase); EXTR-* (Phase 2 consumers of this phase's output)
- `CLAUDE.md` — condensed stack reference and project constraints

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield. Repo contains only CLAUDE.md and .planning/. Phase 1 creates the codebase.

### Established Patterns
- Stack is research-locked, not open: Python 3.12+ / pdfplumber 0.11 / python-docx / Pydantic 2.13 / uv / ruff / pytest. No PyMuPDF (AGPL), no LangChain.
- `pipeline/` must be a pure library — every stage `f(artifact) → artifact`, no HTTP/queue imports. This is the single most important architectural boundary (enables CLI validation now, web wrap in Phase 4).

### Integration Points
- Phase 2 consumes the JSON document map (section hierarchy + page provenance) for section-aware chunking with provenance envelopes — the schema designed here is Phase 2's input contract.

</code_context>

<specifics>
## Specific Ideas

- **User action item at phase start:** Request the SAM.gov API key (requires SAM.gov account via login.gov; key from Account Details page). ~10 business day issuance; Phase 5 depends on it. This is a Ross-personal task the executor should surface, not perform.
- Corpus packages should be genuinely hostile — the research warns that testing on clean born-digital PDFs confirms false confidence. The scanned-SF30 and non-UCF packages are deliberate stress tests, not afterthoughts.

</specifics>

<deferred>
## Deferred Ideas

- **OCR fallback (Docling)** — deferred until eval evidence shows pdfplumber + Claude native PDF insufficient (likely evaluated Phase 2+). Phase 1 only flags scanned pages.
- **Header/footer-aware table extraction improvements** — only if corpus evidence demands; Docling is the designated path.

</deferred>

---

*Phase: 1-Parsing & Structure Foundation*
*Context gathered: 2026-07-22*
