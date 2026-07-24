---
phase: 01-parsing-structure-foundation
plan: 05
subsystem: pipeline
tags: [ucf, sectioning, regex, sf30, sf33, sf1449, far-12.603, classification, pydantic]

# Dependency graph
requires:
  - phase: 01-parsing-structure-foundation (plan 01)
    provides: DocumentMap/ParsedFile/SectionNode/PageSpan/BlockSpan Pydantic schema
  - phase: 01-parsing-structure-foundation (plan 03)
    provides: PDF/DOCX parsers, first_page_layout_text capture
  - phase: 01-parsing-structure-foundation (plan 04)
    provides: apply_quality (cleaned page text, non-ok pages emptied)
provides:
  - sectioning package - SECTION/PART/PARA_NUMBER regexes, FAR 15.204-1 role-title table, find_heading_candidates
  - build_section_tree with TOC disambiguation (PageSpan for PDF, BlockSpan for DOCX) + find_toc_pages
  - classify package - SF33/SF1449/SF30 form signatures, FAR 12.603 combined-synopsis markers, SF30 amendment ladder
  - classify_package four-way honest classification (full_ucf/partial_ucf/non_ucf_commercial/unknown) with evidence + warnings
affects: [01-06 CLI + corpus validation, phase-02 extraction chunking]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Signal-priority per line: SECTION heading > PART heading > paragraph numbering > role title"
    - "A7 start rule: leading-line, non-TOC, prefer last occurrence preceding a subsequent distinct heading"
    - "Detection ladder: form-text evidence always beats filename evidence; filename matches explicitly unverified"
    - "Classification never silent: evidence always populated, non-full_ucf always warns"

key-files:
  created:
    - src/rfp_analyzer/pipeline/sectioning/__init__.py
    - src/rfp_analyzer/pipeline/sectioning/headings.py
    - src/rfp_analyzer/pipeline/sectioning/tree.py
    - src/rfp_analyzer/pipeline/classify/__init__.py
    - src/rfp_analyzer/pipeline/classify/forms.py
    - src/rfp_analyzer/pipeline/classify/package.py
    - tests/unit/test_headings.py
    - tests/unit/test_tree.py
    - tests/unit/test_forms.py
    - tests/unit/test_package_classify.py
  modified: []

key-decisions:
  - "TOC page indices exposed via exported find_toc_pages() rather than a second return value from build_section_tree (keeps the list[SectionNode] interface clean for the pipeline)"
  - "Letter nodes get CANONICAL_LETTER_ROLES fallback (FAR 15.204-1) when heading title text carries no role title"
  - "FAR 12.603 combined-synopsis files labeled base_solicitation in ladder rung 3 (the notice IS the solicitation)"
  - "Commercial signal caps classification at partial_ucf whenever any UCF structure is detected (Open Question 1 encoded)"

patterns-established:
  - "TOC disambiguation: >=4 distinct section letters OR majority (of 2+) dot-leader/trailing-page-number heading lines"
  - "All regexes line-anchored with bounded quantifiers; adversarial timing test enforces sub-second matching (T-01-12)"

requirements-completed: [PARS-02]

# Metrics
duration: 13min
completed: 2026-07-24
---

# Phase 1 Plan 05: UCF Sectioning & Package Classification Summary

**UCF section-boundary detection with TOC disambiguation (PageSpan/BlockSpan trees), SF33/SF1449/SF30 form signatures with the SF30 amendment ladder, and articulate four-way package classification — 43 new unit tests, all synthetic/CI-safe**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-07-24T00:44:25Z
- **Completed:** 2026-07-24T00:57:30Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 10 created

## Accomplishments

- Heading signal layer: SECTION/PART/PARA_NUMBER regexes (line-anchored, dash/colon/case tolerant, bounded quantifiers per T-01-12) plus the FAR 15.204-1 role-title table — "Proposal Submission Instructions" attachments get the instructions role with no "SECTION L" literal (Pitfall 3)
- Section tree builder with the Pitfall 1 regression killed: a page-1 TOC listing SECTION A–M never seeds section starts; L lands on its real page (asserted page 40 vs page 1); DOCX gets BlockSpan locators with style-independent text heuristics (Pitfall 4)
- SF30 detection ladder: form-text rung extracts the Block 2 amendment number (accepts None); scanned SF30s fall back to filename matching explicitly marked `amendment_evidence: "filename"` — never a silent plain attachment (Pitfall 5, T-01-13)
- classify_package: full_ucf/partial_ucf/non_ucf_commercial/unknown with evidence always populated and every non-full outcome warned (T-01-14); SF1449 + detected L/M → partial_ucf (Open Question 1)

## Task Commits

Each task was committed atomically (TDD: test commit then feat commit):

1. **Task 1: Heading regexes, role titles, candidate detection** - `a5b6e06` (test), `f0b600f` (feat)
2. **Task 2: TOC disambiguation and section tree builder** - `ec75ec0` (test), `667bc94` (feat)
3. **Task 3: Form signatures, SF30 ladder, package classification** - `0b349b9` (test), `f2dde1f` (feat)

## Files Created/Modified

- `src/rfp_analyzer/pipeline/sectioning/headings.py` - SECTION_HEADING/PART_HEADING/PARA_NUMBER regexes, normalize_line, ROLE_TITLES, find_heading_candidates (A5 assumption tagged)
- `src/rfp_analyzer/pipeline/sectioning/tree.py` - TOC_MIN_DISTINCT_HEADINGS, find_toc_pages, build_section_tree with A7 start rule and PageSpan/BlockSpan emission
- `src/rfp_analyzer/pipeline/classify/forms.py` - FORM_SIGNATURES (both SF1449 title variants), COMBINED_SYNOPSIS_MARKERS, AMENDMENT_FILENAME_RE, detect_form, detect_combined_synopsis, assign_doc_role
- `src/rfp_analyzer/pipeline/classify/package.py` - classify_package returning (classification, evidence, warnings)
- `src/rfp_analyzer/pipeline/sectioning/__init__.py`, `src/rfp_analyzer/pipeline/classify/__init__.py` - stage exports
- `tests/unit/test_headings.py` (14 tests), `tests/unit/test_tree.py` (6), `tests/unit/test_forms.py` (24), `tests/unit/test_package_classify.py` (9)

## Decisions Made

- `build_section_tree` keeps the `list[SectionNode]` return; TOC pages surface through separately exported `find_toc_pages()` (the plan allowed either shape; this keeps the Phase-2-facing interface clean while the 01-06 report layer can still say "TOC on page 1")
- Letter nodes receive a canonical FAR 15.204-1 role fallback (`CANONICAL_LETTER_ROLES`) when the heading's own title carries no role text — a Section L titled unusually still classifies as instructions
- Role-title nodes are emitted as top level only when a file has zero letter sections, preventing duplicate L/instructions nodes in full-UCF base documents while catching role-only attachments

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Combined-synopsis files labeled base_solicitation, not attachment**
- **Found during:** Task 3 (assign_doc_role ladder rung 3)
- **Issue:** Plan rung 3 specified base_solicitation only for SF33/SF1449 matches; a FAR 12.603 combined synopsis uses no form, so its main document would have been mislabeled "attachment" — dishonest labeling for the package's actual solicitation document
- **Fix:** Rung 3 also assigns base_solicitation when `detect_combined_synopsis` matches (the notice text IS the solicitation per FAR 12.603)
- **Files modified:** src/rfp_analyzer/pipeline/classify/forms.py
- **Verification:** test_combined_synopsis_markers_detected + non-UCF classification tests pass
- **Committed in:** f2dde1f (Task 3 commit)

**2. [Rule 1 - Bug] TOC majority-dot-leader rule requires >= 2 heading lines**
- **Found during:** Task 2 (TOC detection implementation)
- **Issue:** The plan's "majority of heading lines end in page-number/dot-leader" rule is degenerate at one heading line — a single real section heading with an incidental trailing digit would nuke that section's start page
- **Fix:** Majority rule only applies when a page has >= 2 section-letter heading candidates (documented tunable behavior; the >= 4-distinct-letters rule is unchanged)
- **Files modified:** src/rfp_analyzer/pipeline/sectioning/tree.py
- **Verification:** Both TOC tests pass; single-heading real section pages never classified TOC
- **Committed in:** 667bc94 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both fixes tighten honesty/correctness of the heuristics; no scope creep.

## Issues Encountered

- Task 3 acceptance criterion "grep COMMERCIAL ITEMS >= 1 in test file" initially unmet because the older-variant detection test used lowercase input (deliberately, to prove case tolerance); added an explicit FORM_SIGNATURES table test asserting both uppercase SF1449 title literals.
- Task 3 acceptance "commit + push, CI green" — push is orchestrator-owned in this parallel worktree execution (branch `worktree-agent-*` has no remote); CI runs on the orchestrator's merge/push. Local equivalent verified: `ruff check`, `ruff format --check`, and full unit suite all green.

## Known Stubs

None — all exported functions are fully implemented; no placeholder values, TODOs, or unwired data paths.

## Threat Flags

None — no security-relevant surface beyond the plan's threat model (T-01-12 regex DoS mitigated via bounded anchored patterns + timing test; T-01-13 filename spoofing mitigated via ladder ordering + explicit unverified evidence; T-01-14 mitigated via always-articulate classification).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 01-06 (CLI + corpus validation) can now wire: parse → apply_quality → build_section_tree → assign_doc_role → classify_package → DocumentMap, and render TOC/warnings/evidence in the report
- All heuristic constants (TOC_MIN_DISTINCT_HEADINGS, LEADING_LINE_LIMIT, regex forms) are named and corpus-tunable per A5/A7 — 01-06's real-corpus run is the falsification pass
- Full unit suite: 100 passed, 1 skipped (corpus-dependent), CI-safe

## Self-Check: PASSED

- All 10 created files verified present on disk
- All 6 task commits verified in git log (a5b6e06, f0b600f, ec75ec0, 667bc94, 0b349b9, f2dde1f); SUMMARY committed separately
- Working tree clean; no untracked files left behind
- Full unit suite: 100 passed, 1 skipped; ruff check + format clean

---
*Phase: 01-parsing-structure-foundation*
*Completed: 2026-07-24*
