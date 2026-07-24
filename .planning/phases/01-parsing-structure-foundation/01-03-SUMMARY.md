---
phase: 01-parsing-structure-foundation
plan: 03
subsystem: parsing
tags: [pdfplumber, python-docx, hashlib, zipfile, pydantic, tdd]

# Dependency graph
requires:
  - phase: 01-parsing-structure-foundation (plan 01-01)
    provides: ParsedFile/PageInfo/BlockInfo schema contract in pipeline/models.py; pdfplumber and python-docx pinned via uv
provides:
  - rfp_analyzer.pipeline.parsing package (discover/pdf/docx modules)
  - discover_files(package_dir) with sha256+file_id identity, .pdf/.docx allowlist, .doc rejection, size cap, resolve()-containment traversal defense
  - parse_pdf(path, sha256=, file_id=) with 1-indexed pages, raw quality metrics (cid_count, replacement_char_count, has_images), page.close() memory guard, page-1 layout text
  - parse_docx(path, sha256=, file_id=) with 0-indexed document-order block ordinals, faithful style names, zip-bomb pre-open guard
  - synthetic PDF/DOCX fixture factories in tests/unit/conftest.py (corpus-free CI)
affects: [01-04 quality gates, 01-05 sectioning/form detection, 01-06 pipeline assembly]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-file failure isolation (parse_status never raises), pre-parse hostile-input guards before library code touches bytes, raw metrics at parse time / quality judgment deferred to later stage]

key-files:
  created:
    - src/rfp_analyzer/pipeline/parsing/__init__.py
    - src/rfp_analyzer/pipeline/parsing/discover.py
    - src/rfp_analyzer/pipeline/parsing/pdf.py
    - src/rfp_analyzer/pipeline/parsing/docx.py
    - tests/unit/conftest.py
    - tests/unit/test_discover.py
    - tests/unit/test_pdf.py
    - tests/unit/test_docx.py
  modified:
    - src/rfp_analyzer/pipeline/models.py

key-decisions:
  - "Extended ParsedFile.file_type Literal with 'other' so rejection records for .doc/.txt/unknown files are representable (Rule 3 — model could not express them)"
  - "Containment check runs before any file read; outside-package rejections carry sha256='' because hashing would mean reading a file that escaped the package dir"
  - "Rejected-but-contained files (.doc, .txt, oversize) are still hashed so every in-package entry has a stable identity"

patterns-established:
  - "Per-file isolation: parse functions never raise — every failure mode is an explicit parse_status on a ParsedFile"
  - "Guards precede parsers: size cap and containment in discovery, zip-bomb check before Document() opens a DOCX"
  - "Parse stage records raw signals only (metrics, quality='pending'); the quality stage owns judgment"

requirements-completed: [PARS-01]

# Metrics
duration: 6min
completed: 2026-07-23
---

# Phase 01 Plan 03: Per-File Parsing Layer Summary

**File discovery with sha256 identity and traversal/size guards, pdfplumber PDF parsing with per-page raw metrics and memory-safe page.close(), and python-docx block-ordinal parsing behind a zip-bomb guard — all failure modes are explicit statuses, never crashes**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-23T22:20:21Z
- **Completed:** 2026-07-23T22:26:35Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 9

## Accomplishments
- `discover_files`: rglob traversal (nested SAM.gov attachment dirs discovered with relative-path filenames), .pdf/.docx allowlist, explicit ".doc legacy Word not supported" rejection, `MAX_FILE_BYTES` cap, and resolve()-containment defense against symlink/junction traversal (T-01-06, T-01-08)
- `parse_pdf`: 1-indexed pages with raw text, `cid_count`/`replacement_char_count`/`has_images` metrics for plan 01-04's quality gates, `page.close()` after each page (T-01-09), layout-mode text captured for page 1 only (feeds plan 01-05 SF-form extraction), whole-body exception isolation (T-01-06 / Pitfall 2)
- `parse_docx`: `iter_inner_content()` document-order blocks with 0-indexed ordinals and faithful style names; stdlib `zipfile` bomb guard (1 GiB uncompressed cap + 200x ratio) rejects hostile archives before python-docx opens them (T-01-07); zero synthesized page numbers
- Synthetic fixture factories (raw-bytes minimal PDF builder, python-docx DOCX builder) keep all 18 new unit tests corpus-free — CI needs no external files

## Task Commits

Each task was committed atomically (TDD: RED test commit, then GREEN feat commit):

1. **Task 1: File discovery with identity, allowlist, and hostile-input guards** — `f862a9f` (test), `a090d7f` (feat)
2. **Task 2: PDF parsing with pdfplumber** — `14667ba` (test), `4bfe61b` (feat)
3. **Task 3: DOCX parsing with python-docx** — `ec0a35e` (test), `7fa5ab5` (feat)

No refactor commits were needed — GREEN implementations passed ruff check/format after formatting was applied pre-commit.

## Files Created/Modified
- `src/rfp_analyzer/pipeline/parsing/__init__.py` — package docstring (pure-library boundary note)
- `src/rfp_analyzer/pipeline/parsing/discover.py` — `discover_files`, `DiscoveredFile` dataclass, `MAX_FILE_BYTES`, streaming sha256 identity
- `src/rfp_analyzer/pipeline/parsing/pdf.py` — `parse_pdf` with per-page metrics and failure isolation
- `src/rfp_analyzer/pipeline/parsing/docx.py` — `parse_docx` with `MAX_DOCX_UNCOMPRESSED`/`MAX_COMPRESSION_RATIO` bomb guard
- `tests/unit/conftest.py` — `make_minimal_pdf` and `make_docx` fixture factories
- `tests/unit/test_discover.py` — 7 discovery behaviors (1 skipped on Windows without symlink privilege)
- `tests/unit/test_pdf.py` — 6 PDF behaviors incl. wall-clock sanity guard
- `tests/unit/test_docx.py` — 6 DOCX behaviors incl. both bomb-guard branches
- `src/rfp_analyzer/pipeline/models.py` — `file_type` Literal widened with `"other"` (see Deviations)

## Decisions Made
- Outside-package files are rejected without being read: their record carries `sha256=""` and a zero-prefixed file_id, since hashing would require following the escaping path. All in-package rejections (.doc/.txt/oversize) are still hashed for stable identity.
- Verified RESEARCH Assumption A3 at implementation: `page.images` exists on pdfplumber 0.11.10 pages; the `page.objects.get("image")` fallback is retained defensively.
- `make_docx` fixture accepts interleaved entries (str, `(text, style)`, `{"table": rows}`) within the plan's `(path, paragraphs, tables=None)` signature so document-order tests can mix paragraphs and tables.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extended ParsedFile.file_type Literal with "other"**
- **Found during:** Task 1 (file discovery)
- **Issue:** Plan requires rejection records to be ParsedFile instances, but `file_type` was `Literal["pdf", "docx"]` — a rejected `.doc`/`.txt`/unknown file had no representable type, making rejection records unconstructible
- **Fix:** Widened the Literal to `Literal["pdf", "docx", "other"]` with a docstring noting `"other"` is only valid on rejected records; additive change, no schema_version bump (existing consumers unaffected — Phase 2 filters on parse_status)
- **Files modified:** src/rfp_analyzer/pipeline/models.py
- **Verification:** Existing test_models.py suite still green; discovery tests construct rejection records for all three cases
- **Committed in:** a090d7f (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal additive schema widening required for the plan's own rejection-record contract. No scope creep.

## Issues Encountered
- The `pytest` executable is blocked by a Windows Application Control policy in this environment; all test runs used `uv run python -m pytest` instead (identical behavior).
- Task 3's "commit + push, CI green" acceptance item: push is deferred to the orchestrator — this plan executed in a parallel worktree whose branch the orchestrator merges and pushes after the wave completes. Full local suite (`uv run python -m pytest tests/unit -q`) is green: 23 passed, 1 skipped.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 01-04 (quality gates) can consume `PageInfo.metrics` (`cid_count`, `replacement_char_count`, `has_images`) and `char_count`; every page arrives `quality="pending"` with raw text.
- Plan 01-05 (sectioning/form detection) can consume `first_page_layout_text` for SF-form field extraction and DOCX `BlockInfo.style` names for heading detection.
- Known residual (accepted per threat model T-01-06): no hard wall-clock timeout on pathological PDFs — must revisit before Phase 4 web upload.

## Known Stubs
None — all modules fully implemented; no placeholders, TODOs, or unwired data paths.

## Self-Check: PASSED

All 8 created/modified source and test files exist on disk; all 6 task commits (f862a9f, a090d7f, 14667ba, 4bfe61b, ec0a35e, 7fa5ab5) verified in git log; full unit suite green (23 passed, 1 skipped).

---
*Phase: 01-parsing-structure-foundation*
*Completed: 2026-07-23*
