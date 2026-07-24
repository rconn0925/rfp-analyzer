# Phase 2: Requirement Extraction & Grounding - Research

**Researched:** 2026-07-23
**Domain:** Local-LLM structured extraction (Ollama + Qwen2.5), verbatim quote grounding via string/fuzzy match, deterministic requirement classification, recall/precision eval harness over federal RFPs
**Confidence:** HIGH (Ollama API, package versions, model context windows, grounding-library APIs all verified against a live runtime + registries) / MEDIUM (chunking token budgets and heuristic thresholds — deliberately eval-tunable against the golden set)

## Summary

Phase 2 turns the Phase 1 `DocumentMap` into a set of grounded `Requirement` records using a **local** Qwen2.5 model served by Ollama (v0.32.3, confirmed running on this machine with both `qwen2.5:14b-instruct` and `qwen2.5:32b-instruct` present, each with a 32768-token context window). Extraction uses Ollama's JSON-schema `format` parameter driven by a Pydantic `model_json_schema()`, so the model returns guaranteed-parseable JSON against the `Requirement` schema. Nothing in this phase talks to the Anthropic API — that entire row of the recommended stack is superseded (per the CLAUDE.md banner) and must not be referenced.

The two hard problems are (1) **verbatim grounding without model-generated citations** and (2) **atomic splitting that does not break that grounding**. Grounding (EXTR-02) is computed from the Phase 1 map and verified by string/fuzzy match: each requirement carries a `verbatim_text` span that must locate inside the cited page's `PageInfo.text` after normalization; if it does not, the reference is rejected/flagged. The tension with the locked *atomic granularity* decision is resolved by a **two-field design**: `verbatim_text` holds the real contiguous source span (this is what grounds), while `atomic_obligation` holds the model's single-obligation rewrite (which is *not* required to verbatim-match). Compound sentences ("shall submit A, B, and C") thus become three atomic rows that all share one verifiable verbatim span and a `parent_statement_id`. This preserves the honesty backbone while matching how proposal teams shred.

The single most important execution detail: **Ollama silently truncates any prompt to `num_ctx` (default ~4096 tokens) unless you explicitly pass `options={'num_ctx': 32768}`.** A section chunk longer than 4096 tokens will have its tail dropped with no error, and every requirement past that point vanishes — a catastrophic, invisible recall failure that would corrupt the entire eval. This is Pitfall 1 and the first thing every extraction call and every test must guard.

**Primary recommendation:** Use the native `ollama` Python client (0.6.2) — not the OpenAI-compatible endpoint — because `num_ctx`/`seed`/`temperature` pass cleanly through its `options` dict (verified against the installed package's `Options` model); the OpenAI-compat path is the documented failure mode for `num_ctx`. Chunk extraction **per UCF section** from the DocumentMap (sub-chunk large sections like the 161-page Section C Annexes into overlapping page windows), always pass `options={'num_ctx': 32768, 'temperature': 0, 'seed': <fixed>}`, ground every `verbatim_text` with `rapidfuzz.fuzz.partial_ratio_alignment` after NFKC + whitespace + de-hyphenation normalization, run a pure-Python shall/must/will/should sweep as the independent EXTR-05 cross-check, and score recall/precision separately against the two-agent golden set for the 14B-vs-32B bake-off.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **LOCKED — LLM foundation is LOCAL (no Anthropic API).** Entire extraction layer runs on a local open-source model via Ollama. Never an API key. Runtime: Ollama v0.32.3 at `http://localhost:11434` (OpenAI-compatible `/v1` exists but see recommendation to prefer native client). Validated 2026-07-24: 100% GPU on the RX 7900 XTX (24 GB VRAM) via ROCm, ~50 tok/s at 14B, JSON-schema structured outputs working. Do NOT research or reference `anthropic`, `messages.parse()`, Claude, Citations API, Files API, or Batch API.
- **LOCKED — Models present:** `qwen2.5:32b-instruct` (19 GB, quality) and `qwen2.5:14b-instruct` (9 GB, faster). **Model choice is an eval bake-off**, not a fixed decision — run both against the golden set; recall/precision + latency pick the winner.
- **LOCKED — Structured outputs** via Ollama's JSON-schema `format` param (pass a JSON schema, get guaranteed-valid JSON against the `Requirement` schema). NOT `messages.parse()`.
- **LOCKED — Grounding is computed + string-match verified (EXTR-02).** No LLM-generated citation ever reaches output. For each requirement the source reference (document, section/paragraph, page) is computed from the Phase 1 document map and string-match verified against the source page text. If the verbatim text can't be located in the cited page's text, the reference is rejected/flagged. Mandatory, not optional — the honesty backbone.

### Claude's Discretion (researcher/planner decide)

- Extraction chunking strategy (per-section vs per-page vs sliding window) given the local context window; how to feed Section L/M/C and attachments.
- Prompt design, few-shot examples, temperature, per-model tuning.
- Stable requirement ID scheme (must be deterministic and stable across re-runs — Phase 1 flagged stable IDs as first-class).
- The EXTR-05 deterministic keyword sweep implementation and how it reconciles with the AI extraction.
- Eval harness structure (metrics, matching rule for "same requirement", reporting).
- SF30 amendment change-detection approach (INTK-03) — how modified rows are flagged.

### Product Decisions (locked by Ross)

- **Golden set: agent-drafted + adversarial-validated (autonomous).** One agent hand-shreds N4008526R0033 into a requirement list; a SECOND independent agent adversarially validates it against the source PDF (finds misses, over-splits, wrong verbatim spans, wrong page refs) and reconciles. Persisted in-repo with a companion review note for non-blocking Ross spot-check. Honest caveat to record: an agent-built baseline shares blind spots with the extractor — the EXTR-05 deterministic sweep is the independent cross-check that partially mitigates this.
- **Accuracy target: balanced F1, eval-tuned.** No deliberate recall/precision lean; optimize overall F1 and let the eval tune thresholds/prompts. BUT still **report recall AND precision separately** every run so regressions in either are visible.
- **Requirement granularity: atomic.** Split compound obligations into separate rows, each with its own stable ID, so each gets its own Phase 3 judgment and outline mapping. Planning must define the splitting rule precisely (enumerations, coordinated verb phrases) and ensure each atomic row still carries a verbatim span that string-match-verifies against source — atomic splitting must not break verbatim grounding.

### Deferred Ideas (OUT OF SCOPE)

- Multi-model ensemble / voting extraction — single chosen model for v1.
- Fine-tuning a local model on federal RFPs — v1 uses instruct models as-is.
- SAM.gov fetch intake — deferred; Phase 5 optional.
- Hosted GPU inference for a live public demo — Phase 5 uses precompute + cache.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXTR-01 | Extract every requirement (shall/must/will/should, Section L instructions, Section M criteria) as verbatim text with a stable requirement ID | Ollama structured-output extraction per section chunk (Pattern 1); two-field `verbatim_text` + `atomic_obligation` schema (Pattern 3); content-derived stable ID scheme (Pattern 4) |
| EXTR-02 | Every requirement carries a computed source reference (document, section/paragraph, page) verified by string-match — never LLM citations | Grounding via `rapidfuzz.partial_ratio_alignment` after NFKC/whitespace/de-hyphenation normalization; reference computed from DocumentMap page locators, never from model output (Pattern 5) |
| EXTR-03 | Classify each requirement by type (L instruction / M criterion / C-SOW shall / clause / attachment) and binding keyword | Type derived from the owning `SectionNode.role` (already in the map) reconciled with model classification; binding keyword from deterministic sweep (Pattern 2 + Pattern 6) |
| EXTR-04 | Scan attachments (PWS, QASP, CDRLs) and Sections C/H for requirements outside L/M | Iterate ALL files/sections in the DocumentMap, not just L/M roles; the primary corpus has a 161-page Section C Annexes + 18-page Section F Annex to cover (Pattern 1 chunking) |
| EXTR-05 | Deterministic shall/must/will/should keyword sweep reconciles against AI extraction and surfaces missed candidates | Pure-Python regex sweep over cleaned `PageInfo.text`; reconciliation by verbatim-span overlap; unmatched hits surfaced as "missed candidates" (Pattern 6) |
| INTK-03 | Detect SF30 amendments, extract their requirements, flag potentially modified rows (no silent merging) | Amendment files already labeled `doc_role="amendment"` in the map; extract amendment change statements as their own rows; change-verb detection flags affected base rows without merging (Pattern 7) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **The Technology Stack banner supersedes the Anthropic rows.** LLM layer is local Ollama + Qwen2.5. Do not reference anthropic SDK, Sonnet, Citations/Files/Batch APIs anywhere in the plan.
- **Pure pipeline library:** `src/rfp_analyzer/pipeline/` has NO HTTP/CLI/queue imports from presentation code. The Ollama call layer lives inside the pipeline but must stay import-pure — local HTTP to `localhost:11434` is permitted (it's a library making a network call, like a DB driver); no web-framework deps. Presentation imports pipeline, never the reverse.
- **No whole-package LLM calls ever** — CLAUDE.md is explicit: dense pages can exhaust context; chunk by section, one extraction call per section (or sub-section).
- **Direct SDK + Pydantic per stage** — no LangChain/LlamaIndex. The pipeline is deterministic stages, not agentic retrieval.
- **TDD is the house style;** `uv run python -m pytest` (the bare `pytest` exe is policy-blocked on this Windows machine). ruff clean. Per-file isolation / hostile-input honesty.
- **Dual CLI output pattern** established in Phase 1: JSON artifact + human-readable stdout report. Phase 2 adds an `extract` subcommand following the same shape.
- **Metrics repurpose, no schema change:** `RunMetrics` already has `llm_calls`, `input_tokens`, `output_tokens`, `estimated_cost_usd` (zeroed in Phase 1). Populate `llm_calls`/tokens/latency for the local model; `estimated_cost_usd` stays 0.0 (local inference). Consider adding model name + latency via `stage_timings` keys rather than a schema change, or bump `schema_version`.

## Architectural Responsibility Map

Tiers are pipeline stages within the pure library (no web tiers in this phase):

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Chunking DocumentMap sections into model-sized prompts | `extraction` (new) | `models` (reads locators) | Section text + page locators already live in the map; chunker is pure transformation |
| Local model call (Ollama) with JSON-schema format | `extraction.client` (new) | — | Thin wrapper over `ollama.Client`; import-pure; the only network-touching module |
| Requirement schema (verbatim, atomic, source ref, type) | `models` (Pydantic) | — | Extends the Phase 1 contract module; serialized to `requirements.json` |
| Verbatim grounding / string-match verification | `grounding` (new) | `models` | Computes + verifies source refs from the map; rejects unverifiable quotes |
| Deterministic keyword sweep + reconciliation | `sweep` (new) | `grounding` | Pure Python over cleaned page text; independent of the model |
| Requirement classification (type + binding keyword) | `extraction` + `sweep` | `models` (SectionNode.role) | Type from section role; keyword from sweep; reconcile with model label |
| SF30 amendment change detection | `amendments` (new) | `classify` (Phase 1 role labels) | Operates on files already labeled `doc_role="amendment"` |
| Eval harness (recall/precision/F1, bake-off) | `eval` (new, or `tests/eval`) | `grounding` (matching rule) | Scores extraction against the golden set; drives model selection |
| Stable requirement ID assignment | `models`/`extraction` | — | Content-derived hash; deterministic across re-runs |
| `extract` CLI subcommand + report | `cli.py` | `extraction` | Presentation only; JSON artifact + stdout report (Phase 1 dual pattern) |

## Standard Stack

### Core (new for Phase 2)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama (Python) | 0.6.2 | Native client for the local Ollama runtime | Official Ollama Python client; `Client.chat(..., format=schema, options={...})` passes `num_ctx`/`seed`/`temperature` cleanly (verified against installed `Options` model). `[CITED: ollama.com/blog/structured-outputs, github.com/ollama/ollama-python]` `[VERIFIED: PyPI 0.6.2 latest 2026-07-23; slopcheck install approved]` |
| rapidfuzz | 3.14.5 | Fuzzy substring alignment for verbatim grounding | MIT, C++-backed, fast. `fuzz.partial_ratio_alignment` returns `src_start`/`src_end` — locates the matched span inside page text to map back to a page offset (verified present in installed 3.14.5). `[ASSUMED: discovered via training/WebSearch — passes slopcheck + registry, but not from authoritative docs, so treat name as assumed]` `[VERIFIED: PyPI 3.14.5 latest; API confirmed by import]` |

### Runtime (already present — not a pip install)

| Component | Version | Purpose | Status |
|-----------|---------|---------|--------|
| Ollama runtime | 0.32.3 | Local model server at `http://localhost:11434` | `[VERIFIED: /api/version returned 0.32.3 on this machine, 2026-07-23]` |
| qwen2.5:32b-instruct | Q4_K_M, ctx 32768 | Quality extraction model | `[VERIFIED: /api/tags — 19.85 GB, param 32.8B, context_length 32768, capabilities [completion, tools]]` |
| qwen2.5:14b-instruct | Q4_K_M, ctx 32768 | Faster extraction model | `[VERIFIED: /api/tags — 8.99 GB, param 14.8B, context_length 32768, capabilities [completion, tools]]` |

### Already installed (Phase 1, reused)

pdfplumber 0.11.10 (its `unicode_norm` param + ligature map matter for grounding normalization), pydantic 2.13.x, pytest 9.1.1, ruff. No new versions needed.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Native `ollama` client | OpenAI-compatible endpoint (`/v1`) via `openai` SDK | **Do NOT use for extraction.** The OpenAI-compat path is the documented `num_ctx` failure mode — several clients silently drop `options.num_ctx`, so the model runs at 4096 ctx and truncates. Native client passes `num_ctx` through `options` reliably. Use native. `[CITED: ollama/ollama issues re num_ctx over OpenAI API]` |
| Native `ollama` client | Raw `httpx` POST to `/api/chat` | Works and stays dependency-light, but you re-implement request/response typing the `ollama` package already provides. `ollama` is 15 KB, MIT, one dep tree — acceptable. Prefer it; drop to raw httpx only if the client proves limiting. |
| rapidfuzz | stdlib `difflib.SequenceMatcher` | difflib is pure-Python and dependency-free but ~100x slower and lacks a partial-alignment primitive; grounding runs over hundreds of quotes × long pages. Use rapidfuzz; keep difflib as a zero-dep fallback only if a dependency freeze is demanded. |
| rapidfuzz | `thefuzz`/`fuzzywuzzy` | thefuzz wraps rapidfuzz or a slower core and adds a layer; rapidfuzz is the modern maintained root. Use rapidfuzz directly. |
| Two-field verbatim+atomic | Verbatim-only, no atomic split | Would violate the locked atomic-granularity decision. Two-field is required. |

**Installation:**
```bash
uv add ollama rapidfuzz
```
(No `--dev`; both are runtime deps of the extraction stage.)

**Version verification (2026-07-23):** `pip index versions` → `ollama 0.6.2` latest, `rapidfuzz 3.14.5` latest. Ollama runtime + both models verified live via `/api/version` and `/api/tags`.

## Package Legitimacy Audit

slopcheck 0.x run 2026-07-23 (`slopcheck install ollama rapidfuzz`) — the tool checks packages and installs only the clean ones; both installed successfully, meaning neither was flagged `[SLOP]`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| ollama | PyPI | ~2 yrs (since 0.0.x, 2024) | millions/mo (approx) | github.com/ollama/ollama-python (official org) | [OK] | Approved |
| rapidfuzz | PyPI | ~6 yrs | millions/mo (approx) | github.com/rapidfuzz/RapidFuzz | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Provenance note:** `ollama` was discovered from official Ollama documentation (ollama.com blog + ollama-python repo) → authoritative. `rapidfuzz` was discovered from training/WebSearch → tagged `[ASSUMED]` by the package-name provenance rule despite passing slopcheck + registry existence. Both are ecosystem-dominant with real source repos; low risk. (Download counts approximate from training knowledge; slopcheck verdict + live PyPI version history are the operative evidence.)

## Architecture Patterns

### System Architecture Diagram

```
document_map.json  (Phase 1 output: files → sections(locator) → pages(text, quality))
        │
        ▼
┌──────────────── CLI (rfp-analyzer extract <artifacts-dir> --model qwen2.5:14b-instruct) ────────────────┐
│                                                                                                          │
│  load + validate DocumentMap (schema_version check)                                                      │
│        │                                                                                                 │
│        ▼                                                                                                 │
│  chunker: for each file, for each section (skip non-ok pages) ─────────────────────┐                     │
│    emit Chunk{ text, page_map[(char_range → page_number)], section_label, role,     │                     │
│               doc_role, file_id }   ; sub-chunk large sections into overlapping     │                     │
│    page windows so each chunk + expected output fits < num_ctx                      │                     │
│        │                                                                            │                     │
│        ▼                                                                            │                     │
│  ┌──────────────────────────────┐        ┌──────────────────────────────────────┐  │                     │
│  │ extraction.client (ollama)   │        │ sweep (pure Python, NO model)        │  │                     │
│  │  Client.chat(model, msgs,    │        │  regex shall/must/will/should/       │  │                     │
│  │   format=RequirementBatch    │        │  "is required to"/"shall not" over   │  │                     │
│  │     .model_json_schema(),    │        │  cleaned page text → candidate hits  │  │                     │
│  │   options={num_ctx:32768,    │        │  (verbatim sentence + page)          │  │                     │
│  │     temperature:0, seed:N})  │        └──────────────────────────────────────┘  │                     │
│  │  → RequirementDraft[]        │                        │                          │                     │
│  │    (verbatim_text,           │                        │                          │                     │
│  │     atomic_obligation,       │                        │                          │                     │
│  │     type_guess, keyword,     │                        │                          │                     │
│  │     parent lineage)          │                        │                          │                     │
│  └──────────────────────────────┘                        │                          │                     │
│        │                                                  │                          │                     │
│        ▼                                                  ▼                          │                     │
│  ┌──────────────────────────────────────┐   ┌──────────────────────────────────┐   │                     │
│  │ grounding: normalize(verbatim) vs     │   │ reconcile: each sweep hit covered │   │                     │
│  │ normalize(page.text); exact substr →  │   │ by an extracted verbatim span?    │   │                     │
│  │ rapidfuzz.partial_ratio_alignment;    │   │ unmatched → "missed candidate"    │   │                     │
│  │ >=thresh → source_ref{doc,sec,page,   │   │ (EXTR-05 surfaced gap)            │   │                     │
│  │ char_span}; else → verified=False,    │   └──────────────────────────────────┘   │                     │
│  │ flag                                  │                                          │                     │
│  └──────────────────────────────────────┘                                          │                     │
│        │                                                                            │                     │
│        ▼                                                                            │                     │
│  assign stable IDs (content hash) ; attach type (SectionNode.role reconciled) ──────┘                     │
│        │                                                                                                  │
│        ├───────────────► requirements.json  (verbatim, atomic, grounded source_ref, type, keyword, ID)   │
│        └───────────────► stdout report: counts by type/section, unverified flags,                        │
│                          missed-candidate list, metrics (model, calls, tokens, latency)                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                     │
                     ┌───────────────────────────────┴───────────────────────────────┐
                     ▼                                                                ▼
        eval harness (tests/eval): match requirements.json ↔ golden_set.json     bake-off:
        by fuzzy-verbatim overlap + page → precision / recall / F1 (reported     run 14b & 32b,
        separately)                                                              compare P/R/F1 + latency
```

Trace: the map enters top-left; each section becomes one or more chunks; the model extracts drafts while an independent pure-Python sweep finds keyword candidates; grounding verifies every verbatim span against real page text (rejecting model hallucination); reconciliation surfaces what the model missed; stable IDs + types finalize records; two artifacts exit; the eval harness scores against the golden set and drives the model bake-off.

### Recommended Project Structure

New modules inside the pure library; the extraction client is the only network-touching file.

```
src/rfp_analyzer/pipeline/
├── models.py            # EXTEND: add Requirement, RequirementDraft, SourceRef, RequirementSet
├── extraction/
│   ├── __init__.py
│   ├── client.py        # ollama.Client wrapper — ONLY network module; num_ctx guard lives here
│   ├── chunker.py       # DocumentMap sections → Chunk{text, page_map, section_label, role, ...}
│   ├── prompt.py        # system/user prompt templates + few-shot; verbatim-copy instruction
│   └── extract.py       # orchestrates chunk → client → drafts; per-model tuning
├── grounding/
│   ├── __init__.py
│   ├── normalize.py     # NFKC + whitespace collapse + de-hyphenation + ligature (shared both sides)
│   └── verify.py        # rapidfuzz alignment → SourceRef | flag
├── sweep.py             # deterministic keyword sweep + reconciliation
├── amendments.py        # SF30 change-statement detection + modified-row flagging (INTK-03)
└── ids.py               # content-derived stable requirement IDs

tests/
├── unit/                # normalize, grounding, sweep, id-stability, chunker (committed fixtures)
├── eval/
│   ├── golden/          # golden_set.json (primary-ucf) + review-note.md (committed — text, not binary)
│   ├── metrics.py       # precision/recall/F1 + matching rule
│   └── test_bakeoff.py  # runs 14b vs 32b; skipped if Ollama absent (like corpus tests)
└── integration/         # end-to-end extract over primary-ucf; skipif no Ollama / no corpus
```

### Pattern 1: Section-scoped chunking with page-offset preservation

**What:** Feed the model one UCF section at a time (not whole files, never whole packages). For each chunk, build the concatenated cleaned text AND a `page_map` recording which character range came from which page — this is what lets grounding map a matched span back to a page number.
**When to use:** All extraction. Sub-chunk any section whose text + expected output would exceed the context budget.

**Token budget (32768 ctx):** reserve output room. Dense federal body text tokenizes at roughly 600–1000 tokens/page for Qwen `[ASSUMED — measure on corpus]`. A safe rule: cap each chunk's **input** at ~16k tokens and reserve ~12k for output JSON, leaving headroom. That's ~15–25 pages/chunk. Section L (p49–57, ~9pp) and Section M (p58–70, ~13pp) each fit in one chunk; the 161-page Section C Annexes must be windowed. **Prefer smaller chunks over max-context stuffing** — long-context recall degrades toward the tail (see Pitfall 4), and smaller chunks bound output size (Pitfall 5).

**Overlap:** when sub-chunking a large section, overlap windows by ~1 page so a requirement straddling a page break isn't split. De-duplicate by stable ID afterward (content hash makes cross-window duplicates collapse naturally).

```python
# Prescriptive shape — chunker builds page_map for grounding
class Chunk(BaseModel):
    file_id: str
    section_label: str            # "L", "M", "C", "SOW", "H", attachment name
    role: str | None              # SectionNode.role → seeds EXTR-03 type
    doc_role: str                 # base_solicitation | amendment | attachment
    text: str                     # concatenated cleaned page text for the window
    page_map: list[tuple[int, int, int]]  # (char_start, char_end, page_number) per page

def iter_chunks(dmap: DocumentMap, max_input_chars: int) -> Iterator[Chunk]:
    for f in dmap.files:
        if f.parse_status != "ok":
            continue
        for section in _walk_sections(f.sections):
            pages = _pages_in_locator(f, section.locator)          # skip non-"ok" quality
            yield from _window(f, section, pages, max_input_chars)  # 1 chunk if it fits
```

### Pattern 2: Ollama structured-output call with the num_ctx guard

**What:** Every model call passes the Pydantic-derived JSON schema as `format` and an `options` dict that pins `num_ctx`, `temperature=0`, and a fixed `seed`. The `num_ctx` line is not optional — omitting it silently caps context at ~4096 tokens.
**When to use:** The single extraction entry point (`extraction/client.py`).

```python
# Source: ollama.com/blog/structured-outputs + verified installed ollama 0.6.2 Options fields
from ollama import Client
from pydantic import BaseModel

class RequirementDraft(BaseModel):
    verbatim_text: str            # EXACT contiguous span copied from source — grounds
    atomic_obligation: str        # single-obligation rewrite — NOT required to verbatim-match
    binding_keyword: str          # shall | must | will | should | shall not | none
    type_guess: str               # instruction | evaluation | sow_pws | clause | attachment | other
    parent_index: int | None      # links atomic siblings from one compound sentence

class RequirementBatch(BaseModel):
    requirements: list[RequirementDraft]

_client = Client(host="http://localhost:11434")   # localhost HTTP is allowed in the pure lib

def extract_chunk(chunk_text: str, model: str, seed: int = 7) -> RequirementBatch:
    resp = _client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},   # "copy verbatim, do not paraphrase"
            {"role": "user", "content": chunk_text},
        ],
        format=RequirementBatch.model_json_schema(),   # guaranteed-valid JSON
        options={
            "num_ctx": 32768,        # CRITICAL — else silent truncation to ~4096
            "temperature": 0,        # determinism
            "seed": seed,            # reproducible bake-off
            "num_predict": -1,       # don't cap output (else JSON truncates mid-array → parse fail)
        },
        stream=False,
    )
    return RequirementBatch.model_validate_json(resp.message.content)
```

Notes: `Client.chat` accepts `format`, `options`, `stream`, `keep_alive` (verified via `inspect.signature` on installed 0.6.2). `Options` exposes `num_ctx`, `seed`, `temperature`, `num_predict`, `top_k`, `top_p`, `stop` (verified). Consider `keep_alive="30m"` during a bake-off so the 19 GB 32B model isn't reloaded between chunks. Capture `resp` token counts (`prompt_eval_count`, `eval_count`) into `RunMetrics`.

### Pattern 3: Two-field verbatim + atomic (resolves the atomic-vs-grounding tension)

**What:** Compound obligations split into atomic rows, but grounding needs a real contiguous span. So each atomic row carries BOTH: `verbatim_text` (the true source span — this verifies against the page) and `atomic_obligation` (the model's single-duty rewrite — display/analysis text, never grounded).
**When to use:** Always. This is the load-bearing schema decision of the phase.

Example — source sentence: *"The offeror shall submit a technical volume, a past-performance volume, and a price volume."*

| ID | verbatim_text | atomic_obligation | parent |
|----|---------------|-------------------|--------|
| r-a1 | "The offeror shall submit a technical volume, a past-performance volume, and a price volume." | "Submit a technical volume." | — |
| r-a2 | *(same span)* | "Submit a past-performance volume." | r-a1 |
| r-a3 | *(same span)* | "Submit a price volume." | r-a1 |

All three ground to the same verified page span; Phase 3 judges/maps each atomic obligation independently. **Splitting rule (prescriptive, define precisely in the plan):** split on (a) coordinated noun-phrase enumerations under one verb ("shall submit A, B, and C"), (b) coordinated verb phrases sharing a subject ("shall submit X and shall not disclose Y"), (c) lettered/numbered sub-lists. Do NOT split conditional clauses or single obligations with qualifiers. When no split applies, `atomic_obligation` == a light normalization of `verbatim_text` and `parent` is null.

### Pattern 4: Content-derived stable requirement IDs

**What:** IDs must be identical across re-runs (Phase 1 flagged this as first-class). Order-based counters are NOT stable — extraction order can shift. Derive the stable key from content.

```python
# Stable key = hash of (file sha256/id + normalized verbatim + occurrence index + atomic ordinal)
import hashlib
def requirement_id(file_id: str, verbatim: str, occurrence: int, atomic_ord: int) -> str:
    norm = normalize(verbatim)                      # same normalizer grounding uses
    h = hashlib.sha256(f"{file_id}|{norm}|{occurrence}|{atomic_ord}".encode()).hexdigest()
    return f"REQ-{h[:10]}"
```

- `occurrence` disambiguates identical sentences appearing twice in one file (e.g., boilerplate); compute it deterministically by the verbatim span's page+char order.
- `atomic_ord` distinguishes atomic siblings sharing one verbatim span.
- Provide a **human-readable display label** separately (e.g., `L.4.2-3` = section path + ordinal) for the report and Excel export, but the stable machine key is the content hash. Display labels may renumber; the hash key must not.
- Re-running the same model+seed over the same map must reproduce identical IDs — assert this in a unit test (extract twice, compare ID sets).

### Pattern 5: Grounding — normalize then locate then map to page

**What:** Verify `verbatim_text` really exists in the cited page and compute the `SourceRef` from the map. Never trust a model-emitted page number.

**Normalization (identical on both sides — the quote and the page text):**
1. Unicode NFKC (folds ligatures like `ﬁ`→`fi`, full/half-width, etc.). pdfplumber also offers `extract_text(unicode_norm="NFKC")` and an internal ligature map — normalize at extraction OR here, but be consistent. `[CITED: pdfplumber discussion #904 ligature map; unicode_norm param]`
2. De-hyphenate soft line-break hyphens: `re.sub(r"(\w)-\n(\w)", r"\1\2", text)` before collapsing whitespace (federal PDFs wrap "require-\nments").
3. Collapse all whitespace runs (including newlines) to single spaces.
4. Optionally casefold for the *match* score but keep original for the stored span.

**Locate:**
```python
# Source: rapidfuzz 3.14.5 — fuzz.partial_ratio_alignment returns src_start/src_end
from rapidfuzz import fuzz
def ground(verbatim: str, page_text: str, threshold: float = 92.0):
    q, hay = normalize(verbatim), normalize(page_text)
    idx = hay.find(q)
    if idx != -1:
        return ("exact", idx, idx + len(q), 100.0)
    ali = fuzz.partial_ratio_alignment(q, hay)   # handles residual OCR/whitespace noise
    if ali and ali.score >= threshold:
        return ("fuzzy", ali.src_start, ali.src_end, ali.score)
    return None                                   # → verified=False, flag the requirement
```
Then use the chunk's `page_map` to convert the hay char offset back to a `page_number`, and read `section_label`/`file_id` from the chunk → build `SourceRef{document, section, page, char_span, match="exact"|"fuzzy", score}`. If `ground` returns None, set `verified=False` and surface it — do not drop silently, do not emit an unverified page number.

**Threshold** (92.0) is a starting point — eval-tune. Report the exact/fuzzy/failed counts every run so drift is visible.

### Pattern 6: Deterministic keyword sweep + reconciliation (EXTR-05)

**What:** A pure-Python pass — zero model involvement — that finds every binding-keyword sentence in the cleaned page text, then checks which extracted requirements cover each hit. Unmatched hits are candidate misses the model dropped. This is the *independent* cross-check that partially mitigates the shared blind spots of an agent-built golden set.

```python
BINDING = re.compile(r"\b(shall not|shall|must|will|should|is required to|are required to)\b", re.I)
# sentence-segment cleaned page text (simple: split on ". " with abbreviation guards),
# keep only sentences containing a BINDING hit; record (page, verbatim_sentence, keyword)
```

**Reconciliation rule:** a sweep hit is "covered" if some extracted requirement's grounded `verbatim_text` span overlaps the hit sentence on the same page (normalized substring or fuzzy ≥ threshold). Uncovered hits → `missed_candidates` list in the report and artifact. **Also the reverse:** an extracted requirement whose keyword ≠ any sweep hit on its page is a possible over-extraction (hallucinated obligation) — flag for the precision side. The sweep also supplies the authoritative `binding_keyword` for EXTR-03 (take it from the source text, not the model's guess).

**Caveats to encode:** the sweep over-generates (definitions, quoted clauses, "the Government will" non-obligations) — it is a *recall floor / candidate surface*, not ground truth. Its value is catching model misses, not being precise itself.

### Pattern 7: SF30 amendment handling (INTK-03) — extract + flag, never merge

**What:** Amendment files are already `doc_role="amendment"` in the map. Extract their requirements as their **own rows** (source ref = the amendment file/page). Detect change statements and flag potentially-affected base rows without merging.
**When to use:** Any file with `doc_role="amendment"`.

- **Extract amendment content** the same way as base sections (the SF30 Item 14 description block carries the substantive changes). Each amendment requirement gets its own stable ID and grounds to the amendment PDF.
- **Change-verb detection:** regex for amendment change language — `is (hereby )?(changed|revised|amended|deleted|added|replaced)`, `delete .* and (insert|substitute)`, `in lieu of`, `is changed to read`. A sentence matching these is a `change_statement`.
- **Flag, don't merge:** for each change statement, record it as its own row tagged `is_amendment_change=True` with the amendment number (if known). If it references a base section/paragraph (e.g., "Section L.4.2 is changed to read..."), attach a soft `affects` pointer to base requirements in that section and set their `possibly_modified=True` — but keep both rows. No automated merge (explicitly out of scope per REQUIREMENTS.md "Auto-merging amendment changes").
- **Phase 1 reality:** `amendment_number` is frequently `None` because SF30 Block 2 is an AcroForm field invisible to the text layer (STATE.md). A Phase 2 *candidate* (not required): read AcroForm field values via `pdfplumber`/`pypdf` to recover the number. Treat as nice-to-have; `None` remains an honest outcome and the change rows are still valid.

### Anti-Patterns to Avoid

- **Omitting `num_ctx`** — silent truncation; the #1 recall killer (Pitfall 1). Never call the model without it.
- **Trusting a model-emitted page/section number** — violates EXTR-02. Page refs are computed from the map + verified, always.
- **Requiring `atomic_obligation` to verbatim-match** — it's a rewrite; only `verbatim_text` grounds. Conflating them breaks either atomicity or grounding.
- **Whole-file or whole-package prompts** — CLAUDE.md-forbidden; blows context and tanks tail recall. Chunk by section.
- **Order-based requirement IDs** — not stable across re-runs. Use content hashes.
- **Dropping unverifiable quotes silently** — flag `verified=False` and surface; silent drops hide both hallucination and grounding bugs.
- **Treating the keyword sweep as ground truth** — it over-generates; it's a candidate surface, not the answer.
- **Using the OpenAI-compat `/v1` endpoint for extraction** — the `num_ctx` passthrough failure lives there.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON-valid model output | Prompt "please return JSON" + regex repair | Ollama `format=schema` (grammar-constrained) | Guaranteed parseable against the Pydantic schema; no repair loop |
| Fuzzy span location | Custom edit-distance / sliding-window matcher | `rapidfuzz.fuzz.partial_ratio_alignment` | C++-fast, returns src_start/src_end for page mapping |
| Ligature/width normalization | Hand-rolled char table | `unicodedata.normalize("NFKC", ...)` (+ pdfplumber's map) | NFKC folds ligatures, full/half width, compatibility chars correctly |
| Ollama request/response typing | Raw httpx + manual dicts | `ollama.Client` | Typed, maintained, passes `options` cleanly; 15 KB |
| Schema/serialization | Hand JSON (de)serializers | Pydantic 2 models (extends Phase 1 contract) | One versioned contract; `format` uses the same `model_json_schema()` |
| Model-call retries on flaky loads | Custom loop | (defer) tenacity if needed | Local calls rarely 429; add only if the runtime proves flaky |

**Key insight:** the deterministic sub-problems (JSON validity, fuzzy alignment, Unicode folding) all have mature solutions. The genuinely novel code is the *chunk→ground→reconcile* wiring and the atomic-splitting rule — exactly what the golden-set eval exists to tune. Do not spend novelty budget re-implementing string matching.

## Runtime State Inventory

Phase 2 is greenfield extraction code over an existing pipeline — no rename/refactor/migration. **N/A.** The one stateful external dependency is the Ollama runtime + pulled models, covered under Environment Availability. No stored data, OS-registered state, or build artifacts are renamed by this phase.

## Common Pitfalls

### Pitfall 1: `num_ctx` silent truncation destroys recall
**What goes wrong:** A 15-page section chunk (~10k tokens) is sent; Ollama runs at the default ~4096-token context, silently drops everything past the first ~4096 tokens, and the model extracts requirements from only the first few pages. No error, no warning. Recall craters and looks like a "model quality" problem.
**Why it happens:** Ollama's default `num_ctx` is ~4096 (Modelfile baseline 2048; runtime picks ~4096); exceeding it truncates from the start with no signal. `[VERIFIED: multiple Ollama issues + docs, 2026]`
**How to avoid:** ALWAYS pass `options={"num_ctx": 32768}` (matches the models' `context_length`). Add a guard that estimates chunk tokens and asserts they fit under `num_ctx − reserved_output`. Use the native client (OpenAI-compat is where `num_ctx` gets dropped).
**Warning signs:** Recall is fine on short sections and collapses on long ones; requirements only ever come from the start of a chunk; `prompt_eval_count` in the response is suspiciously capped near 4096.

### Pitfall 2: Verbatim drift (model paraphrases instead of copying)
**What goes wrong:** `verbatim_text` is a fluent paraphrase, not the source characters, so grounding fails (or worse, fuzzy-matches loosely and attaches a wrong page).
**Why it happens:** Instruct models default to helpful rewriting; structured output constrains *shape*, not *fidelity*.
**How to avoid:** System prompt must be explicit and repeated: "Copy the exact characters from the source. Do not paraphrase, summarize, correct, or reformat `verbatim_text`. Put any rewording only in `atomic_obligation`." Temperature 0. Then let grounding be the hard gate — anything that doesn't locate is flagged `verified=False`, which turns drift into a visible metric, not a silent corruption. Track the exact-vs-fuzzy-vs-failed ratio; a rising fuzzy/failed share means drift.
**Warning signs:** High fuzzy-match rate, low exact-match rate; grounding scores clustering just above threshold.

### Pitfall 3: JSON output truncation on large sections
**What goes wrong:** A dense section produces 60+ requirements; the JSON array is cut off mid-object; `model_validate_json` raises.
**Why it happens:** Output hit a token cap (`num_predict`) or the combined input+output exceeded `num_ctx`.
**How to avoid:** Set `num_predict=-1` (uncapped) but bound *input* chunk size so input+expected-output stays under `num_ctx`. Smaller chunks = smaller, complete outputs. Wrap `model_validate_json` in a per-chunk try/except that records a `parse_failed` chunk (isolated failure, Phase 1 house style) and continues — never crash the run.
**Warning signs:** `json.JSONDecodeError`/ValidationError on the largest sections only; output ending mid-string.

### Pitfall 4: Long-context tail-recall degradation on Qwen2.5
**What goes wrong:** In a max-context chunk, requirements near the end are missed more than those near the start.
**Why it happens:** Qwen2.5 14B/32B are trained at 32k, but RoPE-based attention degrades on long relative distances; extraction quality is best well below the ceiling. `[CITED: Qwen2.5 technical report; Qwen long-context blog]`
**How to avoid:** Chunk well under the ceiling (~16k input, not 30k). Prefer more, smaller chunks. The overlap-window de-dup (Pattern 1) covers boundary requirements. The EXTR-05 sweep is the safety net that catches whatever still slips.
**Warning signs:** Missed requirements cluster at the end of long chunks; shrinking chunk size raises recall.

### Pitfall 5: pdfplumber text noise breaks string-match
**What goes wrong:** A real quote fails to ground because the page text has a soft-hyphen line break, a ligature, a stripped-header artifact, or collapsed table whitespace that the quote lacks.
**Why it happens:** Phase 1 cleaned text still carries de-hyphenation seams and NFKC-foldable glyphs; the model's `verbatim_text` normalizes them away.
**How to avoid:** Apply the SAME normalizer (NFKC + de-hyphenation + whitespace collapse) to both the quote and the page text before matching (Pattern 5). rapidfuzz `partial_ratio_alignment` absorbs residual noise above threshold. Unit-test the normalizer on real ligature/hyphenation fixtures from the primary corpus.
**Warning signs:** Grounding fails on quotes a human can clearly see on the page; failures correlate with hyphenated line-wraps or `ﬁ`/`ﬂ` glyphs.

### Pitfall 6: GPU nondeterminism defeats "reproducible" eval
**What goes wrong:** Same model, same seed, same input — slightly different extraction between runs, so the bake-off numbers wobble.
**Why it happens:** `temperature=0` + fixed `seed` makes Ollama greedy and mostly reproducible, but GPU floating-point reduction order (especially under ROCm) is not bit-identical across runs; ties can break differently.
**How to avoid:** Pin `temperature=0` and `seed`, and treat the eval as tolerant of small variance — report to 2 significant figures, run the golden eval more than once if a decision is close, and rely on the golden-set delta (14B vs 32B) being larger than the noise. Document determinism as "high but not bit-exact" honestly.
**Warning signs:** ID-stability test flakes by one or two requirements between identical runs.

### Pitfall 7: 32B model + 32k context spills VRAM → CPU offload → crawl
**What goes wrong:** The bake-off's 32B run is far slower than 50 tok/s and GPU utilization drops below 100%.
**Why it happens:** 32B Q4_K_M weights (~19 GB) plus a 32k-token KV cache can exceed 24 GB VRAM, forcing partial CPU offload. (14B at ~9 GB has ample headroom; the user validated 100% GPU at 14B.)
**How to avoid:** For the 32B run, either lower `num_ctx` to the largest value that keeps 100% GPU (check `ollama ps` / GPU%), or accept slower throughput and record it as a bake-off cost. This is legitimate bake-off signal: if 32B needs reduced context or runs slow to fit, that weighs against it. Measure GPU% and tok/s, not just accuracy.
**Warning signs:** `ollama ps` shows CPU/GPU split for 32B; tok/s an order of magnitude below the 14B baseline.

## Code Examples

### Extraction call (verified against installed ollama 0.6.2)
```python
# Source: ollama.com/blog/structured-outputs; Options fields confirmed on installed 0.6.2
from ollama import Client
client = Client(host="http://localhost:11434")
resp = client.chat(
    model="qwen2.5:14b-instruct",
    messages=[{"role": "system", "content": SYSTEM_PROMPT},
              {"role": "user", "content": chunk.text}],
    format=RequirementBatch.model_json_schema(),
    options={"num_ctx": 32768, "temperature": 0, "seed": 7, "num_predict": -1},
    keep_alive="30m",
    stream=False,
)
batch = RequirementBatch.model_validate_json(resp.message.content)
metrics.llm_calls += 1
metrics.input_tokens += resp.prompt_eval_count or 0     # token accounting for RunMetrics
metrics.output_tokens += resp.eval_count or 0
```

### Shared normalizer (grounding + IDs + sweep must all use this)
```python
import re, unicodedata
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)          # folds ligatures, widths
    text = re.sub(r"(\w)[-\xad]\s*\n\s*(\w)", r"\1\2", text)  # de-hyphenate line wraps
    text = re.sub(r"\s+", " ", text)                    # collapse whitespace
    return text.strip()
```

### Precision/recall matching rule (eval harness)
```python
# A predicted requirement matches a golden one iff normalized verbatim overlaps
# (fuzzy >= MATCH_THRESHOLD) AND page numbers agree (same file, |Δpage| <= 0).
from rapidfuzz import fuzz
def is_match(pred, gold, thresh=90.0) -> bool:
    if pred.source_ref.file_id != gold.file_id or pred.source_ref.page != gold.page:
        return False
    return fuzz.token_set_ratio(normalize(pred.verbatim_text),
                                normalize(gold.verbatim_text)) >= thresh
# precision = matched_preds / total_preds ; recall = matched_golds / total_golds
# report precision, recall, AND f1 separately (per locked balanced-F1 decision)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Anthropic Sonnet + Citations API (original CLAUDE.md stack) | Local Ollama + Qwen2.5, computed string-match grounding | Phase 2 pivot, 2026-07-24 | No API key, no per-token cost, full data locality; grounding is verification not model-citation |
| Prompt-and-pray JSON + regex repair | Grammar-constrained `format=schema` structured outputs | Ollama structured outputs GA, late 2024 | Guaranteed-valid JSON against the Pydantic schema |
| fuzzywuzzy/thefuzz (python-Levenshtein) | rapidfuzz (C++), MIT | 2023+ | Faster, maintained, alignment primitives |
| Model emits its own citations | Compute ref from doc map + verify quote | project design (predates pivot) | Eliminates the hallucinated-citation failure class |

**Deprecated/outdated for this phase:** any reference to `anthropic`, `messages.parse()`, Claude models, Citations/Files/Batch APIs (superseded by the local stack); the OpenAI-compat Ollama endpoint for extraction (num_ctx passthrough hazard).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Qwen dense-page tokenization ≈ 600–1000 tokens/page | Pattern 1 budget | Medium — wrong budget over/under-chunks; measure `prompt_eval_count` on the first corpus chunk and calibrate |
| A2 | Grounding threshold 92 (rapidfuzz partial) / match threshold 90 (token_set) are good starting points | Patterns 5–6, eval | Medium — eval-tunable; too low = false grounding, too high = real quotes rejected; sweep + report make errors visible |
| A3 | `verbatim_text` + `atomic_obligation` two-field design satisfies both atomic granularity and EXTR-02 | Pattern 3 | Low-Medium — core design bet; validated the moment the first compound sentence grounds while its atomic rows carry the shared span |
| A4 | Overlap-window + content-hash de-dup cleanly collapses cross-chunk duplicates | Patterns 1, 4 | Low — worst case a few dupes survive; a de-dup pass on stable ID handles it |
| A5 | GPU nondeterminism under ROCm is small enough that golden-set deltas dominate noise | Pitfall 6 | Low-Medium — if noisy, run eval 2–3× and average; decision margin usually larger |
| A6 | 32B Q4 + large num_ctx may spill 24 GB VRAM | Pitfall 7 | Low — it's a measured bake-off variable, not a correctness risk; lower num_ctx or accept slower |
| A7 | SF30 substantive changes live in the Item 14 description block and are extractable text | Pattern 7 | Medium — some SF30s are scanned (Phase 1 hostile specimen); scanned amendment pages are quality-flagged and honestly skipped, change rows just won't extract |
| A8 | rapidfuzz `partial_ratio_alignment` src offsets map reliably back through the chunk page_map | Pattern 5 | Low — offsets are into the normalized haystack; keep a parallel raw↔normalized index or re-locate in raw text |
| A9 | `estimated_cost_usd` stays 0.0 (local); tokens/latency are the meaningful metrics | CLAUDE.md constraints | None — local inference has no per-token dollar cost |

## Open Questions

1. **Exact chunk token budget for each Qwen size.**
   - What we know: 32768 ctx; tail recall degrades below the ceiling; must reserve output room.
   - What's unclear: the precise input cap that maximizes F1 without over-chunking (call overhead).
   - Recommendation: start at ~16k input / reserve ~12k output; sweep chunk size as an eval knob during the bake-off. Measure `prompt_eval_count` to ground A1.

2. **Does grounding need char-offset mapping through normalization, or is per-page re-location enough?**
   - What we know: rapidfuzz returns offsets into the normalized haystack; we need a page number, not exact chars, for the ref.
   - Recommendation: since grounding is scoped to a single page's text (via page_map), the page number is known once a page's text matches — exact char offset is optional metadata. Store char_span best-effort; the page is the load-bearing output.

3. **AcroForm SF30 amendment-number recovery — in scope for Phase 2 or defer?**
   - What we know: Phase 1 left `amendment_number=None` (AcroForm fields invisible to text layer); flagged as a Phase 2 candidate.
   - Recommendation: treat as nice-to-have. Change-statement rows are valid without the number. If cheap (pdfplumber/pypdf field read), add it; otherwise defer — don't let it block extraction.

4. **Sentence segmentation quality for the sweep and atomic splitting.**
   - What we know: naive `. ` splitting mis-handles "No.", "U.S.", "e.g.", section numbers like "L.4.2".
   - Recommendation: a small abbreviation-guarded splitter in pure Python (no new dep); tune against corpus. Over-segmentation hurts the sweep's precision but not its recall-floor role.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Ollama runtime | All extraction | ✓ | 0.32.3 (`/api/version`) | None — hard requirement; tests skipif unreachable |
| qwen2.5:14b-instruct | Bake-off (fast) | ✓ | Q4_K_M, ctx 32768, 8.99 GB | — |
| qwen2.5:32b-instruct | Bake-off (quality) | ✓ | Q4_K_M, ctx 32768, 19.85 GB | Lower num_ctx if VRAM-bound (Pitfall 7) |
| ollama (Python) | client wrapper | ✗ (needs `uv add`) | 0.6.2 on PyPI | Raw httpx to `/api/chat` (Pattern alt) |
| rapidfuzz | grounding, eval | ✗ (needs `uv add`) | 3.14.5 on PyPI | stdlib difflib (slower, no alignment) |
| pdfplumber / pydantic | reused from Phase 1 | ✓ | 0.11.10 / 2.13.x | — |
| GPU (RX 7900 XTX / ROCm) | 100% GPU inference | ✓ | 24 GB, validated 100% GPU @14B | 32B may partial-offload at max ctx |
| Primary corpus (primary-ucf) | golden set + integration | ✓ (gitignored) | N4008526R0033, 7 files, 290 pp | tests skipif corpus absent |

**Missing dependencies with no fallback:** none blocking — the two pip installs are trivial (`uv add ollama rapidfuzz`); the runtime + models are already present and validated.
**Missing dependencies with fallback:** ollama Python client (raw httpx), rapidfuzz (difflib) — neither fallback is needed given both are clean installs.
**CI note:** GitHub Actions has no GPU and no Ollama. All model-calling tests must `skipif` on Ollama unreachable (mirror Phase 1's corpus-skip pattern). Grounding, normalizer, sweep, chunker, and ID-stability tests run pure-Python in CI with committed fixtures. The bake-off and end-to-end extraction run locally only.

## Security Domain

`security_enforcement` is not explicitly disabled in config → treated as enabled. Phase 2 is still a local CLI over local files, but it introduces the first LLM call, which changes the threat surface versus Phase 1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local runtime, no auth |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Document text is untrusted input fed to an LLM. Treat model output as untrusted too: validate via Pydantic (`format` schema), ground every quote (reject/flag unverifiable), isolate per-chunk parse failures. No `eval`/exec of model or document content. |
| V6 Cryptography | no (hashing only) | `hashlib.sha256` for stable IDs — integrity, not secrecy |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection — RFP text contains "ignore instructions and…" | Tampering | The model's job is extraction, and **grounding is the backstop**: any injected/fabricated "requirement" that isn't verbatim-locatable on a real page is flagged `verified=False`. Keep document text strictly in the user turn; keep extraction instructions in the system turn; never execute extracted text. |
| Hallucinated requirement (model invents an obligation) | Spoofing (fake provenance) | EXTR-02 grounding rejects it (no source span); EXTR-05 reverse-check flags requirements with no keyword on their page. This is the core honesty mechanism. |
| Local runtime exposure (`0.0.0.0:11434`) | Info Disclosure | Bind to `localhost` only (client uses `http://localhost:11434`); no remote exposure in this phase. |
| Resource exhaustion (a pathological 400-page section) | DoS | Chunk-size cap + per-chunk isolation; a slow chunk is visible on a local CLI. Revisit hard timeouts before Phase 4 web upload. |

## Validation Architecture

**Skipped** — `.planning/config.json` sets `workflow.nyquist_validation: false`. (Standard pytest + the eval harness remain the quality gate per the house TDD style; the Nyquist-specific section is intentionally omitted per the researcher spec.)

## Sources

### Primary (HIGH confidence)
- Live Ollama runtime on this machine — `GET /api/version` → `0.32.3`; `GET /api/tags` → both qwen2.5 models, `context_length: 32768`, Q4_K_M, capabilities `[completion, tools]` (2026-07-23)
- Installed `ollama` 0.6.2 — `inspect.signature(Client.chat)` params `[model, messages, tools, stream, think, logprobs, top_logprobs, format, options, keep_alive]`; `Options` fields include `num_ctx, seed, temperature, num_predict, top_k, top_p, stop` (verified by import)
- Installed `rapidfuzz` 3.14.5 — `fuzz.partial_ratio_alignment` present (verified by import)
- ollama.com/blog/structured-outputs — Python `format=Model.model_json_schema()`, `options={'temperature':0}`, "use Pydantic, say return JSON, set temperature 0"
- github.com/ollama/ollama/blob/main/docs/api.md — `format` JSON-schema request examples for `/api/chat` and `/api/generate`; `options` (num_ctx, seed, temperature)
- PyPI via `pip index versions` (2026-07-23) — `ollama 0.6.2`, `rapidfuzz 3.14.5` latest
- slopcheck `install ollama rapidfuzz` (2026-07-23) — both clean, installed
- Phase 1 artifacts — `models.py` (DocumentMap/ParsedFile/SectionNode/PageInfo/Locator contract), `run.py`, `metrics.py`, `cli.py`, `tests/corpus/manifest.json` (primary-ucf = N4008526R0033, L@p49 M@p58), `01-RESEARCH.md` (stable-ID + verbatim-verification hand-off)

### Secondary (MEDIUM confidence)
- Ollama num_ctx default/truncation — multiple GitHub issues (ollama/ollama #6286, #10974) + how-to guides (autodidacts.io, serverman.co.uk, markaicode) agree: default ~4096, silent truncation, must pass `options.num_ctx`; OpenAI-compat path drops it
- Qwen2.5 long-context behavior — qwenlm.github.io Qwen2/Qwen2.5-1M blogs; Qwen2/Qwen2.5 technical reports (arxiv 2407.10671, 2412.15115): 32k-trained, RoPE tail degradation, extraction strong below ceiling
- pdfplumber ligature/normalization — jsvine/pdfplumber discussion #904 (ligature map), `unicode_norm` param on `extract_text`

### Tertiary (LOW confidence / assumptions — see Assumptions Log)
- Per-page token estimate (A1), grounding/match thresholds (A2), GPU-nondeterminism magnitude (A5), VRAM spill for 32B at max ctx (A6) — all eval/measurement-tunable, flagged for calibration on first corpus run

## Metadata

**Confidence breakdown:**
- Standard stack + runtime: HIGH — versions verified on PyPI, runtime + both models verified live, client/rapidfuzz APIs confirmed by import, slopcheck clean
- Architecture (chunk→ground→reconcile, two-field schema, stable IDs): HIGH on design shape (constrained by locked decisions + Phase 1 contract); MEDIUM on exact token budgets/thresholds (eval-tunable by design)
- Grounding approach: HIGH — computed-ref + fuzzy-verify is the locked design; rapidfuzz alignment API verified
- Pitfalls: HIGH for num_ctx (verified across sources + live runtime) and verbatim drift; MEDIUM for long-context degradation and VRAM specifics (model-/hardware-dependent)

**Research date:** 2026-07-23
**Valid until:** ~2026-08-23 (Ollama moves fast — re-check `num_ctx` behavior and structured-output API if the runtime is upgraded past 0.32.x; Qwen2.5 and FAR structure are stable on this horizon)
