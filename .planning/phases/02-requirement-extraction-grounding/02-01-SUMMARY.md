---
phase: 02-requirement-extraction-grounding
plan: 01
subsystem: api
tags: [pydantic, schema, normalization, hashing, grounding, ollama-structured-output]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: DocumentMap/ParsedFile/SectionNode/PageInfo contract, RunMetrics, doc_role labels
provides:
  - SourceRef/RequirementDraft/RequirementBatch/Chunk/Requirement/MissedCandidate/RequirementSet Pydantic models
  - normalize(text) shared canonical text normalizer (grounding/normalize.py)
  - requirement_id + display_label content-derived stable ID scheme (ids.py)
affects: [grounding, chunker, sweep, amendments, extraction, eval-harness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-field verbatim_text + atomic_obligation schema (grounding vs atomicity)"
    - "doc_role provenance on SourceRef (not is_amendment bool) for INTK-03 gating"
    - "Ollama-safe flat schema (Literal enums only, no constrained numerics/recursion)"
    - "Content-hash stable IDs keyed off shared normalizer"

key-files:
  created:
    - src/rfp_analyzer/pipeline/grounding/__init__.py
    - src/rfp_analyzer/pipeline/grounding/normalize.py
    - src/rfp_analyzer/pipeline/ids.py
    - tests/unit/test_requirement_models.py
    - tests/unit/test_normalize.py
    - tests/unit/test_ids.py
  modified:
    - src/rfp_analyzer/pipeline/models.py

key-decisions:
  - "SourceRef carries doc_role: str (provenance) rather than an is_amendment bool — reusable, self-describing"
  - "requirement_id = sha256(file_id|normalize(verbatim)|occurrence|atomic_ord)[:10] — order-independent, content-derived"
  - "ids.py imports the grounding normalizer so hash keys use the same canonical form grounding compares against"

patterns-established:
  - "Single canonical normalizer imported by grounding/ids/sweep — no forked variants"
  - "RequirementDraft/RequirementBatch double as the Ollama format schema and stay flat"

requirements-completed: [EXTR-01, EXTR-02]

# Metrics
duration: 12min
completed: 2026-07-24
---

# Phase 2 Plan 01: Requirement Schema, Normalizer & Stable IDs Summary

**Phase 2 data contract (SourceRef/Requirement/RequirementBatch + 4 siblings), the single canonical NFKC/de-hyphenation normalizer, and a sha256 content-derived stable requirement_id scheme — the interface-first foundation every later Phase 2 module imports.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-24
- **Completed:** 2026-07-24
- **Tasks:** 3 (all TDD RED→GREEN)
- **Files modified:** 7 (1 modified, 6 created)

## Accomplishments
- Extended `models.py` with seven new Pydantic models (SourceRef, RequirementDraft, RequirementBatch, Chunk, Requirement, MissedCandidate, RequirementSet), all round-tripping through JSON; SourceRef carries `doc_role` provenance for INTK-03 amendment gating.
- RequirementBatch's `model_json_schema()` is Ollama-structured-output-safe — asserted free of `minimum`/`maximum`/`minLength`/`maxLength`.
- Created the shared `normalize()` primitive: NFKC ligature fold, soft line-break de-hyphenation (plain `-` and U+00AD), whitespace collapse, idempotent.
- Created `ids.py` with a provably deterministic, content-derived `requirement_id` (reusing the shared normalizer) plus a renumberable `display_label`.

## Task Commits

Each task was committed atomically (TDD test → feat):

1. **Task 1: Phase 2 requirement schema in models.py** — `1164a40` (test) → `8cae89f` (feat)
2. **Task 2: Shared text normalizer (grounding/normalize.py)** — `5ba6fc7` (test) → `cef537b` (feat)
3. **Task 3: Content-derived stable requirement IDs (ids.py)** — `de2bff1` (test) → `6c6ab48` (feat)

## Files Created/Modified
- `src/rfp_analyzer/pipeline/models.py` — added the seven Phase 2 requirement models (extends, does not break, the Phase 1 contract; DocumentMap.schema_version unchanged)
- `src/rfp_analyzer/pipeline/grounding/__init__.py` — grounding package docstring (EXTR-02 honesty backbone)
- `src/rfp_analyzer/pipeline/grounding/normalize.py` — `normalize(text)` shared canonical normalizer
- `src/rfp_analyzer/pipeline/ids.py` — `requirement_id` + `display_label`
- `tests/unit/test_requirement_models.py` — 9 behavior tests
- `tests/unit/test_normalize.py` — 6 behavior tests
- `tests/unit/test_ids.py` — 6 behavior tests

## Decisions Made
- `SourceRef.doc_role` is a `str` (holds the ParsedFile.doc_role value) rather than a Literal — provenance stays reusable and does not couple SourceRef to the ParsedFile enum vocabulary.
- Field order in `Requirement` places required `verified` after `source_ref` and before the defaulted amendment fields (Pydantic v2 permits required-after-optional; keeps the load-bearing fields grouped).
- All mutable defaults use `Field(default_factory=...)` — verified independent-instance behavior in a test.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. Windows CRLF warnings on commit are cosmetic (git autocrlf); `uv run python -m pytest` was used throughout per the policy-blocked bare `pytest` constraint.

## Threat Model Compliance
- **T-02-01 (Tampering):** RequirementBatch schema asserted flat — no constrained numerics or recursion — so Ollama grammar-constrained decoding cannot be bypassed by a malformed schema (test `test_requirement_batch_schema_has_no_ollama_forbidden_keywords`).
- **T-02-02 (Repudiation):** `requirement_id` hashes `(file_id|normalized_verbatim|occurrence|atomic_ord)`; occurrence + atomic_ord guarantee distinct rows for repeated/atomic-split text (tests `test_atomic_siblings_get_distinct_ids`, `test_repeat_occurrence_gets_distinct_id`).

## Verification
- `uv run python -m pytest tests/unit/test_requirement_models.py tests/unit/test_normalize.py tests/unit/test_ids.py -q` → 21 passed.
- `uv run ruff check src/rfp_analyzer/pipeline/models.py src/rfp_analyzer/pipeline/grounding src/rfp_analyzer/pipeline/ids.py` → clean.
- Full unit suite regression check: `uv run python -m pytest tests/unit -q` → 170 passed, 1 skipped.

## Next Phase Readiness
- Downstream Phase 2 plans (grounding verify, chunker, sweep, amendments, extraction client, eval harness) now have concrete importable contracts and the two pure primitives (`normalize`, `requirement_id`) — no codebase exploration needed.
- No blockers. All three tests are pure-Python and run in CI without Ollama/GPU/corpus.

## Self-Check: PASSED
- Files exist: models.py, grounding/normalize.py, grounding/__init__.py, ids.py, all three test files — verified present.
- Commits exist: 1164a40, 8cae89f, 5ba6fc7, cef537b, de2bff1, 6c6ab48 — verified in git log.

---
*Phase: 02-requirement-extraction-grounding*
*Completed: 2026-07-24*
