"""Single pipeline entry: DocumentMap -> grounded, reconciled RequirementSet.

RESEARCH assembly order (chunk -> ground -> reconcile -> missed-candidate list
-> metrics). ``run_extraction`` composes the parts the prior plans built into one
pure library call, mirroring ``run.run_pipeline``'s style: no printing, no CLI or
queue imports, stage timings captured with ``time.perf_counter`` into
``RunMetrics.stage_timings``.

Wiring, in order:

1. **chunk** — ``iter_chunks(document_map)`` yields section-scoped windows over
   every ok file/section (EXTR-04 reach: L, M, and attachments/C alike).
2. **extract** — ``extract_requirements`` calls the model per chunk and grounds
   every draft's ``verbatim_text`` into a computed :class:`SourceRef`. The real
   Ollama call is wrapped so its ``prompt_eval_count``/``eval_count`` fold into a
   run-level :class:`RunMetrics` (llm_calls + tokens); ``estimated_cost_usd``
   stays ``0.0`` because local inference has no per-token dollar cost (A9).
3. **sweep + reconcile** — a deterministic binding-keyword sweep over every ok
   page's text; ``reconcile`` stamps each covered requirement's authoritative
   ``binding_keyword`` (the source-derived keyword wins over the model's guess,
   EXTR-05) and surfaces every uncovered hit as a :class:`MissedCandidate`.
4. **amendment flag** — ``flag_amendments`` marks amendment-sourced change rows
   and back-points affected base rows (INTK-03), never merging.

``model_name`` lives on the :class:`RequirementSet` (not ``RunMetrics``), and the
per-stage latency lives in ``stage_timings`` — so no schema change is needed
(RESEARCH "metrics repurpose, no schema change").

``extract_fn`` is injectable so the whole assembly is CI-testable with a canned
batch and no GPU; when it is left ``None`` the real, metrics-capturing Ollama
call is used.
"""

import time

from rfp_analyzer.pipeline.amendments import flag_amendments
from rfp_analyzer.pipeline.extraction.chunker import iter_chunks
from rfp_analyzer.pipeline.extraction.client import extract_chunk
from rfp_analyzer.pipeline.extraction.extract import ExtractFn, extract_requirements
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import DocumentMap, RequirementSet
from rfp_analyzer.pipeline.sweep import reconcile, sweep_hits

DEFAULT_MODEL = "qwen2.5:14b-instruct"
"""Default local model for end-to-end extraction. The 14b-vs-32b bake-off is a
separate plan (02-07); 14b is the faster default for the full-corpus pass."""


def run_extraction(
    document_map: DocumentMap,
    model: str = DEFAULT_MODEL,
    seed: int = 7,
    extract_fn: ExtractFn | None = None,
) -> RequirementSet:
    """Compose chunk -> extract -> reconcile -> amendment-flag into a RequirementSet.

    ``extract_fn`` defaults to the real (metrics-capturing) Ollama call; tests
    inject a fake that returns canned batches so the full path runs GPU-free.
    Stage latencies land in ``metrics.stage_timings`` under ``extract`` /
    ``sweep`` / ``amendments``; ``model`` is recorded on
    ``RequirementSet.model_name`` and ``estimated_cost_usd`` stays ``0.0`` (local).
    """
    metrics = RunMetrics()

    if extract_fn is None:
        # Wrap the real client so each call's token counts fold into the
        # run-level metrics; the injected-fake path skips this and leaves the
        # LLM counters at zero (nothing to account for a canned batch).
        def extract_fn(chunk_text: str, model_name: str, seed_value: int) -> object:
            return extract_chunk(chunk_text, model_name, seed_value, metrics=metrics)

    timings: dict[str, float] = {}

    chunks = list(iter_chunks(document_map))

    t0 = time.perf_counter()
    requirements = extract_requirements(chunks, model, seed, extract_fn=extract_fn)
    timings["extract"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    hits = _sweep_all_pages(document_map)
    requirements, missed_candidates = reconcile(requirements, hits)
    timings["sweep"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    requirements = flag_amendments(requirements)
    timings["amendments"] = time.perf_counter() - t0

    metrics.stage_timings = timings

    return RequirementSet(
        package_name=document_map.package_name,
        model_name=model,
        requirements=requirements,
        missed_candidates=missed_candidates,
        metrics=metrics,
    )


def _sweep_all_pages(document_map: DocumentMap) -> list:
    """Every binding-keyword sweep hit over every ok page's text, across all files.

    Only ``parse_status=="ok"`` files and ``quality=="ok"`` pages contribute —
    the same trust floor the chunker uses. ``file_id`` threads onto each hit so a
    surfaced :class:`MissedCandidate` keeps its provenance.
    """
    hits = []
    for file in document_map.files:
        if file.parse_status != "ok":
            continue
        for page in file.pages:
            if page.quality == "ok" and page.text:
                hits.extend(sweep_hits(page.text, page.page_number, file.file_id))
    return hits
