# Requirements: RFP Analyzer — Federal Compliance Matrix Generator

**Defined:** 2026-07-22
**Core Value:** Upload a real federal RFP and get back an accurate, fully populated compliance matrix with no manual shredding.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Intake

- [ ] **INTK-01**: User can upload a multi-file federal RFP package (PDF and DOCX: base solicitation, SF30 amendments, attachments) via the web UI
- [ ] **INTK-02**: User can fetch a solicitation package (notice + attachments) from SAM.gov by pasting a solicitation number or link
- [ ] **INTK-03**: System detects SF30 amendments in the package, extracts their requirements, and flags potentially modified rows (no silent merging)

### Parsing & Structure

- [x] **PARS-01**: System parses hostile real-world federal PDFs (tables, multi-column, SF forms) into text with a structural document map (section hierarchy + page numbers)
- [x] **PARS-02**: System detects UCF section boundaries (L, M, C/SOW/PWS, H, etc.) and degrades honestly when a package doesn't follow clean UCF structure (e.g., FAR Part 12 combined synopsis)

### Extraction

- [ ] **EXTR-01**: System extracts every requirement (shall/must/will/should statements, Section L instructions, Section M evaluation criteria) as verbatim text with a stable requirement ID
- [ ] **EXTR-02**: Every extracted requirement carries a computed source reference (document, section/paragraph, page) verified by string-match against the source — never LLM-generated citations
- [ ] **EXTR-03**: System classifies each requirement by type (L instruction / M criterion / C-SOW shall / clause / attachment requirement) and binding keyword
- [ ] **EXTR-04**: System scans attachments (PWS, QASP, CDRLs) and Sections C/H for requirements outside L/M
- [ ] **EXTR-05**: A deterministic shall/must/will/should keyword sweep reconciles against AI extraction and surfaces any missed candidate requirements

### Analysis

- [ ] **ANLZ-01**: System cross-maps Section L ↔ Section M ↔ Section C/SOW requirements and flags gaps and orphans (L-without-M, M-without-L, SOW-without-either)
- [ ] **ANLZ-02**: System derives a proposal outline (volumes/sections) from Section L structure and maps every requirement to an outline node
- [ ] **ANLZ-03**: User can author a company capabilities profile by pasting free text (capability statement, past performance) and edit it later
- [ ] **ANLZ-04**: System judges compliance per requirement (Fully/Partially/Non-comply + rationale + confidence) against the stored capabilities profile

### Export

- [ ] **EXPT-01**: User can download a formatted .xlsx with a compliance matrix sheet matching the practitioner-standard columns (ID, source ref, verbatim text, type, keyword, proposal section, F/P/N, cross-refs, empty owner/status/notes)
- [ ] **EXPT-02**: Export includes a cross-reference matrix sheet (proposal-outline-ordered with L/M/C refs per section)
- [ ] **EXPT-03**: Export includes a shred checklist sheet (sentence-level with binding-keyword highlighting)
- [ ] **EXPT-04**: User can download the compliance matrix as raw CSV

### Pipeline & Web App

- [ ] **PIPE-01**: Full pipeline runs automated end-to-end (upload → parse → extract → analyze → matrix → download) with no manual steps
- [ ] **PIPE-02**: Long-running analysis executes as an async background job with stage-level progress visible in the UI
- [ ] **PIPE-03**: A processed analysis persists — user can return to view results and re-download exports without re-running the pipeline

### Demo & Hosting

- [ ] **DEMO-01**: App is publicly hosted at a stable URL
- [ ] **DEMO-02**: Demo mode serves a precomputed sample RFP analysis + fictional company profile with zero live LLM calls, experiencable in ~60 seconds
- [ ] **DEMO-03**: Live (non-demo) processing is protected by rate limiting and a spend kill-switch to bound public API cost

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Trust & Review

- **TRST-01**: Per-row extraction confidence surfaced in the UI with "needs human review" flags
- **TRST-02**: Attachment-requirement coverage report ("N requirements found outside Sections L/M")
- **TRST-03**: Matrix review/edit UI (only if automated accuracy proves insufficient)

### Amendments

- **AMND-01**: Requirement-level amendment (SF30) diffing with change flags across versions

### Product

- **PROD-01**: Multi-user accounts, teams, billing
- **PROD-02**: Response drafting per requirement

## Out of Scope

| Feature | Reason |
|---------|--------|
| Proposal text drafting/generation | Crowded space, massive scope, highest hallucination stakes; matrix rows carry enough context to feed drafting later |
| Capture/pipeline management (opportunity discovery, bid/no-bid, CRM) | Different product; SAM.gov fetch is analysis of a *known* solicitation only |
| Content library / past-performance reuse | Requires corpus ingestion + retrieval quality work; capabilities profile is the minimal stand-in |
| Non-federal formats (state/local, commercial, grants) | Non-FAR formats are unstandardized; wrecks parsing accuracy — federal UCF only, stated in UI |
| FedRAMP / CMMC / SOC 2 posture | Enterprise-sales requirement, unattainable solo; demo uses fictional data + README security note |
| Word add-in / Office integration | Separate platform build; only matters once drafting exists |
| Auto-merging amendment changes | No reliable automated SF30 merge pattern exists; v1 detects + flags instead |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTK-01 | Phase 4 | Pending |
| INTK-02 | Phase 5 | Pending |
| INTK-03 | Phase 2 | Pending |
| PARS-01 | Phase 1 | Complete |
| PARS-02 | Phase 1 | Complete |
| EXTR-01 | Phase 2 | Pending |
| EXTR-02 | Phase 2 | Pending |
| EXTR-03 | Phase 2 | Pending |
| EXTR-04 | Phase 2 | Pending |
| EXTR-05 | Phase 2 | Pending |
| ANLZ-01 | Phase 3 | Pending |
| ANLZ-02 | Phase 3 | Pending |
| ANLZ-03 | Phase 4 | Pending |
| ANLZ-04 | Phase 3 | Pending |
| EXPT-01 | Phase 3 | Pending |
| EXPT-02 | Phase 3 | Pending |
| EXPT-03 | Phase 3 | Pending |
| EXPT-04 | Phase 3 | Pending |
| PIPE-01 | Phase 4 | Pending |
| PIPE-02 | Phase 4 | Pending |
| PIPE-03 | Phase 4 | Pending |
| DEMO-01 | Phase 5 | Pending |
| DEMO-02 | Phase 5 | Pending |
| DEMO-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-22*
*Last updated: 2026-07-22 after roadmap creation (traceability mapped)*
