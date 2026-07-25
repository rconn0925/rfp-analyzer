---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 03 blocked on a cross-mapping design decision (03-01, 03-02 done)
last_updated: "2026-07-24T00:00:00.000Z"
last_activity: 2026-07-24 -- 03-02 surfaced a blocking L<->M cross-mapping finding
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 13
  completed_plans: 15
  percent: 45
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-22)

**Core value:** Upload a real federal RFP and get back an accurate, fully populated compliance matrix with no manual shredding.
**Current focus:** Phase 03 — blocked on the L<->M cross-mapping approach

## Current Position

Phase: 03 (analysis-export) — BLOCKED on a design decision
Plan: 2 of 6 (03-01 schema, 03-02 cross-mapping)
Status: 03-03..03-06 held pending Ross's call on cross-mapping (see Blockers)
Last activity: 2026-07-24 -- 02-07 shipped the eval harness + Claude Code engine seam

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 6
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 6 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P06 | 45min | 4 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Inside-out build order — pure pipeline library validated via CLI + evals (Phases 1-3) before any web code (Phases 4-5)
- [Roadmap]: 5 coarse phases reconciled from research's 7 — Analysis+Export merged (both consume the extracted set); Demo/Hardening+SAM.gov merged (both gate/extend the public app)
- [Research]: Python/FastAPI + pdfplumber (MIT, no AGPL PyMuPDF) + Claude Sonnet 5; Postgres-backed job queue, Cloudflare R2 files, Railway deploy (web + worker + Postgres)
- [Research]: Verbatim-quote verification and stable requirement IDs must land in the *first* extraction implementation (Phase 2) — retrofitting is a rewrite
- [Phase 01]: Commercial-form packages with role-title-only section nodes classify non_ucf_commercial — only UCF letter sections trigger the Open Question 1 partial_ucf rule (corpus evidence from non-ucf-part12)
- [Phase 01]: primary-ucf ground truth corrected full_ucf -> partial_ucf: base solicitation verified as a genuine SF1449 carrying a complete UCF A-M structure; partial_ucf with a verify-package-format warning is the honest classification
- [Phase 01]: SF30 Block 2 amendment numbers are AcroForm field values invisible to the text layer — amendment_number=None is the honest Phase 1 outcome; Phase 2 candidate: read AcroForm fields

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: RESOLVED — the engine is Claude Code on Ross's subscription, reached through a file-mediated replay seam (chunks.jsonl -> Claude -> drafts.jsonl -> extract). Ollama/Qwen fully retired: no dependency, no client, no network call anywhere in the extraction stage. Grounding remains string-match verification against the Phase 1 document map.
- [Phase 2]: RESOLVED — golden set built (02-04) and scored (02-07): recall 0.971, precision 0.426 (in scope), 277/277 grounded. See tests/eval/EVAL.md.
- [Phase 3]: NEW — the golden set is a validated SAMPLE, not an exhaustive shred of its pages, so precision is a lower bound and not an error rate. Making it exhaustive over a defined page range is the highest-value eval improvement.
- [Phase 3]: **BLOCKING** — L<->M cross-mapping by text similarity does not work on the primary package and is not a tuning problem. Section L DELEGATES its content to Section M ("responses to each non-price factor as specified in Section M"), so M carries the real submittal instructions (topic coverage: phase-in L=0/M=3, safety L=0/M=15, experience L=0/M=5). Similarity reports those as m_without_l gaps, which is wrong. No stable threshold exists (45.0 maps 95%, 55.0 maps 22%, 65.0 maps 4%). Fix = anchor on the evaluation FACTOR, which needs (a) sub-section structure carried onto Requirement (section_label is L/M/C only today) and (b) a req_type rule splitting M's submittal subsections from its evaluation criteria — both reach back into Phase 1/2. NEEDS A SCOPE DECISION.
- [Phase 3]: NEW — parser defect: the Section C Annexes two-column spec table injects the TITLE column mid-sentence ("authorizations to Licenses perform work"). Corrupts exported requirement text even when grounding succeeds. Needs column-aware annex extraction + running-header suppression.

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Scope | SAM.gov API key request (~10 business day issuance) | Deferred by user 2026-07-24 — upload is the intake path; key only gates the optional Phase 5 SAM.gov fetch | Phase 1 |
| Scope | SAM.gov fetch feature + rate-limit confirmation (10/day vs 1,000/day by role) | Deferred with the key — Phase 5 ships demo + hardening on upload intake alone; SAM.gov fetch becomes an optional add-on if/when a key exists | Phase 1 |

## Session Continuity

Last session: 2026-07-24T05:50:56.825Z
Stopped at: Phase 2 context gathered
Resume file: .planning/phases/02-requirement-extraction-grounding/02-CONTEXT.md
