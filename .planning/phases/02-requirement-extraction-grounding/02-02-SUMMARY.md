---
phase: 02-requirement-extraction-grounding
plan: 02
subsystem: pipeline
tags: [grounding, rapidfuzz, verbatim-verification, anti-hallucination, extr-02]

# Dependency graph
requires:
  - phase: 02-requirement-extraction-grounding
    plan: 01
    provides: SourceRef/Chunk Pydantic models, normalize(text) shared normalizer
provides:
  - "ground(verbatim, page_text, threshold) -> (kind, start, end, score) | None — verbatim locate primitive"
  - "build_source_ref(verbatim, chunk, threshold) -> SourceRef — map-computed, string-verified provenance"
  - "DEFAULT_THRESHOLD (92.0) module constant — eval-tunable grounding threshold"
affects: [extraction, sweep, amendments, eval-harness]

# Tech tracking
tech-stack:
  added:
    - "rapidfuzz>=3.14.5 (MIT, C++-backed fuzzy matching; partial_ratio_alignment for span location)"
  patterns:
    - "Grounding = normalize both sides -> exact substring (100.0) -> rapidfuzz fuzzy at/above threshold"
    - "Page number computed ONLY from chunk.page_map, never from model output (EXTR-02 honesty backbone)"
    - "Ungroundable quotes flagged verified=False/page=None, never dropped"
    - "doc_role threaded onto every SourceRef (grounded AND ungroundable) for INTK-03 gating"

key-files:
  created:
    - src/rfp_analyzer/pipeline/grounding/verify.py
    - tests/unit/test_grounding.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Use rapidfuzz dest_start/dest_end (haystack offsets), NOT src_start/src_end (query offsets), to locate the span in page text — the RESEARCH Pattern 5 snippet used src_* which would index the wrong string (Rule 1 fix)"
  - "ground() returns offsets into the NORMALIZED page text; build_source_ref maps that offset to a page via page_map bands over normalized chunk text"
  - "_page_for_offset falls back to the last band starting at/before the offset so an offset on the final band's exclusive end still resolves to a real map page (never invents one)"

patterns-established:
  - "grounding/verify.py is the single anti-hallucination gate: no model-emitted citation reaches output"

requirements-completed: [EXTR-02]

# Metrics
duration: 14min
completed: 2026-07-24
---

# Phase 2 Plan 02: Verbatim Grounding (rapidfuzz verify + computed SourceRef) Summary

**The EXTR-02 honesty backbone: `ground()` locates a requirement's `verbatim_text` in real page text (exact then rapidfuzz-fuzzy after shared normalization), and `build_source_ref()` computes a `SourceRef` whose page comes only from the chunk's `page_map` — never a model citation — flagging unlocatable quotes `verified=False`/`page=None` rather than dropping them or inventing a page.**

## Performance

- **Duration:** ~14 min
- **Completed:** 2026-07-24

## What Was Built

Two primitives in `src/rfp_analyzer/pipeline/grounding/verify.py`:

- **`ground(verbatim, page_text, threshold=92.0)`** — normalizes both sides (NFKC + de-hyphenation + whitespace collapse via the shared `normalize`), tries an exact substring hit (score 100.0), else `rapidfuzz.fuzz.partial_ratio_alignment` accepting a hit at/above `DEFAULT_THRESHOLD`. Returns `(match_kind, start, end, score)` indexing the normalized page text, or `None` for empty/whitespace/absent quotes. This is the hallucination/prompt-injection gate — a fabricated "requirement" that is not verbatim-locatable on a real page returns `None`.
- **`build_source_ref(verbatim, chunk, threshold=92.0)`** — grounds against `chunk.text`, translates the matched offset into a page number by scanning `chunk.page_map`, and builds a `SourceRef` (page + char span + match kind + score + `verified=True` + chunk identity + `doc_role`). On a miss it returns a retained-but-flagged `SourceRef(verified=False, match="none", page=None, char_start=None, char_end=None)` still carrying `file_id`/`filename`/`section_label` and `doc_role` so the flag is traceable and INTK-03 amendment gating stays correct.

`rapidfuzz>=3.14.5` added as a runtime dependency.

## Tasks & Commits

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Package legitimacy gate — rapidfuzz (pre-approved) | (satisfied by orchestrator; install folded into task 2 RED commit) |
| 2 RED | Failing tests for `ground()` + add rapidfuzz | `6bd0e03` |
| 2 GREEN | `ground()` implementation | `80cf5cd` |
| 3 RED | Failing tests for `build_source_ref()` | `49b9ddc` |
| 3 GREEN | `build_source_ref()` implementation | `1fe6d81` |

## Package Legitimacy Gate (Task 1)

The plan's Task 1 is a `checkpoint:human-verify gate="blocking-human"` for `rapidfuzz` (tagged `[ASSUMED]` in the RESEARCH Package Legitimacy Audit). **The orchestrator pre-approved this gate** (recorded 2026-07-24): rapidfuzz on pypi.org/project/rapidfuzz is the canonical MIT-licensed C++-backed fuzzy-matching library (repo github.com/rapidfuzz/RapidFuzz, docs rapidfuzz.github.io/RapidFuzz, tens of millions of downloads/month — not a typosquat), version 3.14.5 published. `uv add rapidfuzz` proceeded under that approval; the executor did not pause for human input.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fuzzy span offsets: use `dest_start`/`dest_end`, not `src_start`/`src_end`**
- **Found during:** Task 2
- **Issue:** The RESEARCH Pattern 5 snippet (and the plan's `<interfaces>` note) returns `ali.src_start`/`ali.src_end` from `fuzz.partial_ratio_alignment(query, haystack)`. Verified against installed rapidfuzz 3.14.5: `src_*` indexes the **query** (first arg) while `dest_*` indexes the **haystack** (second arg, the page text), and rapidfuzz does not swap these by length. Using `src_*` would locate the span in the wrong string, producing a garbage offset that then maps to a wrong (or no) page via `page_map` — silently corrupting the load-bearing EXTR-02 page reference.
- **Fix:** `ground()` returns `ali.dest_start`/`ali.dest_end` (offsets into the normalized page text). Confirmed by direct API inspection with both query<haystack and query>haystack cases.
- **Files modified:** `src/rfp_analyzer/pipeline/grounding/verify.py`
- **Commit:** `80cf5cd`

## Verification

- `uv run python -m pytest tests/unit/test_grounding.py -q` → **12 passed** (exact, ligature/hyphenation, fuzzy, absent, empty for `ground`; multi-page page-map selection, identity copy, ungroundable-flag, doc_role on both paths, and the page-only-from-map invariant for `build_source_ref`).
- `uv run python -m pytest tests/unit/ -q` → **182 passed, 1 skipped** (no regressions).
- `uv run ruff check src/rfp_analyzer/pipeline/grounding/verify.py tests/unit/test_grounding.py` → clean.
- `uv lock --check` → resolved, rapidfuzz pinned.
- `grep -q "partial_ratio_alignment" verify.py` and `grep -q "rapidfuzz" pyproject.toml` → both present.

## Threat Model Coverage

- **T-02-03 (hallucinated provenance)** and **T-02-04 (prompt-injected requirement)** — mitigated: `build_source_ref` grounds every verbatim against real page text; anything not verbatim-locatable → `verified=False`/`page=None`, never emitted with an invented page.
- **T-02-SC (rapidfuzz supply chain)** — mitigated: blocking-human legitimacy gate (pre-approved by orchestrator on pypi.org provenance) before install.

## No Known Stubs

All returned `SourceRef` values are fully computed from real inputs; no placeholder/empty-data paths. The `threshold` default (92.0) is deliberately a tunable module constant (`DEFAULT_THRESHOLD`) for the later eval harness, per RESEARCH A2 — not a stub.

## Self-Check: PASSED

- Files: `src/rfp_analyzer/pipeline/grounding/verify.py`, `tests/unit/test_grounding.py`, `.planning/phases/02-requirement-extraction-grounding/02-02-SUMMARY.md` — all present.
- Commits: `6bd0e03`, `80cf5cd`, `49b9ddc`, `1fe6d81` — all present in git log.
