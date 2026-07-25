---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: milestone-complete
stopped_at: v1.0 milestone complete — Phases 1-5 delivered
last_updated: "2026-07-24T00:00:00.000Z"
last_activity: 2026-07-25 -- exhaustive scope L+M audited honestly: precision 0.950, recall 0.864
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 19
  completed_plans: 19
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-22)

**Core value:** Upload a real federal RFP and get back an accurate, fully populated compliance matrix with no manual shredding.
**Current focus:** v1.0 delivered and the three follow-up quality items are done.
Measured: precision 0.950 / recall 0.864 / F1 0.905 across the 16 exhaustively
annotated pages (Section L p49-51 + Section M p58-70, 154 ground-truth rows);
277 requirements, 277 grounded. All 7 false positives are named in EVAL.md.

Recall is 0.864 because page 62 (Factor 1 Basis of Evaluation) was found to have
been missed ENTIRELY — 19 requirements, zero predictions, and zero golden rows,
so it had been invisible on both sides of the ratio and recall read 0.985. Those
19 rows were shredded independently (pass D) and are the only ground truth here
not derived from extraction output. Extracting page 62 is a concrete, bounded
coverage fix.

Next best work, in order:
1. A SECOND READER for the exhaustive scope. Ground truth and extractor share an
   author, so 0.950 measures self-consistency of judgment. No further self-audit
   improves this — it needs someone else's eyes.
2. Extract page 62's Factor 1 evaluation sub-criteria — a known, bounded gap
   worth ~12 points of in-scope recall.
3. Extend the exhaustive scope to the SOW annex (annex p9-16), still
   sample-annotated. VERIFY each declared page was actually read: a page with no
   golden rows and no predictions looks identical to an empty one, which is
   exactly how page 62 hid.
4. Extract the remaining 78 of 97 chunks so the matrix covers the whole 290-page
   package rather than the scoped sections.

## Current Position

Phase: ALL PHASES DELIVERED (1-5)
Plan: 6 of 6 in Phase 03; Phases 04-05 delivered as reframed
Status: v1.0 complete. `rfp-analyzer run <pkg>` produces a compliance workbook;
`showcase` renders the portfolio page. Open items are quality improvements, not gaps.
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
- [Phase 3]: RESOLVED (fe6939c) — golden set now declares an exhaustive_scope (Section L p49-51, pass-C audit); precision inside it is a true error rate of 0.860. Outside it precision remains a labelled lower bound. Remaining: widen the scope, and get a second reader for independence.
- [Phase 3]: RESOLVED (actor typing ab63d8b + factor anchoring a6f1199) — was: L<->M cross-mapping by text similarity did not work on the primary package and is not a tuning problem. Section L DELEGATES its content to Section M ("responses to each non-price factor as specified in Section M"), so M carries the real submittal instructions (topic coverage: phase-in L=0/M=3, safety L=0/M=15, experience L=0/M=5). Similarity reports those as m_without_l gaps, which is wrong. No stable threshold exists (45.0 maps 95%, 55.0 maps 22%, 65.0 maps 4%). Fix = anchor on the evaluation FACTOR, which needs (a) sub-section structure carried onto Requirement (section_label is L/M/C only today) and (b) a req_type rule splitting M's submittal subsections from its evaluation criteria — both reach back into Phase 1/2. FIXED by typing requirements by ACTOR (offeror vs Government) instead of by section, plus dedup keeping the deepest section path. 29 M rows reclassified. REMAINING (advisory-only until fixed): no per-factor anchor, so structurally similar sentences about different factors still link; needs sub-section structure below M.2 that the Phase 1 sectioner does not emit. Award-process statements also land in m_without_l when they are not gaps.
- [Phase 3]: RESOLVED (b4e1233) — the annex two-column spec table defect and the multi-regime running-header failure are both fixed (parsing/columns.py + absolute repetition floor).

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Scope | Phases 4-5 reframed 2026-07-24: local tool + static showcase, no hosted app (subscription cannot be used by a hosted service) | Decided by Ross | Phase 3 |
| Scope | SAM.gov API key request (~10 business day issuance) | Deferred by user 2026-07-24 — upload is the intake path; key only gates the optional Phase 5 SAM.gov fetch | Phase 1 |
| Scope | SAM.gov fetch feature + rate-limit confirmation (10/day vs 1,000/day by role) | Deferred with the key — Phase 5 ships demo + hardening on upload intake alone; SAM.gov fetch becomes an optional add-on if/when a key exists | Phase 1 |

## Session Continuity

Last session: 2026-07-24T05:50:56.825Z
Stopped at: Phase 2 context gathered
Resume file: .planning/phases/02-requirement-extraction-grounding/02-CONTEXT.md
