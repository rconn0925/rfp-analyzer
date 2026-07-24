---
phase: 02-requirement-extraction-grounding
plan: 03
subsystem: extraction
tags: [chunking, page_map, keyword-sweep, reconciliation, sf30-amendments, pure-python, tdd]

# Dependency graph
requires:
  - phase: 02-01
    provides: Chunk / Requirement / SourceRef (doc_role) / MissedCandidate models + shared normalize()
provides:
  - "iter_chunks(document_map, max_input_chars=48000): section-scoped chunker reaching every ok file/section with page_map + doc_role (EXTR-04)"
  - "sweep_hits() + reconcile() + flag_over_extractions(): deterministic binding-keyword sweep and model-miss reconciliation (EXTR-03/05)"
  - "flag_amendments(): doc_role-gated SF30 change detection with possibly_modified/affects flagging, no merge (INTK-03)"
affects: [02-02 grounding, extraction orchestration, eval harness, cli extract subcommand]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Section-scoped windowing with overlapping page windows + per-chunk page_map (RESEARCH Pattern 1)"
    - "Abbreviation-guarded pure-Python sentence segmentation (no new dep)"
    - "doc_role gate before change-verb regex — provenance, not text, decides amendment flagging"

key-files:
  created:
    - src/rfp_analyzer/pipeline/extraction/__init__.py
    - src/rfp_analyzer/pipeline/extraction/chunker.py
    - src/rfp_analyzer/pipeline/sweep.py
    - src/rfp_analyzer/pipeline/amendments.py
    - tests/unit/test_chunker.py
    - tests/unit/test_sweep.py
    - tests/unit/test_amendments.py
  modified: []

key-decisions:
  - "Sectionless ok files get a whole-file fallback chunk so EXTR-04 'every file' holds for structureless attachments"
  - "DOCX BlockSpan sections emit text with an empty page_map — never synthesize a PDF page"
  - "sweep_hits/reconcile stay pure-Python (substring overlap, no rapidfuzz) — this plan adds no deps; rapidfuzz is a sibling plan's concern"
  - "Over-extraction detection exposed as a separate flag_over_extractions() helper, keeping reconcile()'s (requirements, missed_candidates) signature intact"

patterns-established:
  - "Pattern 1: chunker windows oversize sections into overlapping page windows, each carrying a self-consistent page_map"
  - "Pattern 6: deterministic sweep is a recall floor / candidate surface, not ground truth"
  - "Pattern 7: doc_role=='amendment' gate is the decisive guard; base FAR change-verbs are never candidates"

requirements-completed: [EXTR-03, EXTR-04, EXTR-05, INTK-03]

# Metrics
duration: ~35min
completed: 2026-07-24
---

# Phase 2 Plan 03: Chunker, Keyword Sweep & SF30 Amendment Flagging Summary

**Three pure-Python transformations around the model call: a section-scoped chunker that reaches every file/section with page provenance (EXTR-04), a deterministic binding-keyword sweep that reconciles against extraction to surface misses (EXTR-05), and a doc_role-gated SF30 change detector that flags without merging (INTK-03) — all CI-testable, no GPU/Ollama/corpus.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (all TDD RED→GREEN)
- **Files created:** 7 (3 modules + 1 package init + 3 test files)
- **Tests:** 22 new (8 chunker, 8 sweep, 6 amendments); full unit suite 192 passed, 1 skipped

## Accomplishments

- **Chunker (EXTR-04):** `iter_chunks` walks every `parse_status=="ok"` file and recursively every section, concatenating only `ok`-quality page text and building a `(char_start, char_end, page_number)` page_map. Oversize sections window into overlapping page windows (~1 page overlap) capped at `max_input_chars` (default 48000, eval-tunable). Attachments, Section C, and even sectionless files are reachable; DOCX block spans emit text with an empty page_map (no invented pages); every chunk carries the file's `doc_role`.
- **Sweep + reconciliation (EXTR-03/05):** `sweep_hits` segments normalized page text with an abbreviation-guarded splitter (No./U.S./e.g./section numbers never split), keeps binding-keyword sentences, and reports the strongest keyword ("shall not" outranks "shall"). `reconcile` surfaces uncovered hits as `MissedCandidate` rows and stamps each covered requirement's authoritative `binding_keyword` from source. `flag_over_extractions` is the precision-side reverse check.
- **SF30 amendments (INTK-03):** `flag_amendments` gates candidate change statements on `source_ref.doc_role=="amendment"` FIRST, then applies the Pattern 7 change-verb regex. Referenced base sections get `possibly_modified=True` + an `affects` back-pointer; both rows are always retained. The strengthened test proves the doc_role gate — not the regex — is decisive: identical FAR change-verb text flags only the amendment row.

## Task Commits

Each task was committed atomically (TDD test → feat):

1. **Task 1: Section-scoped chunker (EXTR-04)** — `ce063a6` (test) → `54c12e7` (feat)
2. **Task 2: Deterministic keyword sweep + reconciliation (EXTR-05)** — `fb91ad8` (test) → `c49e085` (feat)
3. **Task 3: SF30 amendment change detection (INTK-03)** — `11b6127` (test) → `14271ed` (feat)

## Files Created/Modified

- `src/rfp_analyzer/pipeline/extraction/__init__.py` — extraction stage package docstring
- `src/rfp_analyzer/pipeline/extraction/chunker.py` — `iter_chunks`; section walk, page_map assembly, overlapping windowing, DOCX/sectionless handling
- `src/rfp_analyzer/pipeline/sweep.py` — `SweepHit`, `sweep_hits`, `reconcile`, `flag_over_extractions`; abbreviation-guarded segmentation, binding-keyword precedence
- `src/rfp_analyzer/pipeline/amendments.py` — `flag_amendments`; doc_role gate, change-verb regex, section-reference matching
- `tests/unit/test_chunker.py`, `tests/unit/test_sweep.py`, `tests/unit/test_amendments.py` — 22 behavior tests

## Decisions Made

- **Whole-file fallback for sectionless files:** the must_haves truth says the chunker emits chunks for *every* file; real attachments (CDRL lists) often lack a section tree, so an ok file with no sections yields one chunk over its ok pages. Documented in the module.
- **Pure-Python overlap in sweep/reconcile:** the plan forbids adding deps here (rapidfuzz belongs to a sibling plan). `_overlaps` uses normalized substring containment either direction — deterministic and sufficient since both sides derive from the same normalized page text.
- **`flag_over_extractions` as a separate helper:** the behavior asks for a precision-side "possible over-extraction" surface, but `reconcile`'s signature is fixed to `(requirements, missed_candidates)` and `Requirement` has no over-extraction field. A separate exported helper returns the unsupported subset ("a separate list", per the behavior text) without a model change.

## Deviations from Plan

None requiring deviation rules. Two small in-scope test-fixture calibrations during GREEN:

- Task 1's windowing fixture initially sized two 30-char pages against `max_input_chars=60`; the joiner pushed the pair to 61 chars, yielding single-page windows that cannot overlap. Raised the cap to 70 so 2 pages/window occur and the overlap assertion is meaningful. The chunker behavior was correct; only the fixture arithmetic was off.

## Issues Encountered

None. All three modules landed on the first GREEN pass after the fixture calibration above.

## User Setup Required

None — pure-Python pipeline code, no external services, no new dependencies.

## Next Phase Readiness

- Chunks with `page_map` + `doc_role` are ready for 02-02 grounding (`build_source_ref` maps char offsets back through page_map to a page number).
- `reconcile` output (`MissedCandidate` list) and `flag_over_extractions` are ready to feed the extraction orchestrator's report and the eval harness.
- `flag_amendments` is ready to run over the grounded requirement set; SF30 Block 2 amendment-number recovery remains deliberately out of scope (RESEARCH Open Question 3).
- No STATE.md/ROADMAP.md changes made (parallel-executor constraint).

## Self-Check: PASSED

- All 8 created files verified on disk.
- All 6 task commits verified in git log (ce063a6, 54c12e7, fb91ad8, c49e085, 11b6127, 14271ed).
- `tests/unit/test_chunker.py tests/unit/test_sweep.py tests/unit/test_amendments.py`: 22 passed.
- Full unit suite: 192 passed, 1 skipped. ruff clean on all three modules.

---
*Phase: 02-requirement-extraction-grounding*
*Completed: 2026-07-24*
