# Phase 2: Requirement Extraction & Grounding - Context

**Gathered:** 2026-07-24
**Status:** Ready for planning
**Mode:** Interactive discuss (3 product decisions captured) + locked architecture pivot

<domain>
## Phase Boundary

Every requirement in a package is extracted verbatim with provably real source
references — measurably, with recall/precision evals as the objective signal.

Requirements in scope: EXTR-01 (extract every requirement, verbatim, stable ID),
EXTR-02 (computed + string-match-verified source refs, never LLM citations),
EXTR-03 (classify by type + binding keyword), EXTR-04 (scan attachments + Sections
C/H), EXTR-05 (deterministic keyword sweep reconciled against AI extraction),
INTK-03 (SF30 amendment requirement extraction + flag modified rows, no silent merge).

Input contract: the Phase 1 `DocumentMap` (document_map.json) — parsed, quality-gated,
sectioned, classified pages/sections. This phase consumes that, not raw PDFs.
Output: a set of extracted `Requirement` records (new Pydantic models) with grounded
source references, ready for Phase 3 analysis/export.
</domain>

<decisions>
## Implementation Decisions

### LOCKED — LLM foundation is LOCAL (no Anthropic API)
The entire extraction layer runs on a **local open-source model via Ollama**, NOT
the Anthropic API. This is a hard user constraint (never an API key; subscription
auth is technically impossible + ToS-blocked for a backend). See CLAUDE.md stack
banner and agent memory `local-llm-stack-decision`, `no-api-key-use-claude-subscription`.

- **Runtime:** Ollama v0.32.3, `http://localhost:11434` (OpenAI-compatible `/v1`).
  Validated 2026-07-24: 100% GPU on the RX 7900 XTX (24 GB VRAM) via ROCm,
  ~50 tok/s at 14B, JSON-schema structured outputs working.
- **Models present:** `qwen2.5:32b-instruct` (19 GB, quality) and
  `qwen2.5:14b-instruct` (9 GB, faster). **Model choice is an eval bake-off**, not a
  user decision — run both against the golden set, let recall/precision + latency pick.
- **Structured outputs:** use Ollama's JSON-schema `format` param to guarantee valid
  JSON against the Pydantic `Requirement` schema. NOT `messages.parse()`.
- **No Citations API, no Files API, no Batch API** — none needed (see grounding below).

### LOCKED — Grounding is computed + string-match verified (EXTR-02)
No LLM-generated citation ever reaches output. For each extracted requirement, the
source reference (document, section/paragraph, page) is **computed from the Phase 1
document map** and **string-match verified** against the source page text. If the
verbatim text can't be located in the cited page's text, the reference is rejected/
flagged — this is the honesty backbone and is mandatory, not optional. This design
predates and is unaffected by the local-LLM pivot.

### DECISION — Golden set: agent-drafted + adversarial-validated (autonomous)
Original decision was agent-draft + Ross review; Ross then directed full autonomous
operation (no interactive review). Adjusted: build the ground-truth golden set for
the primary RFP (N4008526R0033) by having one agent hand-shred it into a requirement
list, then a SECOND independent agent adversarially validates it against the source
PDF (finds misses, over-splits, wrong verbatim spans, wrong page refs) and reconciles.
This replaces the human checkpoint with a two-pass agent process. The golden set is
persisted in the repo with a companion review note so Ross can spot-check later
(non-blocking, like Phase 1's HUMAN-UAT). Eval recall/precision is measured against
this validated golden set. Derived from public data + labels; not a large binary.
Caveat to record honestly: an agent-built baseline shares some blind spots with the
extractor — the deterministic keyword sweep (EXTR-05) is the independent cross-check
that partially mitigates this.

### DECISION — Accuracy target: balanced F1, eval-tuned (Ross)
No deliberate lean toward recall or precision. Optimize overall F1 and let the eval
tune thresholds/prompts. (Note for planning: still REPORT recall and precision
separately, not just F1, so regressions in either are visible — the balanced choice
is about the optimization target, not hiding the components.)

### DECISION — Requirement granularity: atomic (Ross)
Split compound obligations into separate requirement rows. "The offeror shall submit
A, B, and C" → three rows, each with its own stable ID, so each gets its own Phase 3
compliance judgment and outline mapping. Matches how proposal teams shred. Planning
must define the splitting rule precisely (enumerations, coordinated verb phrases) and
ensure each atomic row still carries a verbatim span that string-match-verifies
against the source (EXTR-02) — atomic splitting must not break verbatim grounding.

### Claude's Discretion (technical — researcher/planner decide)
- Extraction chunking strategy (per-section vs per-page vs sliding window) given the
  local model's context window; how to feed Section L/M/C and attachments.
- Prompt design, few-shot examples, temperature, and per-model tuning.
- Stable requirement ID scheme (must be deterministic and stable across re-runs —
  RESEARCH from Phase 1 flagged stable IDs as first-class; carry that forward).
- The EXTR-05 deterministic keyword sweep implementation and how it reconciles with
  (surfaces gaps against) the AI extraction.
- Eval harness structure (metrics, matching rule for "same requirement", reporting).
- SF30 amendment change-detection approach (INTK-03) — how modified rows are flagged.
</decisions>

<code_context>
## Existing Code Insights (Phase 1 — reusable)

- `src/rfp_analyzer/pipeline/models.py` — Pydantic contract: `DocumentMap`,
  `ParsedFile`, `PageInfo`, `SectionNode`, `PageSpan`/`BlockSpan`/`Locator`. The new
  `Requirement` model(s) extend this same module. `DocumentMap` is the phase input.
- `src/rfp_analyzer/pipeline/run.py` — `run_pipeline(package_dir) -> DocumentMap`.
  Phase 2 adds a stage that consumes the DocumentMap (extraction is a new pipeline
  stage or a post-pipeline consumer — planner decides).
- `src/rfp_analyzer/pipeline/` is a PURE library (no HTTP/CLI imports) — the LLM
  client wrapper must keep that boundary; the Ollama call layer lives in the pipeline
  but must stay import-pure (local HTTP to localhost is fine; no web-framework deps).
- `src/rfp_analyzer/pipeline/metrics.py` — `RunMetrics` with LLM fields (were zeroed
  in Phase 1 for the $0 Claude plumbing). Repurpose for local-model metrics: calls,
  tokens, latency, model name. No dollar cost (local), but track tokens/latency.
- `src/rfp_analyzer/cli.py` — `parse` subcommand. Phase 2 likely adds an `extract`
  subcommand (dual output pattern established in Phase 1: JSON artifact + stdout report).
- Section text with page locators already exists per file in the DocumentMap — this is
  exactly what EXTR-02 grounding computes references from.
- `tests/corpus/` — the 3 real packages; `manifest.json` documents them. Primary =
  N4008526R0033 (now `full_ucf`). Integration tests key off manifest.json.
- TDD is the established pattern; `uv run python -m pytest` (the `pytest` exe is
  policy-blocked on this Windows machine); ruff clean; per-file isolation / hostile-
  input honesty is the house style.
</code_context>

<specifics>
## Specific Ideas

- **Primary RFP N4008526R0033 is the golden-set source** — its L (49-57) / M (58-70) /
  C boundaries are verified. This is where the hand-shred + human validation happens.
- **Ollama endpoint**: `http://localhost:11434`. Both `qwen2.5:14b-instruct` and
  `qwen2.5:32b-instruct` are pulled and ready. Bake-off both.
- **Report recall AND precision separately** every run (EXTR-05 success criterion +
  the balanced-F1 note above), not just F1.
- The keyword sweep (EXTR-05) is deterministic Python over the cleaned page text
  (shall/must/will/should) — it's the cross-check that catches what the model missed.
</specifics>

<canonical_refs>
## Canonical References (full paths — downstream agents MUST read)

- `.planning/ROADMAP.md` — Phase 2 goal + success criteria (5 criteria)
- `.planning/REQUIREMENTS.md` — EXTR-01..05, INTK-03 exact wording
- `CLAUDE.md` — **stack banner at top of Technology Stack**: LLM layer is local
  Ollama+Qwen, superseding all anthropic/Sonnet/Citations rows. MUST read before planning.
- `.planning/phases/01-parsing-structure-foundation/01-RESEARCH.md` — stable-IDs and
  verbatim-verification were flagged here as must-land-in-Phase-2 (not retrofit).
- `src/rfp_analyzer/pipeline/models.py` — the Pydantic contract to extend.
- `tests/corpus/manifest.json` — golden-set source package (primary-ucf = N4008526R0033).
- Agent memory (project decisions): `local-llm-stack-decision`,
  `no-api-key-use-claude-subscription`, `ucf-structure-decisive-classification`.
</canonical_refs>

<deferred>
## Deferred Ideas

- Multi-model ensemble / voting extraction — out of scope; single chosen model for v1.
- Fine-tuning a local model on federal RFPs — future; v1 uses instruct models as-is.
- SAM.gov fetch intake — deferred (see `sam-gov-api-key-deferred` memory); Phase 5 optional.
- Hosted GPU inference for a live public demo — Phase 5 uses precompute+cache instead.
</deferred>
