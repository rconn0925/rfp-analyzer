---
phase: 01-parsing-structure-foundation
plan: 01
subsystem: scaffolding
tags: [uv, pydantic, ruff, pytest, github-actions, schema]
requires: []
provides:
  - "uv-managed Python 3.12 src-layout package with locked deps (pdfplumber 0.11.10, python-docx 1.2.0, pydantic 2.13.4)"
  - "DocumentMap/ParsedFile/PageInfo/BlockInfo/SectionNode/PageSpan/BlockSpan/Locator — versioned Phase 2 contract"
  - "RunMetrics cost-instrumentation scaffolding (D-09) with zeroed LLM fields"
  - "Public GitHub repo rconn0925/rfp-analyzer with CI workflow (push deferred to orchestrator)"
  - "Corpus gitignore (tests/corpus/*) in place before any corpus binary exists"
affects: [01-02, 01-03, 01-04, 01-05, 01-06, phase-2]
tech-stack:
  added: [uv 0.11.30, pdfplumber 0.11.10, python-docx 1.2.0, pydantic 2.13.4, pytest 9.1.1, pytest-cov 7.1.0, ruff 0.15.22]
  patterns: [src-layout, pure-library pipeline subpackage, discriminated Locator union, TDD]
key-files:
  created:
    - pyproject.toml
    - uv.lock
    - .python-version
    - .gitignore
    - README.md
    - .github/workflows/ci.yml
    - src/rfp_analyzer/__init__.py
    - src/rfp_analyzer/cli.py
    - src/rfp_analyzer/pipeline/__init__.py
    - src/rfp_analyzer/pipeline/models.py
    - src/rfp_analyzer/pipeline/metrics.py
    - tests/unit/test_models.py
  modified: []
decisions:
  - "PageInfo.quality includes 'pending' as pre-quality-stage default; serialized maps must never contain it"
  - "BlockInfo is a typed model (not raw dict as in the research sketch) for DOCX blocks"
  - "ParsedFile.first_page_layout_text carries layout-mode page-1 text for SF-form field extraction"
  - "DocumentMap constructible with no args (all fields defaulted) so schema_version/metrics defaults are testable and incremental assembly works"
  - "master->main rename and initial push deferred to orchestrator (worktree execution mode)"
metrics:
  duration: "6 minutes"
  completed: "2026-07-23"
  tasks: 3
  files: 12
---

# Phase 1 Plan 01: Project Scaffolding, Schema Contract, and Public Repo Summary

**One-liner:** uv-managed Python 3.12 package with the Pydantic DocumentMap schema (PageSpan/BlockSpan Locator union) as the Phase 2 contract, RunMetrics cost scaffolding, corpus-safe gitignore, and a public GitHub repo with CI — push deferred to orchestrator.

## What Was Built

- **Task 1 — Scaffolding (b211192):** Installed uv 0.11.30 via winget (was absent, per RESEARCH environment audit). `uv init --package` src layout, Python pinned to 3.12 (uv-managed; system is 3.14), `requires-python = ">=3.12"`. Locked deps exactly per RESEARCH Standard Stack: pdfplumber 0.11.10, python-docx 1.2.0, pydantic 2.13.4; dev: pytest 9.1.1, pytest-cov 7.1.0, ruff 0.15.22. All 6 packages were pre-cleared by the slopcheck audit (6/6 OK) and installed successfully on first attempt. Entry point `rfp-analyzer = "rfp_analyzer.cli:main"` with an argparse `parse` stub (prints "not yet implemented", exits 2). Pure-library `pipeline/` subpackage root. `.gitignore` with corpus exclusion (`tests/corpus/*` + MANIFEST.md/manifest.json exceptions) committed before any corpus binary exists.
- **Task 2 — Schema (TDD: 72c83fd RED, 0320d1a GREEN):** `models.py` implements RESEARCH Pattern 6 — PageSpan/BlockSpan discriminated `Locator` union, PageInfo (with `pending` pre-quality status), typed BlockInfo, recursive SectionNode, ParsedFile (SF30 amendment fields, `first_page_layout_text`), DocumentMap (schema_version "1.0", 4-way classification, warnings). `metrics.py` implements RunMetrics per D-09 with zeroed LLM fields. Five behavior tests pass: JSON round-trip (PDF+DOCX), Locator discrimination on `kind`, defaults, quality-vocabulary rejection, recursive nesting.
- **Task 3 — Repo + CI (2a27bf5):** `.github/workflows/ci.yml` per RESEARCH Pattern 7 (checkout@v4, setup-uv@v8 python 3.12, `uv sync --locked --dev`, ruff check, ruff format --check, pytest tests/unit). Created public repo `rconn0925/rfp-analyzer` via `gh repo create` (empty, no push) and added `origin` remote (repo-level shared config).

## Deviations from Plan

### Worktree-mode adjustments (per orchestrator spawn instructions, not rule deviations)

**1. Push, branch rename, and CI confirmation deferred to orchestrator**
- **Found during:** Task 3
- **Issue:** Executing in a git worktree on branch `worktree-agent-af75f681f2bb9b1d6`; pushing from the worktree would publish the agent branch, and renaming `master` -> `main` mid-orchestration would break the orchestrator's merge target.
- **Adjustment:** Created the GitHub repo empty (`gh repo create rfp-analyzer --public`), added the `origin` remote (`https://github.com/rconn0925/rfp-analyzer.git`) as shared repo-level config, did NOT push and did NOT rename the branch.
- **Orchestrator follow-ups required:** (1) after merging this worktree, rename `master` -> `main` (`git branch -m master main`), (2) push main (`git push -u origin main`), (3) confirm CI green (`gh run list --limit 1`). Plan acceptance criteria `git branch --show-current == main`, remote push, and CI-success are intentionally unmet inside the worktree.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] uv init defaulted requires-python to >=3.14**
- **Found during:** Task 1 (step 2)
- **Issue:** `uv init` under system Python 3.14 wrote `requires-python = ">=3.14"`, which blocked `uv python pin 3.12`.
- **Fix:** Set `requires-python = ">=3.12"` (a plan-specified value) before pinning; pin then succeeded, uv fetched managed CPython 3.12.13.
- **Files modified:** pyproject.toml
- **Commit:** b211192

## TDD Gate Compliance

- RED gate: `test(01-01)` commit 72c83fd (tests failed with ModuleNotFoundError before implementation)
- GREEN gate: `feat(01-01)` commit 0320d1a (5/5 tests pass)
- REFACTOR: not needed — ruff check and format clean on first pass

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `parse` subcommand prints "not yet implemented", exits 2 | src/rfp_analyzer/cli.py | Plan-mandated stub; plan 01-06 wires the real pipeline. Entry point must resolve now so `uv run rfp-analyzer --help` works. |

## Verification Results

- `uv sync --locked` + `uv run pytest tests/unit -q` — 5 passed
- `uv run rfp-analyzer --help` — entry point resolves
- `uv run ruff check .` + `uv run ruff format --check .` — clean
- `git check-ignore tests/corpus/somefile.pdf` — ignored; MANIFEST.md and manifest.json trackable
- `uv run python -c "import pdfplumber, docx, pydantic"` — exit 0
- No `fitz`/`pymupdf` in pyproject.toml (AGPL prohibition upheld)
- `gh repo view rconn0925/rfp-analyzer --json visibility` — PUBLIC
- `git ls-files tests/corpus/` — empty (no binaries tracked)
- Deferred (post-merge, orchestrator): default branch = main, CI run conclusion = success

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | b211192 | feat(01-01): scaffold uv-managed package with locked deps, tooling, and corpus gitignore |
| 2 (RED) | 72c83fd | test(01-01): add failing behavior tests for document-map schema |
| 2 (GREEN) | 0320d1a | feat(01-01): implement document-map schema and RunMetrics scaffolding |
| 3 | 2a27bf5 | chore(01-01): add GitHub Actions CI (uv sync, ruff check+format, unit tests) |

## Notes for Downstream Plans

- Import the contract as `from rfp_analyzer.pipeline.models import DocumentMap` (and siblings); `from rfp_analyzer.pipeline.metrics import RunMetrics`.
- uv is installed at the winget package path (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`); the PATH modification requires a fresh shell — subsequent agents in this session should use the full path or check `uv --version` first.
- **User action item (from CONTEXT):** request the SAM.gov API key now (login.gov account -> Account Details page) — ~10 business day issuance; Phase 5 depends on it.

## Self-Check: PASSED

All 12 created files verified on disk; all 4 task commits (b211192, 72c83fd, 0320d1a, 2a27bf5) verified in git log.
