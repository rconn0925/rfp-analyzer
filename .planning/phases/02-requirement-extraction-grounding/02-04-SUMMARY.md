---
phase: 02-requirement-extraction-grounding
plan: 04
subsystem: testing
tags: [golden-set, eval, ground-truth, recall-precision, verbatim-grounding, federal-rfp]

# Dependency graph
requires:
  - phase: 01-parsing-structure-foundation
    provides: DocumentMap with cleaned per-page text, section boundaries, and file_ids for the primary package
  - phase: 02-requirement-extraction-grounding (02-01)
    provides: Requirement/SourceRef Pydantic contract whose fields the golden entries mirror
provides:
  - Hand-shredded, adversarially-validated golden set of 103 ground-truth requirements for N4008526R0033
  - Committed locatability gate (check_golden.py + test_golden_verbatim.py) verifying every verbatim on its cited page
  - schema.md (entry-shape docs) and review-note.md (method, findings, coverage, honest caveat)
affects: [02-07-eval-harness, 02-06-bakeoff, requirement-extraction, recall-precision-scoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-pass agent golden-set build (draft + adversarial keyword-sweep miss-check) replacing a human checkpoint"
    - "Two-field ground truth: real contiguous verbatim_text grounds; atomic_obligation is the single-duty rewrite"
    - "Table-interleave-aware span selection: trim verbatim spans where three-column PWS titles contaminate the text stream"
    - "Committed locatability test that skips cleanly when the gitignored corpus/artifact is absent (CI-safe)"

key-files:
  created:
    - tests/eval/__init__.py
    - tests/eval/golden/__init__.py
    - tests/eval/golden/golden_set.json
    - tests/eval/golden/schema.md
    - tests/eval/golden/review-note.md
    - tests/eval/golden/check_golden.py
    - tests/eval/test_golden_verbatim.py
  modified: []

key-decisions:
  - "Golden set is a representative baseline, not an exhaustive shred; 65 residual sweep-hits on covered pages are documented, not hidden"
  - "Excluded government/CO-action statements, near-duplicates, and FAR clause full-text (pp.52-57) as non-obligations"
  - "Atomic siblings share one verbatim span except where a table-column title breaks contiguity — then distinct real spans"

patterns-established:
  - "Pattern: grounding-identical normalization (NFKC + de-hyphenation + whitespace collapse) applied to both quote and page"
  - "Pattern: content-derived stable golden IDs (GOLD-sha256[:10] of file_id|norm-verbatim|atomic_ord)"

requirements-completed: [EXTR-01, EXTR-05]

# Metrics
duration: 42min
completed: 2026-07-24
---

# Phase 2 Plan 04: Golden-Set Ground Truth Summary

**Hand-shredded, adversarially-validated golden set of 103 atomic ground-truth requirements for federal RFP N4008526R0033 — every verbatim span string-match-verified on its cited page — with a committed locatability gate and an honest coverage/caveat review note.**

## Performance

- **Duration:** ~42 min
- **Started:** 2026-07-24T00:45Z (approx)
- **Completed:** 2026-07-24
- **Tasks:** 2
- **Files modified:** 7 created

## Accomplishments
- **Pass A draft:** 57 ground-truth requirements hand-shredded from Sections L (pp.49-51), M (pp.58-70), C (p.10), and the PWS SOW Annex 0200000 (pp.9-16) — each with `file_id`, `page`, real contiguous `verbatim_text`, `atomic_obligation`, `binding_keyword`, and `req_type`, with 7 compound statements atomically split via `parent_id`.
- **Pass B adversarial validation:** an independent `shall/must/shall not` keyword sweep over the covered pages (154 binding hits) surfaced pass-A misses; reconciled by adding 46 genuine contractor/offeror obligations (final: L 24, M 24, C 5, SOW-Annex 50 = 103 entries, 90 unique verbatim spans, 8 atomic-split groups).
- **Honesty backbone:** every one of the 103 verbatims (100%, zero fuzzy exceptions) is an exact substring of its cited page after grounding-identical normalization, enforced by a committed check.
- **Documentation:** `schema.md` (entry shape + two-field design + splitting rule) and `review-note.md` (two-pass method, concrete findings, coverage scope incl. 65 documented residuals, shared-blind-spot caveat + EXTR-05 mitigation, non-blocking Ross spot-check guide).

## Task Commits

1. **Task 1: Draft the ground-truth golden set (pass A)** - `1b841cd` (feat)
2. **Task 2: Adversarial validation + reconciliation (pass B)** - `c0b9d82` (feat)

## Files Created/Modified
- `tests/eval/golden/golden_set.json` - 103 machine-readable ground-truth requirements + match rule + counts
- `tests/eval/golden/schema.md` - entry-shape documentation, two-field design, atomic splitting rule
- `tests/eval/golden/review-note.md` - build method, adversarial findings, coverage scope, honest caveat, spot-check guide
- `tests/eval/golden/check_golden.py` - standalone locatability gate (exit 0/1/2; reused by the pytest wrapper)
- `tests/eval/test_golden_verbatim.py` - pytest: every verbatim locatable (skips w/o corpus) + corpus-free shape invariants
- `tests/eval/__init__.py`, `tests/eval/golden/__init__.py` - package markers

## Decisions Made
- **Representative, not exhaustive:** the golden set targets solid, measurable coverage of L/M/C and primary SOW obligations rather than every clause in the 290-page package (per plan scope). The 65 residual binding sweep-hits on covered pages are quantified in the review note — roughly a third are correctly-excluded non-obligations (government/CO actions, near-duplicates, sweep fragments); the rest are lower-priority Annex p15-16 mechanics deliberately deferred.
- **Interleave handling:** where the three-column PWS table layout interleaves a title word into the extracted prose, spans are trimmed (or atomic siblings carry distinct real spans) so grounding stays honest.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Added a committed locatability checker + pytest wrapper**
- **Found during:** Task 2 (adversarial validation)
- **Issue:** Task 2 acceptance requires "a checker script confirms each golden verbatim_text ... is a substring of its cited page," but the plan's `files_modified` listed only data/doc files. A trustworthy baseline needs the check to be re-runnable and CI-safe, not a throwaway script.
- **Fix:** Added `tests/eval/golden/check_golden.py` (standalone, grounding-identical normalizer, skips when the gitignored corpus/artifact is absent) and `tests/eval/test_golden_verbatim.py` (pytest wrapper + corpus-free shape invariants). Both are committed and green.
- **Files modified:** tests/eval/golden/check_golden.py, tests/eval/golden/__init__.py, tests/eval/test_golden_verbatim.py
- **Verification:** `uv run python tests/eval/golden/check_golden.py` -> 103/103 pass; full suite 216 passed, 1 skipped; ruff clean.
- **Committed in:** `c0b9d82` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing-critical)
**Impact on plan:** The checker is the mechanical enforcement of the plan's own acceptance criterion and threat mitigations T-02-08/T-02-09. No scope creep — still only writes under `tests/eval/`.

## Issues Encountered
- **Table-column interleaving in PWS annex pages:** the parsed text stream interleaves three-column *Spec Item / Title / Description* title words into the prose, so several human-readable spans were not contiguous. Caught by the pass-A verbatim validation (4 defects) and handled by re-paging/trimming or substituting clean contiguous spans; the same care was applied when authoring pass-B annex entries. Documented in review-note.md.

## User Setup Required
None - no external service configuration required. The golden set validates against the gitignored primary corpus / document-map artifact already present in the main checkout.

## Next Phase Readiness
- The measurement baseline (success criterion 5) exists and is machine-readable with a documented match rule — ready for the 02-07 eval harness and the 14B-vs-32B bake-off to score recall/precision separately against it.
- EXTR-05 deterministic sweep is the independent cross-check that mitigates the agent-built baseline's shared blind spots (documented in review-note.md).
- Optional, non-blocking: Ross spot-check per the review-note guide; findings feed straight back into `golden_set.json`.

---
*Phase: 02-requirement-extraction-grounding*
*Completed: 2026-07-24*

## Self-Check: PASSED

All 8 created files exist on disk; both task commits (1b841cd, c0b9d82) are present in git history.
