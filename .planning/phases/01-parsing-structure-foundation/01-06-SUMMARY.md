---
phase: 01-parsing-structure-foundation
plan: 06
subsystem: pipeline
tags: [cli, argparse, pydantic, pdfplumber, integration-tests, pytest, document-map]

# Dependency graph
requires:
  - phase: 01-parsing-structure-foundation (plans 01-01..01-05)
    provides: scaffold + schema (01-01), corpus + manifests (01-02), parsing/discovery (01-03), quality gates (01-04), sectioning + classification (01-05)
provides:
  - run_pipeline(package_dir) -> DocumentMap — pure end-to-end orchestration with per-stage timings
  - Real `rfp-analyzer parse <package-dir> --out <dir>` CLI with D-05 dual output (document_map.json + stdout section-tree report)
  - Corpus-driven integration suite (10 tests) pinning all four phase success criteria to manifest.json expectations
  - Verified Phase 2 input contract: three real federal packages produce validating document maps
affects: [phase-02-extraction, phase-03, cli, evals]

# Tech tracking
tech-stack:
  added: []
  patterns: [pure-pipeline-orchestration, cli-wraps-library-one-import-direction, corpus-portable-tests-from-manifest, session-scoped-pipeline-cache, no-corpus-auto-skip]

key-files:
  created:
    - src/rfp_analyzer/pipeline/run.py
    - tests/integration/__init__.py
    - tests/integration/conftest.py
    - tests/integration/test_corpus_packages.py
  modified:
    - src/rfp_analyzer/cli.py
    - src/rfp_analyzer/pipeline/classify/package.py
    - tests/unit/test_package_classify.py
    - tests/corpus/manifest.json
    - tests/corpus/MANIFEST.md
    - .github/workflows/ci.yml
    - README.md

key-decisions:
  - "Commercial-form packages with role-title-only section nodes classify non_ucf_commercial — only UCF letter sections trigger the Open Question 1 partial_ucf rule (corpus evidence from non-ucf-part12)"
  - "primary-ucf ground truth corrected full_ucf -> partial_ucf: page-1 inspection verified the base solicitation is a genuine SF1449 carrying a complete UCF A-M structure (hybrid); partial_ucf with a verify-package-format warning is the classifier's designed honest answer"
  - "CLI exit codes: 0 success, 1 honest failure (unknown + zero sections), 2 usage errors"
  - "CI runs tests/unit + tests/integration; integration auto-skips without corpus binaries"

patterns-established:
  - "Pipeline orchestration: run_pipeline composes discover -> parse -> quality -> sectioning -> classify as pure f(artifact)->artifact stages, timed via perf_counter into RunMetrics.stage_timings"
  - "Integration expectations read ONLY from tests/corpus/manifest.json fields — corpus-portable, no hardcoded solicitation numbers"
  - "One pipeline run per package per test session (session-scoped cache) — 408-page hostile package parses once (~60s)"

requirements-completed: [PARS-01, PARS-02]

# Metrics
duration: ~45min
completed: 2026-07-24
---

# Phase 1 Plan 6: Pipeline Assembly, CLI Harness & Corpus Verification Summary

**End-to-end `rfp-analyzer parse` CLI producing validating document_map.json + stdout section-tree reports on all three real federal corpus packages, with a 10-test corpus-driven integration suite pinning all four phase success criteria**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-07-24T00:58:56Z
- **Completed:** 2026-07-24T01:45:00Z
- **Tasks:** 4 (Task 3 checkpoint auto-approved under AUTO_MODE with captured evidence)
- **Files modified:** 11

## Accomplishments

- `pipeline/run.py`: pure orchestration of all five stages with perf_counter timings; LLM counters stay zero (D-09 plumbing visible in every report footer)
- Real CLI (D-06 shape) emitting both D-05 artifacts every run; exit code 1 on the machine-checkable honest-failure signal (unknown + zero sections), 2 on usage errors; T-01-16 output paths derive only from the package dir's own name
- 10 corpus-driven integration tests (6 behaviors, parametrized) — all green on the real corpus, all skip cleanly without it (verified by temporarily renaming a package dir: 10 skipped, 0 failed)
- All three corpus packages verified end-to-end: primary partial_ucf with correct L (49-57) / M (58-70) / C (10-11) boundaries and 3 SF30s labeled amendment; hostile honestly unknown with scanned/gibberish/low-text ranges surfaced and emptied; non-UCF flagged non_ucf_commercial with zero fabricated L/M sections
- CI green on the final push (run for 82fadc9: success)

## Task Commits

1. **Task 1: Pipeline orchestration + real CLI** - `b0b1874` (feat)
2. **Task 2 RED: Corpus-driven integration tests** - `2010e33` (test)
3. **Task 2 GREEN: Ground-truth correction + CI integration collection** - `b606cf1` (fix)
4. **Task 3: Checkpoint** - no commit (auto-approved, evidence below)
5. **Task 4: README usage/architecture/corpus docs** - `82fadc9` (docs)

## Files Created/Modified

- `src/rfp_analyzer/pipeline/run.py` - run_pipeline: discover -> parse -> quality -> sectioning -> classify with RunMetrics stage timings
- `src/rfp_analyzer/cli.py` - parse subcommand: JSON artifact + stdout report rendering (classification/evidence, per-file roles, indented section tree with locator ranges, D-03 quality-range notes, warnings, metrics footer)
- `src/rfp_analyzer/pipeline/classify/package.py` - commercial branch now requires UCF *letter* sections (role-title-only nodes are native to FAR Part 12)
- `tests/integration/conftest.py` - manifest.json loader, no-corpus collection skip, session-scoped pipeline cache
- `tests/integration/test_corpus_packages.py` - six behaviors covering SC1-SC4 + totality
- `tests/corpus/manifest.json` / `MANIFEST.md` - primary expected_classification corrected to partial_ucf with rationale
- `.github/workflows/ci.yml` - pytest now collects tests/integration (auto-skips without corpus)
- `README.md` - Usage, Architecture, Test Corpus sections; status "Phase 1 complete"

## Decisions Made

- **Role-title nodes do not contradict a commercial-form signal.** Every FAR Part 12 package natively contains SOW/evaluation prose; only detected UCF letter sections flip SF1449/combined-synopsis packages to partial_ucf (Open Question 1's "detected L/M sections" read literally).
- **primary-ucf is a genuine SF1449/UCF hybrid.** The NAVFAC base solicitation's page 1 is verbatim "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES" yet the document carries a complete SECTION A-M structure. partial_ucf + "verify package format" warning is the honest classification; manifest hypothesis corrected, not the assertion.
- **Amendment numbers unrecoverable from text layer on this corpus.** SF30 Block 2 values are AcroForm field annotations invisible to `extract_text()`; `amendment_number=None` with `form_text` evidence is the honest Phase 1 outcome (see Next Phase Readiness).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Commercial packages with role-title-only nodes mis-classified partial_ucf**
- **Found during:** Task 1 (CLI verification run on non-ucf-part12)
- **Issue:** `classify_package` treated any detected L/M/C-slot node (including role_title detections like a "STATEMENT OF WORK" attachment) as UCF structure, flipping the FAR Part 12 specimen to partial_ucf — violating the plan truth "classified non_ucf_commercial with warnings"
- **Fix:** Commercial branches now key on `any_letter_sections`; role-tagged nodes remain in section trees and evidence
- **Files modified:** src/rfp_analyzer/pipeline/classify/package.py, tests/unit/test_package_classify.py (new pin test)
- **Verification:** non-ucf-part12 now classifies non_ucf_commercial; 101 unit tests pass
- **Committed in:** b0b1874

**2. [Corpus evidence - ground-truth correction] primary-ucf expected_classification full_ucf -> partial_ucf**
- **Found during:** Task 2 (integration RED: `assert 'partial_ucf' == 'full_ucf'`)
- **Issue:** Manifest expectation was a plan-01-02 hypothesis formed before form detection existed; page-1 inspection proves the base form is SF1449
- **Fix:** manifest.json + MANIFEST.md corrected with full rationale — the assertion still reads from manifest; ground truth changed to verified reality, assertions untouched
- **Committed in:** b606cf1

**3. [Rule 2 - Missing critical] CI never collected the integration suite**
- **Found during:** Task 2
- **Issue:** ci.yml ran `pytest tests/unit` only, so the "integration tests auto-skip and CI stays green" truth was unverifiable in CI
- **Fix:** CI now runs `pytest tests/unit tests/integration`
- **Verification:** CI run on 82fadc9 concluded success (integration tests skipped there, as designed)
- **Committed in:** b606cf1

---

**Total deviations:** 3 (1 bug, 1 ground-truth correction, 1 missing critical)
**Impact on plan:** All required for the plan's stated truths. No scope creep. **No heuristic constants were tuned** — quality thresholds, TOC/heading heuristics, and A7 start rules from plans 01-04/01-05 held as-shipped against all three real packages.

## Deferred human verification evidence

Task 3 was a `checkpoint:human-verify` gate, auto-approved under AUTO_MODE. ⚡ Auto-approved checkpoint (human-verify) — evidence captured below for Ross's deferred review. To re-verify by hand, run the three commands in the plan's how-to-verify.

### 1. primary-ucf (`uv run rfp-analyzer parse tests/corpus/primary-ucf --out artifacts`, exit 0)

```
Classification: partial_ucf
  evidence: SF1449 title matched on Solicitation - N4008526R0033.pdf page 1
  evidence: SF30 title matched on Solicitation Amendment N4008526R00330001 SF 30.pdf page 1
  evidence: Section C found at pages 10-11 of Solicitation - N4008526R0033.pdf
  evidence: Section L found at pages 49-57 of Solicitation - N4008526R0033.pdf
  evidence: Section M found at pages 58-70 of Solicitation - N4008526R0033.pdf
  ...
  Solicitation - N4008526R0033.pdf  [base_solicitation]  parse: ok
    SECTION A ... pages 2-9 | C 10-11 | D 12 | E 12-13 | F 14 | G 15-18 | B 19-23 |
    H 24-25 | I 26-42 | J 43-44 | K 45-48 | L 49-57 (6 children L.1-L.6) | M 58-70
  Solicitation Amendment N4008526R00330001 SF 30.pdf  [amendment]  parse: ok
  Solicitation Amendment N4008526R00330002 SF 30.pdf  [amendment]  parse: ok
  Solicitation N4008526R0033 Amendment 0002.pdf  [amendment]  parse: ok
Metrics: files parsed: 7/7  pages parsed: 290  pages flagged: 0
  LLM cost: $0.00 (0 calls)
```

All three SF30-marked files labeled amendment via form_text; L/M start well past page 1 (TOC guard held).

### 2. hostile-scanned (exit 0)

```
Classification: unknown
  evidence: No UCF section headings and no recognized form pages found across 3 file(s)
  ..._Planset.pdf  [attachment]  parse: ok
    pages 1-36: gibberish text layer (broken font encoding)
  ..._Specifications.pdf  [attachment]  parse: ok
    page 1: very little text (partial scan or stamped page)
    pages 2-3: scanned image, no text layer
    page 168: gibberish text layer (broken font encoding)
    pages 300-304, 354: very little text; 356, 359-370: gibberish
Warnings: Package structure unrecognized; downstream extraction has no section anchors to work from.
Metrics: files parsed: 3/3  pages parsed: 408  pages flagged: 59
```

The manifest's known-scanned pages (Specifications pages 2-3) surfaced exactly as the D-03 range note.

### 3. non-ucf-part12 (exit 0)

```
Classification: non_ucf_commercial
  evidence: SF1449 title matched on Solicitation - FA441826Q0079.pdf page 1
  evidence: STATEMENT OF WORK (role sow_pws) found at pages 1-4 of Attachment 01...
  evidence: EVALUATION FACTORS FOR AWARD (role evaluation) found at pages 15-15...
Warnings:
  - Non-UCF commercial package (SF1449 or FAR 12.603 combined synopsis); no Section
    L/M/C structure exists to extract — matrix columns that depend on UCF sections
    will be incomplete.
```

No invented SECTION L/M nodes anywhere (integration test asserts this).

### 4. Artifact spot check (document_map.json)

- hostile Specifications page 2: `quality: "scanned"`, `text: ""` (emptied per D-03)
- hostile Specifications first ok page (p4) carries real text: `"SOLICITATION, OFFER, 1. SOLICITATION NUMBER..."`
- primary base Section L: `{"kind": "pages", "page_start": 49, "page_end": 57}` with 6 children
- All three maps round-trip `DocumentMap.model_validate_json`

### 5. SECTION L page-range sanity check vs the actual PDF (pdfplumber)

Scanned every page of `Solicitation - N4008526R0033.pdf` for leading `SECTION L`/`SECTION M` lines:

```
(page 49, line 2, 'SECTION L - INSTRUCTIONS, CONDITIONS, & NOTICES TO OFFERORS OR QUOTERS')
(page 58, line 2, 'SECTION M - EVALUATION FACTORS FOR AWARD')
```

Reported `page_start` values (L=49, M=58) match the ground-truth heading pages exactly.

## Issues Encountered

- **SF30 amendment numbers are AcroForm values, not page text** — Block 2 of both primary SF30s extracts as the bare label `"2. AMENDMENT/MODIFICATION NUMBER"` with no value in either default or layout mode. `amendment_number` is None (accepted per forms.py contract); the report shows `[amendment]` without a number.
- **Windows console codepage renders em-dashes as `�`** in piped terminal output; `main()` reconfigures stdout/stderr with `errors="replace"` so reports never crash on unencodable characters. The JSON artifact is always UTF-8.

## Corpus observations for Phase 2

- primary base solicitation has SECTION B detected at pages 19-23, *after* G (15-18) — the pricing schedule genuinely appears out of canonical order in this document; only L-before-M ordering is enforced by the classifier's sanity check.
- hostile Specifications.pdf carries a genuine "SPECIAL CONTRACT REQUIREMENTS" role-title node spanning pages 16-370 (construction Div 00 text) — honest signal, does not affect the unknown classification.
- Two attachment PDFs in primary (Section C Annexes, SECTION F ANNEX) contain their own `SECTION F/H` headings — expected, since annexes reproduce section headers; doc_role correctly stays `attachment`.

## Known Stubs

None — the CLI, pipeline, and report are fully wired; no placeholder values flow to output.

## Threat Flags

None — no new security surface beyond the plan's threat model (T-01-15/16/17 mitigations implemented as specified).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2's input contract is proven: three real federal packages produce schema-valid document maps with sections, quality-gated text, and doc roles.
- Phase 2 candidates surfaced by this corpus: AcroForm field reading for SF30 Block 2 amendment numbers; noisy paragraph-title truncation (some L.x/C.x titles absorb body text).
- The primary-ucf package (partial_ucf hybrid) is ready to become the hand-shredded golden set.

## Self-Check: PASSED

All key files exist on disk; commits b0b1874, 2010e33, b606cf1, 82fadc9 present in git log; conftest references manifest.json (3 occurrences).

---
*Phase: 01-parsing-structure-foundation*
*Completed: 2026-07-24*
