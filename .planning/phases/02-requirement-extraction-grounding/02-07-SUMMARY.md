---
phase: 02-requirement-extraction-grounding
plan: 07
subsystem: extraction, eval
tags: [claude-code-engine, replay, chunk_key, precision-recall, eval-harness, golden-set, ollama-retired]

# Dependency graph
requires:
  - phase: 02-requirement-extraction-grounding (plans 01-06)
    provides: extract.py (ExtractFn injection point), chunker.py (iter_chunks), run_extraction.py, sweep/amendments/grounding, RequirementSet models
  - phase: 02-requirement-extraction-grounding (plan 04)
    provides: golden_set.json (103 adversarially-validated ground-truth rows + declared match_rule)
provides:
  - Claude Code as the extraction engine via a file-mediated replay seam (chunks -> drafts.jsonl -> extract)
  - chunk_key() content-derived chunk identity
  - rfp_analyzer.eval.scoring (is_match/score/format_score_line) with golden-scope handling
  - rfp-analyzer chunks subcommand; extract --drafts (required) and --golden
  - tests/eval/fixtures/golden_drafts.jsonl — a committed, replayable Claude extraction run
  - tests/eval/EVAL.md — measured recall/precision/F1 with gap analysis
affects: [03-analysis-export, 04-web, compliance-matrix, parsing-backlog]

# Tech tracking
tech-stack:
  removed: ["ollama (dependency, client.py, liveness probe, requires_ollama marker)"]
  patterns:
    - "Engine-as-artifact: the extraction run is a committed JSONL recording replayed in pure Python, making accuracy numbers exactly reproducible instead of a sample of a stochastic process"
    - "extract_fn is required and keyword-only in both orchestrators — no code path can produce requirements from an unnamed source"
    - "Scoped precision: metrics computed within the golden set's (file_id, page) footprint; out-of-scope predictions counted and surfaced, never dropped or counted as errors"

key-files:
  created:
    - src/rfp_analyzer/pipeline/extraction/replay.py
    - src/rfp_analyzer/eval/scoring.py
    - src/rfp_analyzer/eval/__init__.py
    - tests/eval/metrics -> (moved) tests/eval/test_metrics.py, tests/eval/test_report_golden.py, tests/eval/conftest.py
    - tests/eval/fixtures/golden_drafts.jsonl
    - tests/eval/EVAL.md
    - tests/unit/test_replay.py
    - tests/unit/test_cli_chunks.py
  deleted:
    - src/rfp_analyzer/pipeline/extraction/client.py
    - tests/unit/test_client.py
  modified:
    - src/rfp_analyzer/cli.py
    - src/rfp_analyzer/pipeline/extraction/{chunker,extract,run_extraction,__init__}.py
    - src/rfp_analyzer/pipeline/{metrics,models}.py
    - tests/integration/{conftest,test_extract_corpus}.py
    - pyproject.toml

key-decisions:
  - "Plan reworked before execution: the Qwen 14b-vs-32b bake-off was retired with the local model. Replaced with the work that actually unblocks the eval — run_extraction still defaulted to the Ollama client, so no path produced a scorable extraction."
  - "The engine seam is file-mediated, not an in-process call: a Pro/Max subscription cannot be authenticated programmatically. The indirection is a feature — a committed drafts.jsonl replays byte-identically, so EVAL.md's numbers are auditable."
  - "chunk_key is keyed on normalize(text) ONLY (not file_id) because the ExtractFn seam receives just chunk_text. Identical boilerplate in two files shares a key and grounds independently per chunk — a benign, intended collision."
  - "DEVIATION: scoring moved from tests/eval/metrics.py to src/rfp_analyzer/eval/scoring.py. The plan had the CLI printing scores while the scorer lived in the test tree; src cannot import tests. Scoring is a product surface, not a CI-only gate."
  - "DEVIATION: added scope handling to score(). The golden set annotates ~22 of 290 pages, so counting predictions on unannotated pages as false positives would measure annotation coverage, not extraction quality. Recall is provably unaffected (every golden row is in scope by construction) and a test pins that."
  - "DEVIATION: the plan claimed the corpus test would 'run in CI'. It cannot — the corpus binaries are gitignored (D-02). The real improvement delivered: the ENGINE gate is gone, so the test runs wherever the corpus exists and needs no GPU/API/network."
  - "The 3 missed golden rows were NOT added to the drafts artifact after being identified. Doing so would make recall reflect knowledge of the answer key rather than extraction quality."

# Metrics
measured:
  recall: 0.971       # 100 of 103 golden requirements
  precision: 0.426    # in-scope; a LOWER BOUND, not an error rate — see EVAL.md
  f1: 0.592
  requirements: 277
  grounded: "277/277 (100%)"
  ungroundable: 0
  chunks_extracted: "19 of 98 (the golden-annotated scope)"
tests: "303 passing, 1 skipped"
---

# 02-07: Eval harness + Claude Code engine seam

## What shipped

The phase's objective accuracy signal (success criterion 5), plus the engine
pivot it depended on.

`run_extraction` still defaulted to the retired Ollama client, so there was no
path that produced a scorable extraction at all. The plan was reworked first: the
14B-vs-32B bake-off died with the local model, and was replaced by the two-step
file-mediated seam the subscription decision actually requires —

```
rfp-analyzer chunks  <artifacts> --out chunks.jsonl
(Claude Code reads the chunks and writes drafts.jsonl)
rfp-analyzer extract <artifacts> --drafts drafts.jsonl --golden <golden.json>
```

The indirection buys a property a live model call never had: **an extraction run
is an artifact.** The committed 414-draft recording replays byte-identically on
any machine — no GPU, no API key, no sampling variance anywhere in the pipeline —
so the accuracy numbers can be re-derived rather than trusted. This replaced all
the seed/temperature determinism juggling the local path needed (T-02-18 retired).

## Measured accuracy

| Metric | Value |
|---|---|
| Recall | **0.971** (100/103) |
| Precision (in scope) | 0.426 — *lower bound, not an error rate* |
| F1 | 0.592 |
| Grounded | **277/277 (100%)**, 0 ungroundable |

Precision was investigated rather than reported at face value. Only 10 of 135
unmatched in-scope predictions are atomic siblings of a match; the other 125 have
distinct verbatim spans and 65 carry `shall`/`must`/`shall not`. A hand-inspected
sample are plainly real obligations. **The golden set is a validated sample of its
pages, not an exhaustive shred** — so precision cannot be read as extraction
error. Making it exhaustive over a defined page range is the single
highest-value fix to this eval.

## Findings worth carrying forward

1. **Parser defect (Phase 3 backlog).** The Section C Annexes use a two-column
   spec-item table; flattening injects the *title* column mid-sentence
   ("authorizations to **Licenses** perform work", "30 calendar days written
   **Insurance** notice"). 10 of 70 annex spans had to reproduce the interleaved
   token to ground at all. This corrupts exported requirement text even when
   grounding succeeds — a proposal manager would see gibberish. Needs
   column-aware annex extraction + running-header suppression.

2. **Hyphenation breaks quotable spans.** All 3 missed golden rows are
   line-wrap hyphenation (`multi-\nyear` de-hyphenates to `multiyear`). The fix
   is to keep the newline inside the verbatim span; 2 of 3 were avoidable.

3. **The match rule is superset-tolerant.** `token_set_ratio` scores 100 when a
   prediction contains the golden span, so precision does not penalize over-broad
   quotes. Span tightness is enforced separately by `test_golden_verbatim.py`.

## Verification

- `uv run python -m pytest tests/ -q` → 303 passed, 1 skipped
- `uv run ruff check src/ tests/` → clean
- No `ollama` reference remains in `src/`, `tests/`, or `pyproject.toml`; the
  extraction stage makes zero network calls
- The corpus end-to-end test now runs on the replay path (no engine gate)
