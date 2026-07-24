# RFP Analyzer — Federal Compliance Matrix Generator

## What This Is

A hosted web app that ingests a federal government RFP/solicitation package (uploaded files or fetched from SAM.gov) and automatically produces a fully populated compliance matrix — every requirement extracted with section references, cross-mapped across Sections L, M, and C/SOW/PWS, mapped to a proposal outline, and judged for compliance against a company capabilities profile — exportable to Excel/CSV.

It serves Ross's own business first, doubles as a portfolio showcase for the job hunt (AI/dev employers and the GovCon industry), and is built on a foundation that can become a sellable product.

## Core Value

Upload a real federal RFP and get back an accurate, fully populated compliance matrix with no manual shredding — if the extraction and matrix are wrong or incomplete, nothing else matters.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] User can upload a federal RFP package (PDF/Word, including amendments and attachments) via the web UI
- [ ] User can fetch a solicitation package from SAM.gov by solicitation number/link
- [ ] System extracts every requirement (shall/must/will statements, instructions, evaluation criteria) with requirement ID, section reference, and type
- [ ] System cross-maps Section L ↔ Section M ↔ Section C/SOW/PWS and flags gaps and orphans
- [ ] System maps each requirement to a proposal volume/section per the Section L structure
- [ ] System judges compliance per requirement against a stored company capabilities profile
- [ ] User can export the populated matrix to Excel/CSV
- [ ] App is publicly hosted with a demo mode: preloaded sample RFP + fictional company profile, tryable in ~60 seconds
- [ ] Full pipeline is automated: upload → processing → populated matrix → download, no manual steps required

### Out of Scope

- Manual review/edit workflow as a v1 requirement — the vision is "fully automated"; an editing UI can come later if accuracy demands it
- Proposal response drafting (writing response text per requirement) — extraction and compliance analysis first; drafting is a future differentiator
- Non-federal solicitations (state/local, commercial, grants/NOFOs) — federal FAR-based structure (Sections L/M/C) is the parsing target; other formats are less standardized and dilute v1
- Multi-user accounts / teams / billing — sellable-product features deferred until after the showcase v1 proves the pipeline

## Context

- Ross runs his own business and is on a dual-track job hunt (dev + sales roles); this project is a skills showcase aimed at AI/dev employers and the GovCon industry, so demo polish, a clean public repo, and a live URL matter as much as the tool's utility.
- Not actively bidding federal RFPs today — the tool is built ahead of real bid flow, so the demo-mode sample RFP is the primary proving ground, with at least one real federal RFP run end-to-end.
- Federal RFP packages are typically PDFs (sometimes Word), often split across a base solicitation, amendments (SF30), and attachments — the parser must handle multi-file packages.
- Compliance judgment requires a company capabilities profile; demo mode ships with a fictional company profile. How real profiles are authored/stored is a design decision for planning.
- Public hosting with an AI pipeline has cost exposure — demo mode may need cached/precomputed results or rate limiting to keep a public URL affordable.

## Constraints

- **Hosting**: Must run on a public URL with a low-friction demo — showcase value depends on a recruiter being able to try it in under a minute
- **Domain**: Federal FAR-based solicitations only for v1 — parsing logic targets Section L/M/C (and SOW/PWS) structure
- **Output**: Excel/CSV is the required deliverable format — proposal teams live in spreadsheets
- **Stack**: To be recommended by research — no pre-committed stack

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Web app from day 1 (not CLI-first) | Sellable foundation and hosted showcase are core goals | — Pending |
| Fully automated pipeline (no human-in-the-loop for v1) | The wow-factor and product thesis is upload → finished matrix | — Pending |
| Federal-only parsing for v1 | FAR structure (L/M/C) is standardized enough to parse reliably; other RFP types dilute focus | — Pending |
| Hosted demo mode with sample RFP + fictional company profile | Job-hunt audience must experience the product in ~60 seconds without owning an RFP | — Pending |
| Upload for v1 intake, SAM.gov fetch also in scope | Upload is the reliable baseline; SAM.gov fetch is a strong differentiator worth including | — SAM.gov fetch + API key DEFERRED (2026-07-24); upload is the intake path, fetch is an optional Phase 5 add-on |
| UCF structure is decisive over the cover form (2026-07-24) | A complete UCF A–M structure classifies full_ucf even under an SF1449/combined-synopsis cover, because compliance extraction keys off Sections A–M, not the cover form. Reverses the earlier Phase 1 "Open Question 1" default that treated the commercial-form signal as decisive | — Applied in Phase 1 (classify/package.py); primary golden-set package = full_ucf |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-22 after initialization*
