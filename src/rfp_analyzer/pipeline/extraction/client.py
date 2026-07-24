"""The only network-touching module in the pure library: the Ollama call.

Wraps the NATIVE ``ollama.Client`` (never the compatibility shim endpoint —
that path is the documented ``num_ctx`` passthrough failure). Every
call pins ``options.num_ctx=32768`` so a long section chunk is never silently
truncated to the ~4096 default (Pitfall 1 — the #1 recall killer), plus
``temperature=0`` and a fixed ``seed`` for a reproducible bake-off, and
``num_predict`` bounded to ``RESERVED_OUTPUT_TOKENS`` so a pathological grammar
generation cannot run away unbounded (an earlier full-corpus run wedged on a
large chunk with ``num_predict=-1`` and no timeout).

The Pydantic ``RequirementBatch`` schema is passed as ``format`` so the model
returns grammar-constrained, guaranteed-parseable JSON. A truncated/invalid body,
a per-call timeout, or a transport/server error all raise here — wrapped as
:class:`ExtractionParseError` so the orchestrator can isolate one bad chunk and
keep going (Pitfall 3); one stuck chunk never wedges the whole run.

Import-pure: localhost HTTP to the Ollama runtime is the sole network dependency
(a library making a network call, like a DB driver). No web-framework, CLI, or
queue imports. ``Client(...)`` is constructed lazily and opens no socket at
import time.
"""

import httpx
from ollama import Client, RequestError, ResponseError
from pydantic import ValidationError

from rfp_analyzer.pipeline.extraction.prompt import SYSTEM_PROMPT
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import RequirementBatch

_OLLAMA_HOST = "http://localhost:11434"
"""Localhost only — the runtime is never bound to a remote address in this phase."""

NUM_CTX = 32768
"""Model context window (qwen2.5 ``context_length``). Pinned on every call so a
chunk longer than the ~4096 default is never silently truncated (Pitfall 1)."""

RESERVED_OUTPUT_TOKENS = 12000
"""Token headroom reserved for the output JSON array (Pitfall 3). Input must fit
under ``num_ctx - RESERVED_OUTPUT_TOKENS``. Also the hard ``num_predict`` cap so
grammar-constrained generation cannot run away past the reserved budget."""

REQUEST_TIMEOUT_S = 300
"""Per-call wall-clock ceiling. A single chunk whose grammar generation stalls
raises a timeout (wrapped as ExtractionParseError) instead of blocking the whole
run forever — the failure mode that hung an earlier full-corpus pass."""

_CHARS_PER_TOKEN = 4
"""Coarse chars-per-token heuristic for the fit guard. Deliberately conservative
(English prose averages ~4 chars/token); the guard only needs an upper-bound
signal, not an exact count — the real token count is measured post-call."""

# Estimated token cost of the fixed system prompt, added to the input estimate so
# the guard accounts for the full prompt, not just the document chunk.
_SYSTEM_PROMPT_TOKENS = len(SYSTEM_PROMPT) // _CHARS_PER_TOKEN


class ExtractionParseError(ValueError):
    """The model returned a body that is not a valid ``RequirementBatch``.

    Raised on truncated or otherwise invalid JSON so the orchestrator can record
    the failed chunk and continue — one bad chunk never crashes the whole run.
    """


def estimate_tokens(text: str) -> int:
    """Return a coarse upper-ish token estimate for ``text`` (~4 chars/token)."""
    return len(text) // _CHARS_PER_TOKEN


def _assert_fits(
    chunk_text: str,
    num_ctx: int = NUM_CTX,
    reserved_output: int = RESERVED_OUTPUT_TOKENS,
) -> None:
    """Raise if ``chunk_text`` + system prompt would not leave output room.

    The hard guard behind Pitfall 1: rather than let Ollama silently truncate an
    over-budget prompt to the front ``num_ctx`` tokens (dropping every tail
    requirement with no error), refuse the call. ``reserved_output`` keeps room
    for the JSON array so a dense section's output is not itself truncated
    (Pitfall 3).
    """
    budget = num_ctx - reserved_output
    estimate = estimate_tokens(chunk_text) + _SYSTEM_PROMPT_TOKENS
    if estimate > budget:
        raise ValueError(
            f"chunk estimate {estimate} tokens exceeds the input budget {budget} "
            f"(num_ctx={num_ctx} - reserved_output={reserved_output}); split the "
            f"chunk smaller — sending it would silently truncate the tail."
        )


_client = Client(host=_OLLAMA_HOST, timeout=REQUEST_TIMEOUT_S)
"""Module-level native client. Construction opens no socket; the first ``chat``
call is the first network touch."""


def extract_chunk(
    chunk_text: str,
    model: str,
    seed: int = 7,
    *,
    metrics: RunMetrics | None = None,
) -> RequirementBatch:
    """Extract one chunk's requirement drafts via the local Ollama model.

    Guards ``num_ctx`` first (Pitfall 1), calls the native client with the
    grammar-constrained ``format`` schema and the pinned deterministic
    ``options``, and validates the response into a :class:`RequirementBatch`. A
    truncated/invalid body is re-raised as :class:`ExtractionParseError` for
    per-chunk isolation. When ``metrics`` is supplied, the call and the
    response's ``prompt_eval_count``/``eval_count`` are folded into it (local
    inference has no dollar cost, so ``estimated_cost_usd`` stays 0.0).
    """
    _assert_fits(chunk_text)
    try:
        resp = _client.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk_text},
            ],
            format=RequirementBatch.model_json_schema(),
            options={
                "num_ctx": NUM_CTX,
                "temperature": 0,
                "seed": seed,
                "num_predict": RESERVED_OUTPUT_TOKENS,
            },
            keep_alive="30m",
            stream=False,
        )
    except (httpx.TimeoutException, httpx.TransportError, ResponseError, RequestError) as exc:
        # A stalled/timed-out generation or a transport/server error must not wedge
        # the whole run — surface it as a per-chunk failure the orchestrator isolates.
        raise ExtractionParseError(f"model call failed for one chunk: {exc}") from exc
    if metrics is not None:
        metrics.llm_calls += 1
        metrics.input_tokens += resp.prompt_eval_count or 0
        metrics.output_tokens += resp.eval_count or 0
    try:
        return RequirementBatch.model_validate_json(resp.message.content)
    except ValidationError as exc:
        raise ExtractionParseError(
            f"model returned an invalid RequirementBatch (truncated JSON?): {exc}"
        ) from exc
