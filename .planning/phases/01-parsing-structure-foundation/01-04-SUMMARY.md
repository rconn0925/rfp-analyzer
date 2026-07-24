---
phase: 01-parsing-structure-foundation
plan: 04
subsystem: pipeline
tags: [quality-gates, header-stripping, pdfplumber, pydantic, tdd]

# Dependency graph
requires:
  - phase: 01-parsing-structure-foundation (plan 01-01)
    provides: PageInfo/ParsedFile schema contract (quality literals, stripped_headers field)
  - phase: 01-parsing-structure-foundation (plan 01-03)
    provides: parse_pdf producing quality="pending" pages with raw text and parse-time metrics (cid_count, replacement_char_count, has_images)
provides:
  - rfp_analyzer.pipeline.quality package with apply_quality(ParsedFile) -> ParsedFile stage function
  - classify_page/compute_page_metrics per RESEARCH Pattern 5 (ok/scanned/empty/low_text/gibberish)
  - Cross-page frequency header/footer stripping with patterns recorded on ParsedFile.stripped_headers
  - Five tunable threshold constants + injectable QualityThresholds dataclass for corpus calibration
affects: [01-05 sectioning (consumes cleaned ok-page text), 01-06 document map assembly, phase-02 extraction]

# Tech tracking
tech-stack:
  added: []
  patterns: [stage function signature apply_quality(ParsedFile) -> ParsedFile, call-time-resolved DEFAULT_THRESHOLDS for tunable constants, classification-before-stripping ordering]

key-files:
  created:
    - src/rfp_analyzer/pipeline/quality/__init__.py
    - src/rfp_analyzer/pipeline/quality/gates.py
    - src/rfp_analyzer/pipeline/quality/headers.py
    - tests/unit/test_quality_gates.py
    - tests/unit/test_headers.py
  modified: []

key-decisions:
  - "DEFAULT_THRESHOLDS resolved at call time (thresholds=None -> module lookup) so monkeypatch/tuning swaps work without reload"
  - "MIN_VOTING_PAGES=2 guard: files with fewer than 2 OK pages get no header stripping (frequency meaningless without repetition)"
  - "detect_running_lines votes over whatever pages the caller passes; apply_quality passes only OK-classified pages (scanned pages have no text to vote with)"
  - "DOCX files pass through apply_quality untouched — docx headers/footers live in section properties python-docx never interleaves into body blocks"

patterns-established:
  - "Pipeline stage function: apply_quality(ParsedFile, thresholds=None) -> ParsedFile, pass-through for non-ok parse_status"
  - "Threshold provenance: every constant docstringed with its RESEARCH assumption tag (A1/A2) for tuning traceability"

requirements-completed: [PARS-01]

# Metrics
duration: 6min
completed: 2026-07-24
---

# Phase 01 Plan 04: Quality Gates & Header Stripping Summary

**Per-page quality classification (ok/scanned/empty/low_text/gibberish) with tunable thresholds plus cross-page frequency header/footer stripping, wired into a single apply_quality stage — validated against the hostile corpus (370-page spec: 23 bad pages caught, real running header stripped, zero pending)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-24T00:30:24Z
- **Completed:** 2026-07-24T00:36:45Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 5 created

## Accomplishments

- `classify_page` implements RESEARCH Pattern 5 exactly: scanned (<20 chars + images), empty (<20 chars, no images), low_text (<150 chars + images), gibberish (alpha_ratio < 0.5 OR cid ratio > 0.02 OR >5 U+FFFD), else ok — all five paths tested
- `compute_page_metrics` is a single-pass O(n) scan (no regex — T-01-10 mitigation); alpha_ratio of "" is 0.0, not ZeroDivisionError; parse-time metrics merged with precedence (reuse, don't recompute)
- Thresholds are five named module constants + a frozen `QualityThresholds` dataclass; `DEFAULT_THRESHOLDS` is resolved at call time, proven tunable by monkeypatch and explicit-injection tests (A1 provenance docstrings)
- `detect_running_lines`: digit-stripped/whitespace-collapsed/uppercased keys over top/bottom 2-line bands, >= 40% of OK pages (A2); "Page 3 of 120" and "Page 47 of 120" fold to one pattern
- `apply_quality` stage function: classification before stripping, only OK pages vote, non-ok pages flagged with text emptied (D-03 — T-01-11 mitigation), stripped patterns recorded sorted on `ParsedFile.stripped_headers`, DOCX/failed files pass through — no `"pending"` survives (tested)
- No OCR/Docling code anywhere in the quality package (D-03 flag-and-surface, D-04 deferred) — verified by grep

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1: Per-page metrics and status classification** — `3a7dc91` (test, RED), `bc7298e` (feat, GREEN)
2. **Task 2: Header/footer stripping and apply_quality** — `066c1e1` (test, RED), `429e1af` (feat, GREEN)

No refactor commits needed — GREEN implementations passed lint/format with minor test-file formatting folded into the Task 2 feat commit.

## Files Created/Modified

- `src/rfp_analyzer/pipeline/quality/gates.py` — compute_page_metrics + classify_page + QualityThresholds/DEFAULT_THRESHOLDS + five A1-tagged constants
- `src/rfp_analyzer/pipeline/quality/headers.py` — detect_running_lines + apply_quality stage function + HEADER_FREQ_THRESHOLD/RUNNING_LINE_BAND/MIN_VOTING_PAGES (A2)
- `src/rfp_analyzer/pipeline/quality/__init__.py` — package exports (apply_quality, classify_page, compute_page_metrics, thresholds)
- `tests/unit/test_quality_gates.py` — 13 tests covering all five statuses, empty-string safety, threshold tunability
- `tests/unit/test_headers.py` — 7 tests covering detection/normalization/frequency threshold, scanned-page emptying, DOCX/failed pass-through, no-pending invariant

## Decisions Made

- `classify_page(page, thresholds=None)` resolves `DEFAULT_THRESHOLDS` at call time rather than binding it as a parameter default — makes the constants genuinely swappable for corpus tuning and testable via monkeypatch
- Added `MIN_VOTING_PAGES=2` guard (not in plan text, implied by the technique): with <2 OK pages, any line trivially exceeds 40%, so single-page files would lose their first/last lines
- `detect_running_lines` counts each pattern at most once per page (set per page) so a header repeated within one page can't inflate frequency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used `uv run python -m pytest` instead of `uv run pytest`**
- **Found during:** Task 1 (verification)
- **Issue:** The `pytest` executable is blocked by a Windows Application Control policy on this machine (known from prior executor)
- **Fix:** Ran the module form `uv run python -m pytest` for all verification commands — identical behavior
- **Files modified:** none
- **Verification:** Full unit suite green (43 passed, 1 skipped)

---

**Total deviations:** 1 auto-fixed (1 blocking, environment-only)
**Impact on plan:** None — command substitution only, no code or scope changes.

## Corpus Sanity Check (optional verification — findings for threshold tuning)

Ran `apply_quality` over the hostile-scanned corpus package (read-only, from the main checkout since the corpus is gitignored):

| File | Pages | Statuses | Stripped patterns | Pending |
|------|-------|----------|-------------------|---------|
| Bid Abstract (SF-1409) | 2 | ok: 2 | 4 (SF form boilerplate lines) | 0 |
| Planset (CAD drawings) | 36 | gibberish: 36 | — | 0 |
| Specifications | 370 | ok: 347, gibberish: 14, low_text: 7, scanned: 2 | `MILLER-RICE PILE DIKE SYSTEM REPAIRS`, `SECTION . PAGE` | 0 |

- **D-03 works on real hostile data:** the drawing planset is fully flagged (as gibberish — sparse vector-text soup with alpha_ratio < 0.5 — rather than scanned, since CAD pages carry >20 chars of coordinate text; either way it is surfaced, never silent garbage)
- **Header stripping catches the real running header** on the 370-page spec and folds `SECTION 01 11 00 / PAGE N` variants into one normalized pattern
- **Tuning note:** on the 2-page bid abstract, 40% of 2 pages means any line on both pages is stripped (4 patterns, all genuine SF-form boilerplate here — but small files are the most aggressive stripping regime; revisit if corpus grows)

## Known Stubs

None — no placeholder values, empty-data wiring, or TODO markers in the delivered code.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or trust-boundary changes beyond the plan's threat model. T-01-10 (single-pass metrics, no regex) and T-01-11 (no pending survives, non-ok text emptied) mitigations implemented and tested as planned.

## TDD Gate Compliance

Both tasks followed RED → GREEN: `3a7dc91` (test) → `bc7298e` (feat), `066c1e1` (test) → `429e1af` (feat). RED phases confirmed failing (import errors) before implementation.

## Issues Encountered

- Three E501 line-length lint errors in test_headers.py fixed before the Task 2 feat commit (ruff check + format clean on all delivered files)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `apply_quality` is ready for plan 01-05/01-06 pipeline assembly: sectioning can consume cleaned ok-page text with headers already stripped
- Note for the orchestrator: the plan's "commit + push, CI green" acceptance item is deferred to the post-wave merge — worktree executors do not push
- Threshold constants are documented and injectable; corpus evidence above gives a tuning baseline

## Self-Check: PASSED

All 5 created source/test files and the 4 task commits (`3a7dc91`, `bc7298e`, `066c1e1`, `429e1af`) verified present on the worktree branch.

---
*Phase: 01-parsing-structure-foundation*
*Completed: 2026-07-24*
