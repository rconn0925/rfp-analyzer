# Phase 1: Parsing & Structure Foundation - Research

**Researched:** 2026-07-22
**Domain:** Federal RFP document parsing (PDF/DOCX), UCF structure detection, document-map schema design, Python project scaffolding
**Confidence:** HIGH (library APIs, form signatures, UCF structure verified against official sources) / MEDIUM (heuristic thresholds — deliberately tunable against corpus)

## Summary

Phase 1 builds a pure Python library + CLI that turns a directory of federal RFP files (PDF + DOCX) into a versioned, Pydantic-schema'd document map: per-file identity, section hierarchy with page ranges, per-page quality status, amendment labels, and package classification. The stack is locked (pdfplumber 0.11.10, python-docx 1.2.0, Pydantic 2.13.x, uv/ruff/pytest) and all versions were re-verified on PyPI today. All six packages this phase installs passed slopcheck legitimacy audit.

The two genuinely hard problems are (1) UCF section-boundary detection that doesn't get fooled by table-of-contents pages (the SF33's Block 9 literally lists Sections A–M with page numbers on page 1) and degrades honestly on non-UCF packages, and (2) representing DOCX locations in a document map whose downstream consumer (Phase 2 provenance envelopes) expects page numbers — DOCX has no fixed pages, so the schema must carry a locator union (page spans for PDF, block-ordinal spans for DOCX). Both are solvable with deterministic heuristics; no LLM calls in this phase. Form-page signatures are strong anchors: SF33 ("SOLICITATION, OFFER AND AWARD"), SF1449 ("SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES"), and SF30 ("AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT") all have verified, greppable first-page titles — with one verified nuance: FAR 12.603 combined synopsis/solicitations use *no form at all* (the notice text is the solicitation), so non-UCF detection needs text markers, not just form detection.

Quality gates are simple per-page metrics (char count, alpha/printable ratios, `(cid:N)` artifact counts, image-without-text detection) with thresholds explicitly left tunable against the 3-package corpus per CONTEXT D-decisions. The environment audit found one blocking gap: **uv is not installed** on this machine (winget is available to install it); Python 3.14.6, git, gh (authenticated), and slopcheck are present. The repo is not yet a git repository — D-07 (public GitHub repo from day 1) means `git init` + GitHub repo creation is a Phase 1 task.

**Primary recommendation:** Build parsing as per-file `f(path) → ParsedFile` functions, sectioning as `f(ParsedFile) → SectionTree`, classification as `f(files, trees) → PackageMap`, all pure; anchor section detection on form-page signatures + heading regexes + role-title matching with "heading must not be a TOC line" disambiguation; emit one versioned `document_map.json` per run plus a human-readable tree to stdout.

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

User delegated all gray areas to Claude's judgment ("take the wheel"). Decisions below were made against the research corpus (.planning/research/) and are locked unless contradicted by evidence during execution.

#### Test Corpus
- **D-01:** Validate against a 3-package minimum real-world corpus, manually downloaded from the SAM.gov website (no API key needed for browsing/downloading attachments):
  1. **Clean full-UCF multi-file services solicitation** — base + at least one SF30 amendment + attachments, moderate size (~100–300 pages total). This is the primary package and should be chosen deliberately: the same package becomes Phase 2's hand-shredded golden set.
  2. **Hostile package** — contains scanned pages (a scanned/rescanned SF30 is the ideal specimen) to exercise quality gates.
  3. **Non-UCF package** — FAR Part 12 combined synopsis/solicitation (SF 1449) to prove honest degradation ("non-standard structure" classification, not garbage sections).
- **D-02:** Corpus PDFs/DOCX are **gitignored** (large binaries in a public repo). Commit a `tests/corpus/MANIFEST.md` documenting each package: SAM.gov notice link, solicitation number, file list with checksums, and why it was selected. Small excerpt fixtures (single pages/sections) may be committed for unit tests.

#### Scanned-Page Handling
- **D-03:** **Flag-and-surface only in Phase 1 — no OCR.** Quality gates detect near-empty text layers (scanned-page indicator), gibberish ratio, and repeated header/footer noise (strip headers/footers before downstream use). Per-page quality status is recorded in the document map; low-quality pages are excluded from usable text with an explicit surfaced note (e.g., "pages 45–52: scanned image, no text layer"), never passed through silently.
- **D-04:** Docling (MIT) remains the pre-identified OCR/table fallback, adopted **only on eval evidence** in a later phase — not speculatively.

#### CLI Output Format
- **D-05:** The CLI harness emits **both** artifacts per run:
  - **Canonical JSON document map** — Pydantic-schema'd, versioned; this is the pipeline contract Phase 2 consumes. Written to an artifacts directory.
  - **Human-readable section tree report** to stdout — files → package classification (full UCF / partial / non-UCF / unknown) → section hierarchy with page ranges → per-page quality flags → amendment labels. This is how the phase success criteria get eyeballed.
- **D-06:** CLI shape: point it at a package directory, get artifacts out (e.g., `parse <package-dir> --out <artifacts-dir>`). Exact command naming and arg design is Claude's discretion.

#### Repo & Scaffolding
- **D-07:** **Public GitHub repo from day 1.** Clean, disciplined commit history is itself showcase evidence (PROJECT.md lists a clean public repo as a core goal). Secrets via env vars only; corpus files gitignored per D-02.
- **D-08:** Tooling from the start: **uv** (env/lockfile), **ruff** (lint+format), **pytest**. GitHub Actions CI running lint + tests from Phase 1 onward.
- **D-09:** Cost-per-run instrumentation **scaffolding** lands in Phase 1 (counters/plumbing in the pipeline library), even though Phase 1 itself makes zero LLM calls — research flags per-run cost as needed early for demo-mode decisions.

### Claude's Discretion
- Section-detection heuristics and pdfplumber tuning (regexes vs. layout signals for "SECTION L" boundaries, SF30 form detection approach)
- JSON document-map schema details (must carry: per-file identity, section hierarchy with page ranges, per-page quality status, amendment labels, package classification)
- Exact quality-gate thresholds (chars/page, gibberish ratio) — tune against the corpus
- Repo layout within the locked constraint that `pipeline/` is a pure library (no HTTP, no queue imports)
- CLI command naming/UX

### Deferred Ideas (OUT OF SCOPE)
- **OCR fallback (Docling)** — deferred until eval evidence shows pdfplumber + Claude native PDF insufficient (likely evaluated Phase 2+). Phase 1 only flags scanned pages.
- **Header/footer-aware table extraction improvements** — only if corpus evidence demands; Docling is the designated path.

### Specific Ideas (from CONTEXT.md)
- **User action item at phase start:** Request the SAM.gov API key (requires SAM.gov account via login.gov; key from Account Details page). ~10 business day issuance; Phase 5 depends on it. This is a Ross-personal task the executor should surface, not perform.
- Corpus packages should be genuinely hostile — the research warns that testing on clean born-digital PDFs confirms false confidence. The scanned-SF30 and non-UCF packages are deliberate stress tests, not afterthoughts.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PARS-01 | System parses hostile real-world federal PDFs (tables, multi-column, SF forms) into text with a structural document map (section hierarchy + page numbers) | pdfplumber API (extract_text/extract_words/chars with positions, dedupe_chars, page.close memory management); python-docx iter_inner_content for document-order parsing; per-page quality gates + header/footer stripping design; DocumentMap Pydantic schema with PageSpan/BlockSpan locator union |
| PARS-02 | System detects UCF section boundaries (L, M, C/SOW/PWS, H, etc.) and degrades honestly when a package doesn't follow clean UCF structure (e.g., FAR Part 12 combined synopsis) | Verified UCF Part/Section structure (FAR 15.204-1); heading regex + role-title matching + form-page signatures (SF33/SF1449/SF30, all title-text verified); FAR 12.603 combined-synopsis text markers; PackageClassification enum (FULL_UCF/PARTIAL_UCF/NON_UCF_COMMERCIAL/UNKNOWN) with warnings, never silent mis-sectioning |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Stack locked:** Python 3.12+, pdfplumber 0.11.x (MIT), python-docx 1.2.0, Pydantic 2.13.x. **No PyMuPDF/fitz (AGPL)**, no LangChain/LlamaIndex, no cloud OCR, no .doc (legacy Word) parsing — reject .doc with a clear message.
- **Pure pipeline library:** `pipeline/` has no HTTP, no queue imports; every stage is `f(artifact) → artifact`. Single most important architectural boundary.
- **No whole-package LLM calls ever** (and no LLM calls at all in Phase 1).
- **GSD workflow enforcement:** file changes go through GSD commands (`/gsd-execute-phase` for planned phase work).
- **Dev tools:** uv (Railway's Railpack detects `uv.lock`), ruff (replaces black/flake8/isort), pytest with golden-file tests as core quality gate.
- Section-level chunking downstream (Phase 2) consumes this phase's document map — schema is a contract.

## Architectural Responsibility Map

Tiers here are pipeline stages within the pure library (no web tiers exist in this phase):

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF text/word/position extraction | `parsing` (per-file) | — | pdfplumber owns raw extraction; one file in, one ParsedFile out |
| DOCX paragraph/table extraction | `parsing` (per-file) | — | python-docx `iter_inner_content()` gives document-order blocks |
| Per-page quality gates + header/footer stripping | `quality` | `parsing` (raw metrics captured at parse time) | Quality is computed from parse output; stripping must happen before sectioning consumes text |
| UCF section-boundary detection | `sectioning` | `quality` (skips scanned pages) | Operates on cleaned per-page/per-block text + positions |
| Form-page recognition (SF33/SF1449/SF30) | `classify` | `sectioning` (form pages anchor section A) | Package- and file-level identity decisions, not text structure |
| Amendment (SF30) labeling | `classify` | — | File-role decision from first-page signature + filename fallback |
| Package classification (UCF/partial/non-UCF/unknown) | `classify` | — | Aggregates per-file section trees + form signals |
| Document map assembly + JSON serialization | `models` (Pydantic) | CLI (writes artifact) | Schema is the Phase 2 contract; library builds it, CLI persists it |
| Human-readable tree report | CLI | — | Presentation only; never a data source |
| Cost/metrics instrumentation scaffolding | `metrics` (library) | CLI (prints summary) | D-09: counters/plumbing now, LLM token fields zero until Phase 2 |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pdfplumber | 0.11.10 | PDF text/word/char extraction with positions; table basics | Locked by project research; MIT; built on pdfminer.six. Version confirmed current on PyPI today `[VERIFIED: PyPI via pip index, 2026-07-22]`, matches latest GitHub release (Jun 2026) `[CITED: github.com/jsvine/pdfplumber]` |
| python-docx | 1.2.0 | DOCX paragraphs/tables/headings in document order | Locked; `iter_inner_content() → Iterator[Paragraph | Table]` gives interleaved paragraphs+tables `[CITED: python-docx.readthedocs.io/en/latest/api/document.html]` `[VERIFIED: PyPI]` |
| Pydantic | 2.13.4 | DocumentMap schema, JSON serialization, validation | Locked; v2 API (`model_dump_json`, `model_validate_json`) `[VERIFIED: PyPI]` |

### Supporting (dev)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | latest (0.11.x line) | Env/lockfile/package management | All installs; `uv.lock` committed; Railpack detects it later `[CITED: docs.astral.sh/uv]` |
| ruff | 0.15.22 | Lint + format | `ruff check` + `ruff format` in CI `[VERIFIED: PyPI]` |
| pytest | 9.1.1 | Tests (unit fixtures + corpus integration) | All tests `[VERIFIED: PyPI]` |
| pytest-cov | 7.1.0 | Coverage reporting | Optional in CI; slopcheck notes no linked source repo on PyPI metadata (established package; see audit) `[VERIFIED: PyPI]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse (stdlib) for CLI | typer/click | typer/click are nicer DX but add dependencies not in the locked stack; Phase 1 CLI is one subcommand + two args — argparse is sufficient and keeps the dependency audit surface minimal. **Use argparse.** |
| Per-page text via `extract_text()` | `extract_text(layout=True)` everywhere | `layout=True` mimics visual layout — useful for SF form pages (label/value blocks) but slower and inserts artificial whitespace; use default mode for body text, layout mode only when inspecting form pages `[CITED: github.com/jsvine/pdfplumber]` |
| pdfplumber | Docling | Deferred by D-04 — eval evidence only. Do not add in Phase 1. |

**Installation:**
```bash
uv init --package rfp-analyzer   # or uv init --lib; creates src layout + pyproject
uv add pdfplumber python-docx pydantic
uv add --dev pytest pytest-cov ruff
```

**Version verification (performed 2026-07-22):** `python -m pip index versions <pkg>` confirmed pdfplumber 0.11.10, python-docx 1.2.0, pydantic 2.13.4, pytest 9.1.1, ruff 0.15.22, pytest-cov 7.1.0 as latest on PyPI.

## Package Legitimacy Audit

slopcheck run 2026-07-22 against PyPI (`slopcheck install pdfplumber python-docx pydantic pytest ruff pytest-cov`): **6/6 [OK]**.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pdfplumber | PyPI | ~10 yrs (0.0.0 era → 0.11.10) | millions/mo (approx) | github.com/jsvine/pdfplumber | [OK] | Approved |
| python-docx | PyPI | ~12 yrs | millions/mo (approx) | github.com/python-openxml/python-docx | [OK] — note: "name starts with 'python-'… package is established" | Approved |
| pydantic | PyPI | ~9 yrs | top-10 PyPI package | github.com/pydantic/pydantic | [OK] | Approved |
| pytest | PyPI | ~15 yrs | top-tier | github.com/pytest-dev/pytest | [OK] | Approved |
| ruff | PyPI | ~3.5 yrs | very high | github.com/astral-sh/ruff | [OK] | Approved |
| pytest-cov | PyPI | ~10 yrs | very high | github.com/pytest-dev/pytest-cov | [OK] — note: "No source repository linked" in PyPI metadata (repo exists; metadata gap) | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
*(Download counts are approximate from training knowledge — all packages are ecosystem-dominant; ages/repos consistent with registry history returned by `pip index versions`.)*

uv itself is installed via standalone installer or winget (`winget install astral-sh.uv`), not pip — see Environment Availability.

## Architecture Patterns

### System Architecture Diagram

```
package directory (PDFs + DOCX, manually downloaded corpus)
        │
        ▼
┌──────────────────────── CLI (rfp-analyzer parse <dir> --out <artifacts>) ────────────────────────┐
│                                                                                                  │
│  discover files ──► for each file:                                                               │
│                        ┌───────────────────────────────────────────────┐                         │
│    .pdf ──────────────►│ parsing.pdf: pdfplumber                       │                         │
│                        │  pages → text, words+positions, char counts,  │                         │
│                        │  image presence; page.close() after each      │                         │
│    .docx ─────────────►│ parsing.docx: python-docx                     │──► ParsedFile           │
│                        │  iter_inner_content → ordered blocks          │    (per-file artifact)  │
│    .doc / other ──────►│ rejected with explicit per-file error status  │                         │
│                        └───────────────────────────────────────────────┘                         │
│                                          │                                                       │
│                                          ▼                                                       │
│                        ┌───────────────────────────────────────────────┐                         │
│                        │ quality: per-page/per-file gates              │                         │
│                        │  scanned / low-text / gibberish / ok          │                         │
│                        │  header-footer detection → stripped text      │                         │
│                        └───────────────────────────────────────────────┘                         │
│                                          │ cleaned text + quality flags                          │
│                                          ▼                                                       │
│                        ┌───────────────────────────────────────────────┐                         │
│                        │ sectioning: UCF boundary detection            │                         │
│                        │  form-page anchors + heading regexes +        │                         │
│                        │  role-title match; TOC disambiguation         │──► SectionTree per file │
│                        └───────────────────────────────────────────────┘                         │
│                                          │                                                       │
│                                          ▼                                                       │
│                        ┌───────────────────────────────────────────────┐                         │
│                        │ classify: file roles + package classification │                         │
│                        │  SF30 → amendment; SF33/SF1449 → base;        │                         │
│                        │  combined-synopsis markers → NON_UCF;         │                         │
│                        │  aggregate → FULL/PARTIAL/NON_UCF/UNKNOWN     │                         │
│                        └───────────────────────────────────────────────┘                         │
│                                          │                                                       │
│                     ┌────────────────────┴────────────────────┐                                  │
│                     ▼                                         ▼                                  │
│        document_map.json (Pydantic,                stdout section-tree report                    │
│        versioned — Phase 2 contract)               (human eyeball of success criteria)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Trace: a package dir enters at the top; each file is parsed independently (per-file failures isolated), quality-gated, sectioned, then package-level classification aggregates all files; two outputs exit at the bottom.

### Recommended Project Structure

Src layout; the pure-library boundary is the `pipeline` subpackage (locked constraint). Future phases add `app/`, `worker/`, `web/` beside `src/` without touching it.

```
rfp-analyzer/
├── pyproject.toml            # uv-managed; [project.scripts] rfp-analyzer entry point
├── uv.lock                   # committed
├── .gitignore                # tests/corpus/* excluded (MANIFEST.md kept)
├── .github/workflows/ci.yml  # lint + format-check + tests
├── src/
│   └── rfp_analyzer/
│       ├── pipeline/         # PURE LIBRARY — no HTTP, no queue, no CLI imports
│       │   ├── models.py     # Pydantic: DocumentMap, ParsedFile, SectionNode, PageInfo, locators
│       │   ├── parsing/      # pdf.py (pdfplumber), docx.py (python-docx), discover.py
│       │   ├── quality/      # page gates, gibberish metrics, header/footer stripping
│       │   ├── sectioning/   # UCF heading detection, section tree builder
│       │   ├── classify/     # form signatures (SF30/SF33/SF1449), roles, package classification
│       │   └── metrics.py    # RunMetrics scaffolding (D-09): stage timings, counters, token fields (0)
│       └── cli.py            # argparse; parse <package-dir> --out <artifacts-dir>; report rendering
├── tests/
│   ├── unit/                 # committed excerpt fixtures (single pages/sections)
│   ├── integration/          # corpus-driven; skipped if corpus absent (CI has no corpus)
│   ├── fixtures/             # small committed PDF/DOCX excerpts (D-02 allows)
│   └── corpus/               # GITIGNORED real packages + committed MANIFEST.md
└── README.md
```

### Pattern 1: Per-file parse with isolated failure

**What:** Each file parses independently; a malformed PDF produces a `ParsedFile` with `parse_status: failed` + error message, never a crashed package run.
**When to use:** Always — hostile corpus files are the norm, and pdfminer.six raises on malformed PDFs.
**Example:**
```python
# Source: pdfplumber README (github.com/jsvine/pdfplumber) — open/pages/close API
import pdfplumber

def parse_pdf(path: Path) -> ParsedFile:
    pages: list[PageInfo] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                pages.append(PageInfo(
                    page_number=page.page_number,        # 1-indexed
                    text=text,
                    char_count=len(page.chars),
                    has_images=bool(page.images),        # [ASSUMED: page.images attr — verify at impl]
                ))
                page.close()                             # flush cache — critical on 100–300 page PDFs
    except Exception as exc:                             # pdfminer raises varied exception types
        return ParsedFile(path=path, parse_status="failed", error=str(exc), pages=[])
    return ParsedFile(path=path, parse_status="ok", pages=pages)
```

### Pattern 2: DOCX document-order block extraction with ordinal locators

**What:** DOCX has no fixed pages. Iterate `document.iter_inner_content()` (paragraphs and tables interleaved in document order), assign each block a 0-based ordinal; DOCX locations in the document map are **block spans**, not page spans. Heading detection: `paragraph.style.name` (`"Heading 1"`, `"Heading 2"`…) first, falling back to text heuristics (ALL-CAPS short lines, `L.4.2`-style numbering) because federal DOCX files frequently use direct formatting instead of styles.
**When to use:** All DOCX parsing.
**Example:**
```python
# Source: python-docx.readthedocs.io/en/latest/api/document.html — iter_inner_content, style.name
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

def parse_docx(path: Path) -> ParsedFile:
    doc = Document(str(path))
    blocks: list[BlockInfo] = []
    for i, item in enumerate(doc.iter_inner_content()):   # Iterator[Paragraph | Table], doc order
        if isinstance(item, Paragraph):
            blocks.append(BlockInfo(ordinal=i, kind="paragraph",
                                    text=item.text, style=item.style.name))
        elif isinstance(item, Table):
            cells = [[c.text for c in row.cells] for row in item.rows]
            blocks.append(BlockInfo(ordinal=i, kind="table", table=cells))
    return ParsedFile(path=path, parse_status="ok", blocks=blocks)
```
`RenderedPageBreak` objects exist in python-docx but depend on the producing application having written `w:lastRenderedPageBreak` markers — unreliable across producers. **Do not synthesize page numbers for DOCX**; use block ordinals `[CITED: python-docx docs — RenderedPageBreak listed in API; reliability caveat ASSUMED]`.

### Pattern 3: Anchored section detection with TOC disambiguation

**What:** Three signal classes, in priority order:
1. **Form-page anchors:** page 1 of a file matching SF33/SF1449/SF30 title text pins file identity and (for SF33) marks Section A's start.
2. **Heading regexes** on line starts of cleaned page text: `SECTION L`, `PART I—THE SCHEDULE`, and paragraph numbering `L.1`, `L.4.2`.
3. **Role titles:** "INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS" (→ L role), "EVALUATION FACTORS FOR AWARD" (→ M), "STATEMENT OF WORK" / "PERFORMANCE WORK STATEMENT" (→ C/SOW/PWS role), "SPECIAL CONTRACT REQUIREMENTS" (→ H) — so a package whose instructions live in an attachment titled "Proposal Submission Instructions" still gets role-tagged `[CITED: acquisition.gov/far/15.204-1 for official section titles]`.

**TOC disambiguation (critical):** SF33 Block 9 and standalone TOC pages list *all* section titles on one page. A heading match is a section start only if it is not a TOC line. Practical discriminators: multiple distinct section headings matching on the same page → that page is a TOC, record it, don't split there; a TOC line typically has a trailing page number and dot leaders; a real section start is typically the first matching line at/near the top of its page and is followed by body text of that section. Prefer "a section's start page = last page where the heading appears as a leading line AND at least one subsequent heading appears later" — validate against corpus `[ASSUMED heuristic — tune on corpus per user constraint]`.

**Regex sketches (case-insensitive, whitespace/dash-tolerant):**
```python
SECTION_HEADING = re.compile(
    r"^\s*SECTION\s+([A-M])\b\s*[—–\-:.]?\s*(.{0,120})$", re.IGNORECASE | re.MULTILINE)
PART_HEADING = re.compile(
    r"^\s*PART\s+(I{1,3}|IV)\b\s*[—–\-:.]?\s*(.{0,80})$", re.IGNORECASE | re.MULTILINE)
PARA_NUMBER = re.compile(          # L.1, L.4.2, M.3.1.2 — leading-position paragraph IDs
    r"^\s*([A-M])\.(\d+)(?:\.(\d+))*\b", re.MULTILINE)
```
Normalize before matching: collapse runs of whitespace, unify `–`/`—`/`-`, uppercase. `[ASSUMED: exact regex forms — conventions verified against practitioner descriptions of UCF documents; tune on corpus]`

### Pattern 4: Form-page signatures (verified title text)

| Form | First-page title text (grep target) | Meaning | Source |
|------|-------------------------------------|---------|--------|
| SF33 | `SOLICITATION, OFFER AND AWARD` | UCF base solicitation cover (Section A); Block 9 contains RFP table of contents | [CITED: energy.gov SF-33 specimens; fedsubk.com solicitation anatomy] |
| SF1449 | `SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES` (older revisions: `…FOR COMMERCIAL ITEMS`) | FAR Part 12 commercial solicitation → NON_UCF_COMMERCIAL | [CITED: irs.gov/pub/irs-procure/sf1449.rtf; dla.mil SF1449 guide] |
| SF30 | `AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT` | Amendment file; Block 2 "AMENDMENT/MODIFICATION NO." carries the amendment number; Item 14 = description | [CITED: gsa.gov/system/files/SF30-16c.pdf; acq.osd.mil SF-30 reference] |
| *(no form)* | Text contains `combined synopsis/solicitation` and/or `in accordance with the format in Subpart 12.6` / `FAR 12.603` | FAR 12.603 streamlined solicitation — the notice text IS the solicitation; **no SF1449 is used in this case** → NON_UCF_COMMERCIAL | [CITED: acquisition.gov/far/12.603] |

Match tolerantly (case-insensitive, flexible whitespace/slashes; titles may be split across extracted words on form layouts — match against whitespace-collapsed page-1 text, and also try `extract_text(layout=True)` on page 1 if the default-mode match fails).

**SF30 detection ladder:** (1) page-1 title text match → `amendment`, extract amendment number near Block 2 label `AMENDMENT/MODIFICATION NO`; (2) if page 1 has no text layer (scanned SF30 — the D-01 hostile specimen), fall back to filename patterns (`sf30`, `amend`, `amdt`, `mod`, `a0001`, `0001`-style suffixes) and label `amendment (unverified — scanned, matched by filename)`; (3) neither → not an amendment. Never let a scanned SF30 pass as a silent ordinary attachment: quality gate already flags its pages, and classification surfaces the filename-only match honestly.

### Pattern 5: Per-page quality gates + header/footer stripping

**Per-page metrics** (computed in `quality`, stored on `PageInfo`): `char_count`, `word_count`, `alpha_ratio` (alphabetic chars / non-space chars), `printable_ratio`, `cid_count` (occurrences of `(cid:` — pdfminer.six emits `(cid:NNN)` for glyphs with no Unicode mapping, a classic garbage-text signal `[ASSUMED: well-known pdfminer behavior]`), `replacement_char_count` (U+FFFD), `has_images`.

**Status classification (initial thresholds — all tunable constants, corpus-calibrated per user constraint `[ASSUMED]`):**
- `SCANNED`: `char_count < 20` and `has_images` — image-only page
- `EMPTY`: `char_count < 20` and no images
- `LOW_TEXT`: `char_count < 150` on a page with images (partial scan / stamped page)
- `GIBBERISH`: `alpha_ratio < 0.5` or `cid_count / max(char_count,1) > 0.02` or `replacement_char_count > 5`
- `OK`: otherwise

Pages not `OK` are excluded from sectioning/usable text and surfaced in the report as ranges ("pages 45–52: scanned image, no text layer") — D-03.

**Header/footer stripping (per file):** take the first and last 1–2 physical lines of each page (or words within top/bottom ~8% of `page.height` via `extract_words` positions); normalize (strip digits so `Page 3 of 120` folds to one key, collapse whitespace, uppercase); count frequency across the file's OK pages; any normalized line appearing on ≥ ~40% of pages is a running header/footer — remove from cleaned text, record the stripped patterns on the file entry. `[ASSUMED: standard cross-page-frequency technique; threshold corpus-tunable]`

### Pattern 6: Document map schema (the Phase 2 contract)

Prescriptive model set (Pydantic 2, `schema_version: "1.0"` at the root):

```python
# Pydantic 2.13 — models sketch; names are prescriptive
from typing import Literal
from pydantic import BaseModel, Field

class PageSpan(BaseModel):
    kind: Literal["pages"] = "pages"
    page_start: int   # 1-indexed, inclusive
    page_end: int

class BlockSpan(BaseModel):
    kind: Literal["blocks"] = "blocks"
    block_start: int  # 0-indexed ordinal from iter_inner_content, inclusive
    block_end: int

Locator = PageSpan | BlockSpan   # discriminated by "kind"

class PageInfo(BaseModel):
    page_number: int
    quality: Literal["ok", "scanned", "empty", "low_text", "gibberish"]
    char_count: int
    metrics: dict[str, float]          # alpha_ratio, cid_count, ...
    text: str                          # cleaned (headers/footers stripped); "" if not ok

class SectionNode(BaseModel):
    label: str                         # "L", "L.4", "L.4.2", or "SOW"
    title: str                         # heading text as found
    role: Literal["instructions", "evaluation", "sow_pws", "special_requirements",
                  "clauses", "attachments_list", "other"] | None
    locator: Locator
    detection: Literal["form_anchor", "heading", "role_title", "paragraph_numbering"]
    children: list["SectionNode"] = Field(default_factory=list)

class ParsedFile(BaseModel):
    file_id: str                       # stable slug: sha256[:12] + sanitized name
    filename: str
    sha256: str
    file_type: Literal["pdf", "docx"]
    parse_status: Literal["ok", "failed", "rejected"]   # rejected = .doc etc.
    error: str | None = None
    doc_role: Literal["base_solicitation", "amendment", "attachment", "unknown"]
    amendment_number: str | None = None                 # from SF30 Block 2
    amendment_evidence: Literal["form_text", "filename", None] = None
    page_count: int | None             # None for DOCX
    pages: list[PageInfo] = Field(default_factory=list)      # PDF only
    blocks: list[dict] = Field(default_factory=list)         # DOCX: ordinal/kind/text/style/table
    stripped_headers: list[str] = Field(default_factory=list)
    sections: list[SectionNode] = Field(default_factory=list)

class DocumentMap(BaseModel):
    schema_version: str = "1.0"
    package_name: str                  # directory name
    classification: Literal["full_ucf", "partial_ucf", "non_ucf_commercial", "unknown"]
    classification_evidence: list[str]     # human-readable reasons
    warnings: list[str]                    # honest-degradation surface
    files: list[ParsedFile]
    metrics: "RunMetrics"                  # D-09 scaffolding
```

**Design notes for the planner:**
- The Locator union is the key generalization: ARCHITECTURE.md's provenance envelope (`{doc_id, section_path, page_start, page_end}`) assumed pages; Phase 2 chunking must accept `PageSpan | BlockSpan` (or nullable pages for DOCX). Locking this in the Phase 1 schema prevents a Phase 2 contract break.
- Cleaned page/block **text lives inside the map** (single artifact ≈ 1–2 MB JSON for a 300-page package — acceptable, keeps the Phase 2 contract to one file per run). `[ASSUMED: size estimate]`
- `classification` rules: `full_ucf` when L, M, and C (or SOW/PWS role) all detected with sane ordering; `partial_ucf` when some but not all; `non_ucf_commercial` on SF1449/combined-synopsis signals; `unknown` otherwise — with `warnings` always explaining, e.g., "No Section M heading found; package classified partial_ucf. Results downstream may be incomplete."

### Pattern 7: Scaffolding + CI (D-07/D-08)

- `uv init --package` → src layout, `pyproject.toml` with `[project.scripts] rfp-analyzer = "rfp_analyzer.cli:main"`, `requires-python = ">=3.12"`.
- ruff config in `pyproject.toml`: `[tool.ruff] line-length = 100`, `[tool.ruff.lint] select = ["E","F","I","UP","B","SIM"]` `[ASSUMED: sensible default rule set]`.
- `.gitignore` corpus pattern (keeps MANIFEST.md, D-02):
```gitignore
tests/corpus/*
!tests/corpus/MANIFEST.md
```
- GitHub Actions (verified against uv official docs `[CITED: docs.astral.sh/uv/guides/integration/github/]`):
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v8          # official action; docs pin exact SHA/version
        with:
          python-version: "3.12"
      - run: uv sync --locked --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest tests/unit         # corpus tests auto-skip when corpus absent
```
- Corpus-dependent integration tests use `pytest.mark.skipif(not CORPUS_DIR.exists(), ...)` so CI (no corpus binaries) stays green while local runs exercise real packages.
- Metrics scaffolding (D-09): `RunMetrics` model with `stage_timings: dict[str, float]`, `files_parsed`, `pages_parsed`, `pages_flagged`, and zeroed LLM fields (`llm_calls: 0`, `input_tokens: 0`, `output_tokens: 0`, `estimated_cost_usd: 0.0`) so Phase 2 fills them without schema change.

### Anti-Patterns to Avoid

- **Treating TOC lines as section starts** — the SF33 Block 9 table of contents is on page 1 of nearly every UCF solicitation; naive first-match regex splits the whole document at page 1.
- **Synthesizing page numbers for DOCX** — fabricated provenance is exactly the Pitfall-2 class failure this project exists to prevent; use block ordinals.
- **Silent fallthrough on non-UCF** — never emit an empty/garbage section tree; emit `non_ucf_commercial`/`unknown` + warnings (success criterion 2).
- **Whole-file `pdf.pages` materialization without `page.close()`** — cached char/layout objects on 300-page PDFs balloon memory `[CITED: pdfplumber README memory note]`.
- **Hard-coding literal section letters as the only signal** — role-title matching is what catches "Proposal Submission Instructions.pdf" attachments (PITFALLS.md Pitfall 3).
- **`layout=True` for all extraction** — slower and injects artificial spacing; reserve for form-page inspection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text + positions | Custom pdfminer.six wiring | pdfplumber page API | Tolerances, word grouping, layout mode, dedupe already solved |
| Fake-bold duplicate glyphs | Custom char dedupe | `page.dedupe_chars(tolerance=1)` | Federal PDFs fake bold by double-printing; built-in handles it `[CITED: pdfplumber README]` |
| DOCX XML | lxml over document.xml | python-docx `iter_inner_content()` | Document-order paragraph+table iteration is exactly the need |
| Schema/serialization/validation | Hand-written JSON (de)serializers | Pydantic 2 models + `model_dump_json` | Versioned contract, validation on load in Phase 2 |
| CLI parsing | Custom sys.argv handling | stdlib argparse | One subcommand; zero extra deps |
| File hashing | Custom | `hashlib.sha256` streaming | MANIFEST.md checksums (D-02) |
| OCR | Anything | Nothing in Phase 1 (flag only; Docling deferred by D-04) | Locked decision |

**Key insight:** every deterministic sub-problem here (extraction, ordering, validation) has a mature MIT-licensed solution in the locked stack; Phase 1's genuinely novel code is only the *heuristics* (section anchors, quality thresholds, classification rules) — which is exactly the code the corpus exists to tune.

## Common Pitfalls

### Pitfall 1: TOC page mis-detected as all section starts
**What goes wrong:** Every UCF section "begins" on page 1 because the SF33 Block 9 / TOC page lists them all.
**Why it happens:** First-occurrence regex matching with no page-context check.
**How to avoid:** TOC disambiguation (Pattern 3): many-headings-on-one-page ⇒ TOC; require section starts to be leading lines with following body content; prefer later occurrences.
**Warning signs:** All sections report `page_start=1`; section page ranges overlap wildly.

### Pitfall 2: pdfminer exceptions kill the package run
**What goes wrong:** One malformed/corrupt PDF (common in old SAM.gov attachments) raises deep inside pdfminer.six and the CLI crashes with a stack trace.
**Why it happens:** No per-file isolation.
**How to avoid:** try/except per file → `parse_status: failed` entry in the map; run continues; report lists the failure.
**Warning signs:** CLI exit before the report; missing files in output.

### Pitfall 3: Memory blowup on 100–300 page PDFs
**What goes wrong:** RSS grows to GBs during parse.
**Why it happens:** pdfplumber caches per-page objects (chars, layout) for the life of the page object.
**How to avoid:** `page.close()` after consuming each page; don't retain `Page` objects — retain your own `PageInfo` `[CITED: pdfplumber README]`.
**Warning signs:** Parse time/memory superlinear in page count.

### Pitfall 4: DOCX heading styles absent in the wild
**What goes wrong:** `style.name == "Heading 1"` never matches; DOCX section tree comes back empty.
**Why it happens:** Federal offices often apply bold/caps directly instead of Word styles.
**How to avoid:** Style-name detection first, then the same text-regex/role-title heuristics used for PDFs applied to paragraph text.
**Warning signs:** A DOCX with obvious headings yields zero SectionNodes.

### Pitfall 5: Scanned SF30 invisible to form detection
**What goes wrong:** The hostile-corpus scanned amendment has no text layer, so the title match fails and the file is labeled a plain attachment.
**Why it happens:** Form detection depends on extractable text.
**How to avoid:** Detection ladder (Pattern 4): filename fallback with `amendment_evidence: "filename"` and an explicit unverified label; quality gate independently flags the pages as scanned.
**Warning signs:** A package known to contain an amendment reports zero amendments (success criterion 4 fails).

### Pitfall 6: Header/footer text contaminating section text
**What goes wrong:** "W912DY-26-R-0012 — Page 47" appears inside Section L text; Phase 2 extracts it as requirement noise.
**Why it happens:** No cross-page frequency stripping before text is stored.
**How to avoid:** Pattern 5 stripping *before* text lands in `PageInfo.text`; record stripped patterns for auditability.
**Warning signs:** Same line repeats across many pages' stored text.

### Pitfall 7: Calibrating thresholds on the clean package only
**What goes wrong:** Quality gates pass everything because thresholds were tuned where nothing is hostile; scanned pages sail through as `OK` with 30 chars of stamp text.
**Why it happens:** Corpus laziness — CONTEXT explicitly warns against it.
**How to avoid:** Tune on the hostile package; assert in integration tests that known-scanned pages are flagged.
**Warning signs:** Hostile-package run reports zero flagged pages.

## Code Examples

Core patterns are inline above (Patterns 1–6). Additional verified snippets:

### pdfplumber words with positions (for header/footer bands and layout signals)
```python
# Source: github.com/jsvine/pdfplumber README — extract_words returns dicts with x0/x1/top/bottom/doctop
words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
top_band = [w for w in words if w["top"] < page.height * 0.08]
bottom_band = [w for w in words if w["bottom"] > page.height * 0.92]
```

### Table extraction basics (available if needed for form pages; not a Phase 1 deliverable)
```python
# Source: pdfplumber README — extract_tables(table_settings)
tables = page.extract_tables(table_settings={
    "vertical_strategy": "lines", "horizontal_strategy": "lines"})
# Returns list of tables → rows → cells (str | None)
```

### Stable file identity
```python
import hashlib
def file_identity(path: Path) -> tuple[str, str]:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return digest, f"{digest[:12]}-{re.sub(r'[^a-z0-9]+', '-', path.stem.lower())[:40]}"
```

## Corpus Sourcing (SAM.gov, manual — D-01)

- **No account needed** to search and download attachments at `sam.gov` → Contract Opportunities search `[CITED: sam.gov/opportunities; multiple practitioner guides confirm public attachment download]`. (An account IS needed later for the API key — that's the separate Ross action item.)
- **Clean UCF package:** filter Notice Type = "Solicitation"; DoD services solicitations (Army/Navy/Air Force, NAICS 5415xx/561xxx) are the most reliably full-UCF with SF33 cover pages; pick one with a base PDF + ≥1 SF30 amendment + attachments totaling ~100–300 pages. Check "active" first; archived notices also keep attachments downloadable `[ASSUMED: archived-attachment availability — verify while browsing]`.
- **Non-UCF package:** filter Notice Type = **"Combined Synopsis/Solicitation"** — this filter directly yields FAR 12.603 packages (the exact honest-degradation specimen) `[CITED: acquisition.gov/far/12.603 for what these are]`. An SF1449-based Part 12 solicitation is an acceptable substitute/addition.
- **Hostile/scanned specimen:** amendments on older or smaller-agency notices are frequently signed-and-rescanned SF30s; open candidate PDFs and check for a missing text layer (select-all copies nothing). If the primary package's amendment is born-digital, source the scanned SF30 from a different notice.
- **MANIFEST.md per package:** SAM.gov notice URL, solicitation number, file list with sha256, page counts, and selection rationale (D-02).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyPDF2/pypdf naive text | pdfplumber positions/layout API | ongoing standard | Positions enable header/footer bands + form anchoring |
| python-docx `document.paragraphs` + `document.tables` separately (order lost between them) | `iter_inner_content()` interleaved iteration | python-docx ≥1.1 | Correct document-order block ordinals for DOCX locators |
| Pydantic v1 (`.dict()`, `.parse_raw`) | Pydantic v2 (`model_dump_json`, `model_validate_json`) | 2023; v1 in maintenance | Use v2 idioms only (locked stack pins 2.13.x) |
| pip + venv + black + flake8 + isort | uv + ruff | 2023–2025 mainstream | Single lockfile; single lint/format tool; Railpack-compatible |
| SF1449 titled "…FOR COMMERCIAL ITEMS" | Current revision "…COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES" | 2021 FAR rewrite | Match both title variants |

**Deprecated/outdated:** `.doc` legacy Word — unsupported by python-docx; reject with clear per-file `rejected` status (CLAUDE.md constraint). PyMuPDF — prohibited (AGPL).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Quality-gate thresholds (char_count<20 scanned, alpha_ratio<0.5 gibberish, 2% cid ratio, etc.) | Pattern 5 | Low — explicitly corpus-tunable constants per user constraint; wrong initial values are caught by hostile-package integration tests |
| A2 | Header/footer = normalized line on ≥40% of pages within top/bottom ~8% bands | Pattern 5 | Low — tunable; worst case some noise remains in text, caught in Phase 2 evals |
| A3 | `page.images` attribute on pdfplumber pages (image presence signal) | Pattern 1 | Trivial — pdfplumber documents object types incl. images; verify in first implementation run |
| A4 | pdfplumber throughput on 100–300 page PDFs is seconds-to-low-minutes per file (pdfminer.six based) | Performance notes | Low — CLI harness is offline; if slow, cache parse artifacts keyed by sha256 |
| A5 | Exact heading regex forms (SECTION X, PART I–IV, L.4.2 numbering, dash variants) | Pattern 3 | Medium — the corpus exists precisely to falsify/tune these; detection ladder degrades to role titles |
| A6 | `RenderedPageBreak` markers unreliable across DOCX producers → block ordinals preferred | Pattern 2 | Low — block ordinals are safe regardless; page breaks could later *augment* DOCX locators if present |
| A7 | TOC disambiguation heuristic (many-headings page ⇒ TOC; prefer later leading-line occurrence) | Pattern 3 | Medium — core to success criterion 2; validate on primary corpus package early |
| A8 | Archived SAM.gov notices retain downloadable attachments | Corpus Sourcing | Low — active notices suffice if not |
| A9 | Single-artifact JSON with inline cleaned text ≈1–2 MB for 300-page package | Pattern 6 | Low — if larger, split text into sibling artifact without schema break (text refs) |
| A10 | Approximate package ages/download volumes in legitimacy audit table | Package Legitimacy Audit | None — slopcheck verdicts and PyPI version history are the operative evidence |

## Open Questions

1. **Does the chosen primary corpus package use SF33 or SF1449 cover?**
   - What we know: DoD services solicitations usually SF33 + full UCF; some full-UCF-ish packages ship on SF1449.
   - What's unclear: Can't know until Ross/executor selects the package.
   - Recommendation: Classification treats SF1449 + detected L/M sections as `partial_ucf` (not `non_ucf`) — form signal and structure signal are independent; encode that explicitly.
2. **How reliable are DOCX heading styles in real federal attachments?**
   - What we know: python-docx exposes `style.name`; federal docs often use direct formatting.
   - Recommendation: Implement style-first + text-heuristic fallback (Pattern 2/Pitfall 4); measure on corpus DOCX files.
3. **Where exactly does the amendment number live on text-layer SF30s as extracted?**
   - What we know: Block 2 "AMENDMENT/MODIFICATION NO." (verified form layout); extraction order of form fields varies with layout mode.
   - Recommendation: Try default extraction first, `layout=True` on page 1 as fallback; regex for the label with a nearby token; accept `amendment_number: None` with the amendment still labeled.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime (needs ≥3.12) | ✓ | 3.14.6 (system) | uv can pin/install project Python 3.12+ independently |
| uv | D-08 env/lockfile | ✗ | — | **Install step required:** `winget install astral-sh.uv` (winget verified present) or PowerShell installer from docs.astral.sh/uv |
| git | D-07 repo | ✓ | 2.55.0.windows.1 | — |
| gh CLI | D-07 public GitHub repo creation | ✓ | authenticated as `rconn0925` | — |
| ruff / pytest | D-08 | via uv dev deps | (0.15.22 / 9.1.1 on PyPI) | — |
| slopcheck | package gating | ✓ | installed | — |
| Internet + browser | D-01 manual SAM.gov corpus download | ✓ (assumed on dev machine) | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** uv (trivial winget install — make it an explicit early task).
**Additional finding:** `C:\Users\ross\Projects\rfp-analyzer` is **not yet a git repository** — Phase 1 plan must include `git init`, initial commit hygiene, `.gitignore` before any corpus files land, and `gh repo create` (public) per D-07. Note: `.planning/` docs — decide whether they're committed to the public repo or excluded; GSD `commit_docs: true` implies committed, which is fine for a portfolio repo but the planner should surface it.

## Security Domain

Phase 1 is a local CLI over local files: no auth, no sessions, no network, no crypto. Applicable ASVS categories:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Treat corpus files as hostile: per-file exception isolation (malformed PDFs), extension allowlist (`.pdf`/`.docx` parsed, `.doc`/others rejected explicitly), no `eval`/exec of document content, path handling via `pathlib` under the given package dir only |
| V6 Cryptography | no (hashing only) | `hashlib.sha256` for file identity — integrity, not security |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/pathological PDF (parser DoS: deep object graphs, decompression bombs) | Denial of Service | Per-file try/except; document a per-file wall-clock guard as a known limitation (a hung parse is visible on a local CLI); size sanity check before parse `[ASSUMED: no hard timeout in Phase 1 — acceptable for local CLI, revisit before web upload in Phase 4]` |
| Secrets in public repo | Information Disclosure | D-07: env vars only; `.gitignore` corpus (real solicitation docs are public data, but keep binaries out anyway); no keys exist in Phase 1 |
| Document text later treated as instructions (prompt injection) | Tampering | Out of scope this phase (no LLM calls); document map stores text as data only — nothing to mitigate yet |

## Sources

### Primary (HIGH confidence)
- github.com/jsvine/pdfplumber (README, fetched 2026-07-22) — open/pages, extract_text params (x_tolerance/y_tolerance/layout), extract_words positions, extract_text_lines (experimental), extract_tables/table_settings, dedupe_chars signature, Page.close() memory guidance, v0.11.10 current
- python-docx.readthedocs.io/en/latest/ + /api/document.html — `iter_inner_content() → Iterator[Paragraph | Table]`, `paragraphs`/`tables`/`sections` properties, style names, RenderedPageBreak existence, v1.2.0
- acquisition.gov/far/15.204-1 — UCF Parts I–IV, Sections A–M exact titles
- acquisition.gov/far/12.603 — combined synopsis/solicitation: single-document notice, SF1449 *not* used under 12.603
- gsa.gov/system/files/SF30-16c.pdf + acq.osd.mil SF-30 reference — SF30 title text, block structure (Item 2 amendment no., Item 14 description, Item 11 solicitation amendments)
- docs.astral.sh/uv/guides/integration/github/ — astral-sh/setup-uv action, `uv sync --locked`, `uv run pytest` CI pattern
- PyPI via `pip index versions` (2026-07-22) — all six package versions
- slopcheck audit (2026-07-22) — 6/6 OK

### Secondary (MEDIUM confidence)
- irs.gov/pub/irs-procure/sf1449.rtf, dla.mil SF1449 guide — SF1449 title text and usage conditions
- energy.gov SF-33 specimen PDFs, fedsubk.com solicitation anatomy — SF33 title, Block 9 TOC content
- sam.gov/opportunities + practitioner guides (govdash.com, govtrove.com) — public search/download without account, notice-type filters

### Tertiary (LOW confidence / training knowledge, flagged in Assumptions Log)
- pdfminer `(cid:N)` artifact behavior; header/footer frequency technique; threshold starting values; pdfplumber throughput estimates; DOCX direct-formatting prevalence in federal documents

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version re-verified on PyPI today; slopcheck clean; APIs confirmed against official docs
- Architecture (schema/module design): HIGH — constrained by locked CONTEXT decisions and ARCHITECTURE.md; Locator-union generalization is the one novel call, justified by verified DOCX paginationlessness
- Section-detection heuristics: MEDIUM — form titles and UCF structure verified; exact regexes/disambiguation are hypotheses the 3-package corpus exists to validate (by design, per user constraints)
- Pitfalls: HIGH — grounded in verified API behavior + project PITFALLS.md
- Corpus sourcing: MEDIUM-HIGH — public download verified; archived-attachment availability assumed

**Research date:** 2026-07-22
**Valid until:** ~2026-08-22 (stable libraries; UCF/FAR structure moving slowly — note the FAR Overhaul may alter solicitation formats over 2026, warranting re-check at Phase 2)
