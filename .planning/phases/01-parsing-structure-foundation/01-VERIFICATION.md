---
phase: 01-parsing-structure-foundation
verified: 2026-07-24T04:38:32Z
status: human_needed
score: 28/28 must-haves verified
overrides_applied: 1
overrides:
  - must_have: "The SAM.gov API key request has been surfaced to Ross as a personal action item"
    reason: "DEFERRED by explicit user decision 2026-07-24. Upload / local-package intake is the product's intake path; the key only gates Phase 5's optional SAM.gov fetch. No phase is blocked. Recorded in ROADMAP.md Phase 1 note, STATE.md Deferred Items, and 01-HUMAN-UAT.md item 1."
    accepted_by: "ross"
    accepted_at: "2026-07-24T00:00:00Z"
re_verification:
  previous_status: none
  previous_score: n/a
human_verification:
  - test: "Confirm partial_ucf is the right call for the primary corpus package (Phase 2 golden set)"
    expected: "The base solicitation `Solicitation - N4008526R0033.pdf` is an SF1449 (\"SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES\") that nonetheless carries a complete UCF A-M structure. Per Open Question 1 the commercial-form signal alongside UCF letter sections yields `partial_ucf` + a \"verify package format\" warning. Confirm this hybrid handling is the product behaviour you want, since this package becomes Phase 2's hand-shredded golden set."
    why_human: "Product judgment about classification semantics, not a checkable code property. Both classifications are internally consistent; only Ross can decide which is the honest answer for a hybrid SF1449/UCF package."
  - test: "Decide whether section-heading false positives must be fixed before Phase 2 golden-set shredding"
    expected: "`N4008526R0033 Section C Annexes.pdf` emits two spurious top-level sections — `SECTION F` (pages 110-125) from the body line `Section F.` and `SECTION H - OR ON A MEASURED FROM ISSUE DATE OF` (pages 126-161) from the body prose `Section H or on a measured from issue date of`. `hostile-scanned/...Specifications.pdf` emits `SPECIAL REQS - SPECIAL CONTRACT REQUIREMENTS` spanning pages 16-370. Decide: tighten `_is_cross_reference` / heading gating now, or accept the noise into Phase 2."
    why_human: "Requires a judgment call on precision-vs-recall tradeoff for Phase 2 extraction anchoring. No phase success criterion is violated (the base solicitation's own L/M/C/H boundaries are exactly right and the non-UCF package invents nothing), so this is a scope decision, not a defect gate."
---

# Phase 1: Parsing & Structure Foundation — Verification Report

**Phase Goal:** Real federal RFP packages (multi-file PDF/DOCX) parse into an accurate, navigable document structure that everything downstream can trust
**Verified:** 2026-07-24T04:38:32Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

All four ROADMAP success criteria were verified by **running the real CLI against the real 3-package corpus** and, for the load-bearing claim (UCF boundary correctness), by an **independent pdfplumber read of the source PDF** rather than trusting the pipeline's own report or SUMMARY.md.

### Observable Truths

#### ROADMAP Success Criteria (the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | CLI on a multi-file package (PDFs + DOCX) produces a document map with section hierarchy + page numbers for every file | VERIFIED | Ran `rfp-analyzer parse` on all 3 corpus packages: primary-ucf 7 files/290 pages, non-ucf-part12 4 files/35 pages, hostile-scanned 3 files/408 pages. Each wrote a `document_map.json` that re-validates against `DocumentMap` (893 KB / 106 KB / 856 KB, `pending=0` pages in all three). DOCX leg exercised end-to-end by building a synthetic mixed package and running the CLI: `attachment.docx` produced `SECTION L blocks 1-2` + child `L.1 blocks 2-2` + `SECTION M blocks 3-4`; `legacy.doc` rejected with `.doc legacy Word not supported`. |
| SC2 | UCF boundaries correct on the primary package; non-UCF package flagged and never mis-sectioned | VERIFIED | **Independent check:** direct `pdfplumber` read of `Solicitation - N4008526R0033.pdf` shows p49 line 3 = `Section L - Instructions, Conditions, & Notices to Offerors or Quoters` and p58 line 3 = `Section M - Evaluation Factors for Award`. CLI reports `SECTION L pages 49-57`, `SECTION M pages 58-70` — exact match. `SECTION C pages 10-11`, `SECTION H pages 24-25` also emitted, plus A/B/D/E/F/G/I/J/K. Non-UCF: `non-ucf-part12` → `non_ucf_commercial`, 1 warning, **zero** L/M nodes (integration test `test_non_ucf_package_flagged_not_mis_sectioned` asserts no fabrication). |
| SC3 | Scanned/low-quality pages caught and surfaced as explicit range notes | VERIFIED | `hostile-scanned`: 59/408 pages flagged. Report renders contiguous ranges — `pages 1-36: gibberish text layer (broken font encoding)`, `pages 2-3: scanned image, no text layer`, `pages 300-304: very little text (partial scan…)`, `pages 359-370: gibberish…`. Manifest ground truth ("Specifications.pdf pages 2-3 … 36 raster images each") matches exactly. `non-ucf-part12` flagged 2 (p4 low_text, p9 gibberish). `apply_quality` empties flagged page text (`headers.py:124`), integration test asserts `page.text == ""` for every flagged page. |
| SC4 | SF30 amendment files identified and labeled | VERIFIED | All three SF30 files in `primary-ucf` labeled `[amendment]` via `form_text` evidence (SF30 title matched on page 1 — evidence lines present in the classification block). Ladder rung 2 (filename fallback) correctly did not fire; integration test asserts filename evidence is only ever used when page 1 has no usable text layer. |

#### Plan 01-01 — Scaffolding, schema, public repo + CI

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P01-1 | `uv sync` + `uv run pytest` succeed from a clean checkout | VERIFIED | `uv run python -m pytest tests/` → **134 passed, 1 skipped** in 112 s. Skip is `test_discover.py:144 symlink creation requires privileges on this platform` (Windows, legitimate). `ruff check .` → All checks passed; `ruff format --check .` → 34 files already formatted. |
| P01-2 | Repo public on GitHub under rconn0925 with CI running lint + format-check + unit tests on push | VERIFIED | `gh repo view` → `{"name":"rfp-analyzer","url":"https://github.com/rconn0925/rfp-analyzer","visibility":"PUBLIC"}`. Last 5 CI runs all `success`. **Log inspected** (run 30066972970): pytest step reports `collected 135 items` → `125 passed, 10 skipped` — proving the test step really executes and that the 10 integration tests auto-skip without the corpus. `ci.yml` runs `uv sync --locked --dev`, `ruff check`, `ruff format --check`, `pytest`. |
| P01-3 | DocumentMap schema round-trips through JSON and is importable as the Phase 2 contract | VERIFIED | `DocumentMap.model_validate_json()` succeeded on all 3 emitted corpus maps. `models.py` (124 lines) defines DocumentMap, ParsedFile, PageInfo, BlockInfo, SectionNode, PageSpan, BlockSpan and the discriminated `Locator` union; `schema_version="1.0"` present in all output. |
| P01-4 | Corpus binaries under `tests/corpus/` are invisible to git | VERIFIED | `git ls-files tests/corpus/` → only `MANIFEST.md` and `manifest.json`. `git check-ignore -v` on a corpus PDF → matched by `.gitignore:13 tests/corpus/*`. `git status --porcelain -uall` → empty despite 14 corpus binaries on disk. |

#### Plan 01-02 — 3-package corpus + MANIFEST

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P02-1 | Three real SAM.gov packages exist locally per D-01 | VERIFIED (with noted deviation) | `tests/corpus/{primary-ucf,hostile-scanned,non-ucf-part12}` present with 7/3/4 files. **Independent hash check: all 14 files' sha256 match manifest.json exactly.** Deviation: the "clean full-UCF" package is an SF1449 hybrid (classified `partial_ucf`) and the "FAR Part 12 combined synopsis" package is an SF1449 RFQ with no combined-synopsis marker. Both documented in MANIFEST.md; see WARNING W4. |
| P02-2 | Zero corpus binaries addable to git; only manifests tracked | VERIFIED | Same evidence as P01-4. |
| P02-3 | MANIFEST.md documents every package: notice link, solicitation number, file list with sha256, page counts, rationale | VERIFIED | 6,196-byte MANIFEST.md contains exactly **14 sha256 digests** (= 7+3+4 files), per-package SAM.gov notice URL, solicitation number, agency, title, selection rationale, and file tables with sizes + page counts. |
| P02-4 | SAM.gov API key request surfaced to Ross | PASSED (override) | Override: DEFERRED by explicit user decision 2026-07-24 — upload/local intake is the product path; key only gates Phase 5's optional fetch. Accepted by ross on 2026-07-24. Recorded in ROADMAP.md Phase 1 note and 01-HUMAN-UAT.md item 1. |

#### Plan 01-03 — Parsing layer

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P03-1 | Mixed directory yields one ParsedFile per file; `.doc`/unknown rejected explicitly, never a crash | VERIFIED | Synthetic mixed-package CLI run: `base.pdf` [base_solicitation, ok], `attachment.docx` [attachment, ok], `legacy.doc` [unknown, **rejected**] with `error: .doc legacy Word not supported — convert to .docx and re-upload`. Exit 0. `discover.py:182-187` implements the allowlist; `test_discover.py` (216 lines). |
| P03-2 | Malformed PDF → `parse_status="failed"` with error, run continues | VERIFIED | `pdf.py:71-80` wraps the whole parse in `except Exception` returning a failed ParsedFile. `discover.py` now guards every `stat()`/`open()`/`resolve()` with `OSError` handling (CR-01 fix confirmed in code at lines 54-65, 153-180). |
| P03-3 | PDF pages 1-indexed; DOCX blocks 0-indexed ordinals; no synthesized DOCX page numbers | VERIFIED | `pdf.py:59` `page_number=page.page_number  # 1-indexed`; `docx.py:88` `for i, item in enumerate(...)`. Mixed-package CLI output shows PDF locators as `pages N-M` and DOCX locators as `blocks 1-2` / `blocks 3-4` — never a page number for DOCX. |
| P03-4 | Stable identity: sha256 + file_id slug per file | VERIFIED | `discover.py:67-75` streaming sha256 + `{sha[:12]}-{stem}` file_id. `test_run.py:88-89` asserts filename and file_id uniqueness across nested same-basename files. Every corpus map carries sha256 per file. |

#### Plan 01-04 — Quality gates + header stripping

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P04-1 | Every PDF page gets a final status; `pending` never survives | VERIFIED | `headers.py:116-117` assigns `classify_page` to every page. Ran a `pending` census over all 3 emitted corpus `document_map.json` files: **pending=0** in all three (290 + 35 + 408 pages). |
| P04-2 | Scanned pages flagged, text emptied, excluded downstream; no OCR/Docling code | VERIFIED | `headers.py:122-124` sets `page.text = ""` for every non-ok page. `grep` for OCR/Docling in `src/` → zero hits. Integration test `test_scanned_pages_flagged_and_emptied` asserts emptiness on the real hostile package. |
| P04-3 | Running headers/footers stripped from stored text and recorded on the file | VERIFIED | Live check on `N4008526R0033 Section C Annexes.pdf`: `stripped_headers == ['SECTION C', '- FACILITY INVESTMENT']` and the stripped lines are absent from post-quality page text. Band-scoped removal confirmed at `headers.py:89-97` (WR-04 fix). See INFO note on sub-title stripping. |
| P04-4 | All thresholds are named module-level constants | VERIFIED | `gates.py:24-42` — `SCANNED_MAX_CHARS`, `LOW_TEXT_CHARS`, `GIBBERISH_ALPHA_RATIO`, `GIBBERISH_CID_RATIO`, `GIBBERISH_REPLACEMENT_MAX`, plus an injectable `QualityThresholds` dataclass. `headers.py:30-40` — `HEADER_FREQ_THRESHOLD`, `RUNNING_LINE_BAND`, `MIN_VOTING_PAGES`. Zero magic numbers in the logic paths. |

#### Plan 01-05 — Sectioning + classification

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P05-1 | Standard UCF solicitation yields L/M/C/H nodes with page ranges that do NOT all point at page 1 (TOC recognized) | VERIFIED | See SC2. Emitted ranges: C 10-11, H 24-25, L 49-57, M 58-70 — plus A 2-9, D 12, E 12-13, F 14, G 15-18, B 19-23, I 26-42, J 43-44, K 45-48. Second-level `L.1`-`L.6` and `M.1`-`M.2` children with their own page ranges. Integration test pins `page_start > 1` as the TOC guard. |
| P05-2 | SF30 files labeled `amendment` via form text, filename fallback marked unverified when scanned | VERIFIED | See SC4. `forms.py:154-183` implements the 3-rung ladder; `_page1_usable` (lines 100-113, WR-02 fix) makes a gibberish page-1 layer fall through to rung 2 rather than to `attachment`. CLI renders the fallback as `(unverified — scanned, matched by filename)` (`cli.py:102`). |
| P05-3 | FAR Part 12 / SF1449 package classifies `non_ucf_commercial` with evidence + warnings, never a fabricated UCF tree | VERIFIED | `non-ucf-part12` → `non_ucf_commercial`; evidence: `SF1449 title matched on Solicitation - FA441826Q0079.pdf page 1` plus 7 role-title lines; warning: "Non-UCF commercial package … matrix columns that depend on UCF sections will be incomplete." Zero L/M nodes anywhere in the package. |
| P05-4 | An attachment titled "Proposal Submission Instructions" with no "SECTION L" literal still gets the instructions role | VERIFIED | `headings.py:47-56` `ROLE_TITLES` includes `"PROPOSAL SUBMISSION INSTRUCTIONS": "instructions"`; `tree.py:218-238` emits role-title nodes as the honest top level when no letter sections exist. Behaviour demonstrated live on the real corpus: `non-ucf-part12` emits `SOW — STATEMENT OF WORK pages 1-4` and `EVALUATION — EVALUATION FACTORS FOR AWARD pages 15-15` from role titles alone. |

#### Plan 01-06 — CLI harness + corpus integration tests

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P06-1 | `rfp-analyzer parse <dir> --out <dir>` writes a validating `document_map.json` AND prints a section tree | VERIFIED | Both artifacts produced on every one of the 4 runs I performed (3 corpus + 1 synthetic mixed). Stdout carries classification + evidence, per-file roles, indented section tree with locators, quality range notes, warnings, and the metrics footer (`LLM cost: $0.00 (0 calls)`). |
| P06-2 | Primary package run shows L/M/C boundaries, quality flags, SF30 labeled — all four SCs observable in one report | VERIFIED | Single `primary-ucf` report contains: full A–M section hierarchy with real page ranges (SC1/SC2), 0 flagged pages for this clean package with the mechanism proven on the hostile package (SC3), three `[amendment]`-labelled SF30s (SC4). |
| P06-3 | Non-UCF package classified `non_ucf_commercial` with warnings, not silently mis-sectioned | VERIFIED | See SC2 / P05-3. |
| P06-4 | Integration tests encode these outcomes against manifest.json and auto-skip when the corpus is absent | VERIFIED | `tests/integration/test_corpus_packages.py` (139 lines) reads every expectation from `manifest.json` — no hardcoded solicitation numbers. Locally: 10 integration tests pass against the real corpus. In CI: `125 passed, 10 skipped` (log-verified), so CI stays green without binaries. |

**Score:** 28/28 truths verified (1 via override)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | uv project, locked deps, ruff config, script entry point | VERIFIED | 35 lines; pdfplumber/pydantic/python-docx pinned; `[project.scripts] rfp-analyzer = "rfp_analyzer.cli:main"`; ruff `select = ["E","F","I","UP","B","SIM"]`. |
| `src/rfp_analyzer/pipeline/models.py` | Phase 2 contract (min 80 lines) | VERIFIED | 124 lines; 8 models + discriminated `Locator` union; round-trips real 893 KB output. |
| `src/rfp_analyzer/pipeline/metrics.py` | RunMetrics with zeroed LLM fields | VERIFIED | 25 lines; `llm_calls`/`input_tokens`/`output_tokens`/`estimated_cost_usd` default 0; stage timings populated live (`parse: 79.39s` on the 408-page package). |
| `.github/workflows/ci.yml` | uv sync --locked, ruff check, format --check, pytest | VERIFIED | 18 lines, all 4 steps present, 5/5 recent runs green, pytest output log-verified. |
| `.gitignore` | corpus exclusion with manifest exceptions | VERIFIED | `tests/corpus/*` + `!MANIFEST.md` + `!manifest.json`; `git check-ignore` confirms. |
| `tests/corpus/MANIFEST.md` | human-readable corpus doc, contains sha256 | VERIFIED | 6,196 bytes, 14 sha256 digests, notice URLs + rationale. |
| `tests/corpus/manifest.json` | machine-readable metadata with `role` | VERIFIED | 4,173 bytes; `dir`/`role`/`expected_classification`/`has_amendment`/`has_scanned_pages`/`files[]`; consumed by integration conftest. |
| `parsing/discover.py` | `discover_files` — allowlist, rejections, size guard, containment | VERIFIED | 206 lines; exports `discover_files`; size cap before hashing (WR-01 fix at lines 153-174), `OSError` guards, `_is_within` containment. |
| `parsing/pdf.py` | `parse_pdf` — per-page text + metrics, `page.close()` | VERIFIED | 90 lines; `page.close()` at line 70; layout text captured for page 1 only. |
| `parsing/docx.py` | `parse_docx` — ordered blocks, zip-bomb guard | VERIFIED | 118 lines; `_bomb_check` with 1 GiB total + 200× ratio caps. |
| `quality/gates.py` | `compute_page_metrics` + `classify_page` | VERIFIED | 116 lines; both exported; O(n) single-pass, no regex. |
| `quality/headers.py` | frequency header detection + `apply_quality` | VERIFIED | 129 lines; exports `apply_quality`; writes `file.stripped_headers` (confirmed live). |
| `sectioning/headings.py` | regexes, role-title table, normalization, candidate scan | VERIFIED | 179 lines; exports `find_heading_candidates`, `normalize_line`; all patterns bounded (`.{0,120}`, `\d{1,4}`). |
| `sectioning/tree.py` | TOC disambiguation + `build_section_tree` | VERIFIED | 316 lines; exports `build_section_tree`; TOC page detection, cross-reference filter, PageSpan/BlockSpan branches. |
| `classify/forms.py` | SF33/SF1449/SF30/synopsis signatures + SF30 ladder | VERIFIED | 183 lines; exports `detect_form`, `assign_doc_role`; all four signature variants present. |
| `classify/package.py` | `classify_package` → 4-way + evidence + warnings | VERIFIED | 160 lines; exports `classify_package`; all four literals reachable, `non_ucf_commercial` observed live. |
| `pipeline/run.py` | `run_pipeline` pure orchestration with stage timings | VERIFIED | 97 lines; exports `run_pipeline`; 5 stages timed; zero CLI imports (import boundary intact). |
| `src/rfp_analyzer/cli.py` | argparse `parse` subcommand, JSON + stdout tree + metrics | VERIFIED (untested — see W2) | 194 lines; exports `main`; exit codes manually spot-checked 0/1/2. |
| `tests/integration/test_corpus_packages.py` | corpus-driven assertions for all four SCs | VERIFIED | 139 lines, 6 test functions × parametrized packages = 10 tests, all pass on the real corpus. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pyproject.toml` | `cli.py` | `[project.scripts]` entry point | WIRED | Line 17 `rfp-analyzer = "rfp_analyzer.cli:main"` — and the installed `rfp-analyzer` command actually ran 5 times in this verification. |
| `models.py` | `metrics.py` | `DocumentMap.metrics: RunMetrics` | WIRED | `models.py:16` import + `:124` field; real timings present in emitted JSON. |
| `parsing/pdf.py` | `models.py` | constructs ParsedFile/PageInfo | WIRED | `pdf.py:21` import; 733 real pages constructed across corpus. |
| `parsing/docx.py` | `models.py` | constructs ParsedFile/BlockInfo | WIRED | `docx.py:24` imports `BlockInfo`; block spans observed in live DOCX run. |
| `quality/headers.py` | `models.py` | rewrites PageInfo.text/quality, ParsedFile.stripped_headers | WIRED | `headers.py:117/124/128`; live `stripped_headers` values confirmed non-empty. |
| `sectioning/tree.py` | `models.py` | emits SectionNode with Locator union | WIRED | `tree.py:37` import; both PageSpan and BlockSpan branches exercised live. |
| `classify/package.py` | `models.py` | classification literal + evidence/warnings | WIRED | `non_ucf_commercial` returned at `package.py:129` and observed in a real run. |
| `cli.py` | `pipeline/run.py` | `from rfp_analyzer.pipeline.run import run_pipeline` | WIRED | `cli.py:26` exact match; called at `:156`. |
| `pipeline/run.py` | parsing/quality/sectioning/classify | stage composition | WIRED | `run.py:69/75/79/80` call `apply_quality`, `build_section_tree`, `assign_doc_role`, `classify_package`. Import direction one-way: zero `cli` imports under `pipeline/`. |
| `manifest.json` | corpus package dirs | `dir` field | WIRED | All 3 `dir` values resolve to real directories; **all 14 declared sha256 digests match the on-disk bytes**. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `cli.py` `render_report` | `document_map` | `run_pipeline(package_dir)` | Yes — 290/408/35 real pages, real page ranges, real warnings | FLOWING |
| `document_map.json` | full DocumentMap | `model_dump_json()` of pipeline output | Yes — 893 KB / 856 KB / 106 KB, re-validates, `pending=0` | FLOWING |
| `classify_package` | `evidence`, `warnings` | detected form matches + section trees | Yes — 10 evidence lines on primary, 8 on non-UCF, all naming real files/pages | FLOWING |
| `RunMetrics.stage_timings` | dict | `time.perf_counter` deltas | Yes — `parse: 79.39s`, `quality: 0.11s` on the 408-page package | FLOWING |
| `ParsedFile.stripped_headers` | list[str] | `detect_running_lines` | Yes — `['SECTION C', '- FACILITY INVESTMENT']` on a real annex file | FLOWING |
| `page.metrics` | dict[str,float] | parse-time + computed metrics | Yes — cid_count/has_images drive 59 real quality flags | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite passes | `uv run python -m pytest tests/ -q` | `134 passed, 1 skipped in 112.33s` | PASS |
| Lint clean | `uv run ruff check .` | `All checks passed!` | PASS |
| Format clean | `uv run ruff format --check .` | `34 files already formatted` | PASS |
| CLI on primary corpus package | `rfp-analyzer parse tests/corpus/primary-ucf --out …` | exit 0; A–M tree; L 49-57, M 58-70; 3 amendments | PASS |
| CLI on non-UCF package | `rfp-analyzer parse tests/corpus/non-ucf-part12 --out …` | exit 0; `non_ucf_commercial`; 1 warning; 0 L/M nodes | PASS |
| CLI on hostile package | `rfp-analyzer parse tests/corpus/hostile-scanned --out …` | exit 0; `unknown` + warning; 59/408 pages flagged in ranges | PASS |
| CLI on mixed PDF+DOCX+.doc package | `rfp-analyzer parse <synthetic> --out …` | exit 0; DOCX block spans; `.doc` rejected with message | PASS |
| Independent UCF boundary check | direct `pdfplumber` read of pages 48-50, 57-59 | p49 = "Section L - Instructions…", p58 = "Section M - Evaluation…" — matches CLI exactly | PASS |
| Corpus integrity | sha256 of all 14 corpus files vs manifest.json | `ALL 14 MATCH` | PASS |
| Emitted maps re-validate, no `pending` | `DocumentMap.model_validate_json` on 3 artifacts | all validate; `pending=0` on 733 pages | PASS |
| CLI exit code — no structure found | parse a package with no headings | `exit 1` (documented honest-failure code) | PASS |
| CLI exit code — missing dir | parse a nonexistent path | `exit 2` | PASS |
| CLI exit code — no args | `rfp-analyzer` | `exit 2` + help | PASS |
| CI actually runs tests | `gh run view 30066972970 --log` | `collected 135 items` → `125 passed, 10 skipped in 0.77s` | PASS |
| Repo is public | `gh repo view --json visibility` | `"visibility":"PUBLIC"` | PASS |

### Probe Execution

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| — | — | No probe scripts declared in any PLAN and no `scripts/*/tests/probe-*.sh` exist in the repo | SKIPPED (no probes in scope) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PARS-01 | 01-01, 01-02, 01-03, 01-04, 01-06 | Parses hostile real-world federal PDFs (tables, multi-column, SF forms) into text with a structural document map (section hierarchy + page numbers) | SATISFIED | 733 real pages across 14 real SAM.gov PDFs parsed; per-file section trees with 1-indexed page ranges; 59 hostile pages (scanned/CID-gibberish/low-text) caught rather than passed through; tables extracted as `BlockInfo.table` for DOCX and traversed for PDFs; SF33/SF1449/SF30 form pages recognized. |
| PARS-02 | 01-01, 01-02, 01-05, 01-06 | Detects UCF section boundaries (L, M, C/SOW/PWS, H, etc.) and degrades honestly when a package doesn't follow clean UCF structure | SATISFIED | L/M/C/H boundaries on the primary package independently confirmed against the source PDF; `non-ucf-part12` → `non_ucf_commercial` + warning + zero fabricated L/M; `hostile-scanned` → `unknown` + "no section anchors to work from" warning; `classify_package` honesty contract (non-empty evidence always, ≥1 warning on every non-`full_ucf` outcome) enforced in code and by `test_package_classify.py`. |

**Orphaned requirements:** none. REQUIREMENTS.md maps exactly PARS-01 and PARS-02 to Phase 1; both are claimed by plan frontmatter and both are satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/**`, `tests/**` (source) | — | `TODO`/`FIXME`/`XXX`/`HACK`/`TBD`/`PLACEHOLDER`/"not yet implemented" | — | **Zero debt markers** in any source or test file. The only `TBD` hits are the literal string `"TBD"` used as *table cell test data* in `test_docx.py` / `test_models.py`, plus matches inside corpus PDF binaries. No debt-marker gate triggered. |
| `sectioning/tree.py` | 118, 253, 316 | `return []` | INFO | Deliberate honesty invariant ("a file with zero heading candidates returns an empty list"), documented in the module docstring and covered by `test_tree.py`. Not a stub — the non-empty paths are exercised on real corpus data. |
| `classify/forms.py`, `headings.py` | various | `return None` | INFO | Genuine "no match" sentinels for `detect_form` / `match_role_title`; both `None` and non-`None` paths observed live. Not stubs. |
| `src/rfp_analyzer/cli.py` | whole file | No test file imports `cli`, `render_report`, `build_parser`, or `_run_parse` | WARNING (W2) | 194-line primary deliverable with zero automated coverage. |
| `sectioning/tree.py` `_CROSS_REFERENCE_TAIL_RE` | 51-56 | Alternation misses `OR` and bare `SECTION X.` | WARNING (W1) | Two false-positive top-level sections in the primary package. |

### Warnings (non-blocking findings)

**W1 — Section-heading precision: prose lines become top-level sections.**
`N4008526R0033 Section C Annexes.pdf` emits two spurious top-level nodes:
- `SECTION F  pages 110-125` — sourced from post-quality page-110 line 5, the table body text `Section F.` (verified by re-running parse+quality and dumping the page's lines).
- `SECTION H — OR ON A MEASURED FROM ISSUE DATE OF  pages 126-161` — sourced from page-126 line 8, the table body prose `Section H or on a measured from issue date of`.

`_is_cross_reference` (`tree.py:86-96`) filters prose tails starting with `OF|IS|ARE|WAS|WERE|WILL|SHALL|MAY|HAS|HAVE|HEREBY|ABOVE|BELOW|AND|TO|IN|THEREOF|ENTITLED` — but not `OR`, and not an empty tail (`Section F.`). Same class in `hostile-scanned`: `SPECIAL REQS — SPECIAL CONTRACT REQUIREMENTS  pages 16-370` spans 355 pages of a specifications document from a single role-title line.

**Why this is a WARNING and not a BLOCKER:** SC2's "correctly detected" clause targets the standard solicitation, and `Solicitation - N4008526R0033.pdf`'s own L/M/C/H boundaries are exactly right (independently confirmed). SC2's "never silently mis-sectioned" clause targets the non-UCF package, which emits zero fabricated L/M nodes. Neither false positive is an L/M/C node, so package classification is unaffected. The impact is on Phase 2, which will inherit two bogus section anchors in an attachment. Escalated as human decision item 2.

**W2 — `cli.py` has zero automated test coverage.** `grep` across `tests/` for `cli`, `render_report`, `build_parser`, `_run_parse` returns nothing. The CLI is the phase's headline deliverable ("Running the CLI harness…" is SC1's opening clause) and owns non-trivial logic: exit-code policy, `_quality_ranges` contiguous-range collapsing, output-path derivation from the package dir name (the T-01-16 guard), and Windows console reconfiguration. I manually spot-checked exit 0/1/2 and the rendered report on 4 packages — all correct today — but nothing defends this against regression. Recommend adding CLI tests in Phase 2.

**W3 — Integration test asserts a weaker invariant than the manifest ground truth.** `test_primary_package_ucf_boundaries` asserts only `node.locator.page_start > 1`; it would pass with Section L detected at page 12 or page 30. The manifest records `total_pages` and file page counts but no expected section page numbers. I closed this gap manually for this verification (direct pdfplumber read confirmed 49/58), but the suite does not pin it. Recommend adding expected L/M page starts to `manifest.json` when the Phase 2 golden set is built.

**W4 — Corpus composition deviates from D-01's literal wording.** D-01 called for "one clean full-UCF solicitation" and "one FAR Part 12 combined synopsis/solicitation". Actual: the primary is an SF1449 carrying a full UCF A–M structure (classified `partial_ucf`; ground truth was corrected from `full_ucf` during 01-06 and documented in MANIFEST.md), and the non-UCF specimen is an SF1449 RFQ whose evidence line shows only an SF1449 match — no `COMBINED SYNOPSIS/SOLICITATION` / `FAR 12.603` marker was found. Consequence: the FAR 12.603 marker path in `detect_combined_synopsis` is exercised only by synthetic unit tests (`test_forms.py:99`, `test_package_classify.py:132`), never by real-world data. Roadmap SC2 says "e.g. FAR Part 12 combined synopsis", so the intent (a non-UCF commercial package that must be flagged) is met. Escalated as human decision item 1.

**W5 (INFO) — Header stripper removed an annex sub-title.** On `Section C Annexes.pdf`, `stripped_headers` includes `- FACILITY INVESTMENT`, i.e. the recurring annex title line `1502000 — Facility Investment` was frequency-detected as a running header (digits are stripped before comparison) and removed from those pages. This is by design (band-scoped, frequency-driven) and far less harmful than the pre-fix whole-page stripping, but it is content loss of a title line Phase 2 may want as a sub-section anchor.

**W6 (INFO) — 11 code-review Info findings deferred.** `01-REVIEW.md` records `IN-01..IN-11` as `deferred — out of fix scope`. All Critical (CR-01) and Warning (WR-01..WR-07) findings were fixed, and I independently confirmed the fixes are present in the code (guarded `OSError` handling in `discover.py`; size cap before hashing at `discover.py:153-174`; `_page1_usable` gibberish rung at `forms.py:100-113`; band-scoped stripping at `headers.py:89-97`; `_is_cross_reference` at `tree.py:86-96`; `sanitize_text` surrogate handling). Tracked as tech debt, not phase gaps.

### Disconfirmation Pass (Confirmation Bias Counter)

Per methodology, an explicit search for weaknesses even though the phase passes:

1. **A requirement only partially met:** SC1 says "page numbers for every file", but DOCX files get 0-indexed *block ordinals*, not page numbers. This is a deliberate, documented design decision (`models.py:5-7` "DOCX has no fixed pages — never synthesize page numbers for it"; plan 01-03 must-have truth states it explicitly; assumption A6). The intent — a navigable locator for every file — is fully met, and the discriminated `Locator` union makes the distinction explicit in the Phase 2 contract. Recorded as an accepted interpretation, not a gap.
2. **A test that passes but doesn't test its stated behavior:** `test_primary_package_ucf_boundaries` (W3 above) — its docstring says "L and M sections detected with page_start > 1 (TOC guard)" but the test name implies boundary correctness; it verifies only the TOC guard.
3. **An error path with no coverage:** the CLI exit-1 "honest failure" path (`cli.py:170-171`) and exit-2 usage paths have no automated tests (W2). Manually exercised in this verification — all three return the documented codes.

### Human Verification Required

Automated verification is complete: 28/28 must-haves, all 4 ROADMAP success criteria confirmed against the real corpus with independent source-PDF cross-checks. Two items require your judgment before Phase 2 planning.

#### 1. Is `partial_ucf` the right call for the primary corpus package?

**Test:** Open `tests/corpus/primary-ucf/Solicitation - N4008526R0033.pdf` page 1.
**Expected:** It is an SF1449 ("SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES") that nonetheless carries a complete UCF A–M section structure. Per the Open Question 1 rule, a commercial-form signal alongside UCF letter sections yields `partial_ucf` plus a "verify package format" warning rather than `full_ucf`.
**Why human:** This is a product-semantics decision, not a code property. Both classifications are internally consistent; the package becomes Phase 2's hand-shredded golden set, so the label matters downstream. Related: the corpus has no true FAR 12.603 combined-synopsis specimen (W4), so that code path is only synthetically tested.

#### 2. Fix section-heading false positives now, or accept them into Phase 2?

**Test:** Run `uv run rfp-analyzer parse tests/corpus/primary-ucf --out artifacts` and look at the `N4008526R0033 Section C Annexes.pdf` block.
**Expected:** You will see `SECTION F  pages 110-125` and `SECTION H — OR ON A MEASURED FROM ISSUE DATE OF  pages 126-161`. Both come from ordinary table body prose, not headings (verified against the raw page text). The `hostile-scanned` package similarly emits a 355-page `SPECIAL REQS` role-title node.
**Why human:** A precision-vs-recall tradeoff. Tightening `_is_cross_reference` (add `OR`, reject empty/1-token tails) and gating role-title nodes by span length would remove these, at some risk of dropping real headings. No success criterion is violated — this is a scope call about how clean the Phase 2 anchor set needs to be.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | SAM.gov API key request (`SAM_API_KEY`) | Phase 5 (optional) | ROADMAP Phase 5 SC4: "User can paste a SAM.gov solicitation number or link…". Deferred by explicit user decision 2026-07-24; recorded in the ROADMAP Phase 1 note ("No phase is blocked on it") and 01-HUMAN-UAT.md item 1. Applied as a verification override, not counted as a gap. |

### Gaps Summary

**No gaps.** Every must-have across all six plans and all four ROADMAP success criteria is backed by codebase evidence gathered independently of SUMMARY.md claims:

- The pipeline was **run**, not read: 4 live CLI invocations produced real document maps over 733 real pages of federal PDFs plus a synthetic DOCX package.
- The single most falsifiable claim — "UCF boundaries are correct" — was checked against the **source PDF directly** with pdfplumber, not against the pipeline's own report. Section L really begins on page 49 and Section M on page 58, exactly as reported.
- Corpus integrity was verified by **recomputing all 14 sha256 digests**, not by trusting MANIFEST.md.
- CI green-ness was verified by **reading the run log** (`125 passed, 10 skipped`), not by the badge — confirming the test step really executes and that integration tests skip cleanly without corpus binaries.
- The code-review fix claims (CR-01, WR-01..WR-07) were verified as **present in the source**, not accepted from the fix-outcomes table.

Status is `human_needed` rather than `passed` solely because two items need your judgment (classification semantics for the golden set; whether to tighten heading precision). Neither blocks Phase 2 planning — both are decisions to make *during* it. Four additional warnings (CLI test coverage, weak integration assertion, corpus composition deviation, header sub-title stripping) are recorded as tech debt.

---

_Verified: 2026-07-24T04:38:32Z_
_Verifier: Claude (gsd-verifier)_
