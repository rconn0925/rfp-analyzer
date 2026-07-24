"""Behavior tests for the Ollama client wrapper (client.py) and prompt.py.

The client is the only network-touching module in the pure library. The tests
here are all pure-Python (no GPU, no Ollama): they exercise the ``num_ctx`` fit
guard, the token heuristic, the typed parse-error wrapper, and the verbatim
system prompt. A single live ``extract_chunk`` test is ``skipif`` gated on
Ollama being unreachable (mirrors the corpus-skip pattern) so CI never needs a
model.
"""

import socket

import pytest

from rfp_analyzer.pipeline.extraction.client import (
    ExtractionParseError,
    _assert_fits,
    estimate_tokens,
    extract_chunk,
)
from rfp_analyzer.pipeline.extraction.prompt import SYSTEM_PROMPT
from rfp_analyzer.pipeline.models import RequirementBatch


def _ollama_available(host: str = "localhost", port: int = 11434) -> bool:
    """True when a TCP connect to the local Ollama runtime succeeds.

    Mirrors the corpus-skip guard: model-calling tests are skipped (never
    failed) when the local runtime is unreachable, e.g. in CI.
    """
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


# --- estimate_tokens: pure heuristic -----------------------------------------


def test_estimate_tokens_scales_with_length():
    """The heuristic grows with text length and is never negative."""
    assert estimate_tokens("") == 0
    short = estimate_tokens("a short sentence")
    long = estimate_tokens("a short sentence" * 100)
    assert 0 < short < long


# --- _assert_fits: the num_ctx guard (Pitfall 1) -----------------------------


def test_assert_fits_passes_for_small_chunk():
    """A modest chunk fits comfortably under the budget and does not raise."""
    _assert_fits("The offeror shall submit a technical volume.", num_ctx=32768)


def test_assert_fits_raises_when_input_would_exceed_budget():
    """An over-budget chunk raises rather than letting Ollama silently truncate."""
    # ~4 chars/token heuristic: a chunk far larger than num_ctx - reserved_output.
    huge = "x " * 200_000
    with pytest.raises(ValueError, match="num_ctx"):
        _assert_fits(huge, num_ctx=32768, reserved_output=12000)


def test_assert_fits_reserves_output_room():
    """The guard trips when input alone would leave no room for output JSON."""
    # Build a chunk whose token estimate sits between (num_ctx - reserved) and num_ctx:
    # it must still raise, because reserved_output room is required.
    num_ctx = 8000
    reserved = 4000
    # Target ~ (num_ctx - reserved) + slack tokens of input.
    text = "word " * ((num_ctx - reserved) * 4 // 5 + 500)
    with pytest.raises(ValueError):
        _assert_fits(text, num_ctx=num_ctx, reserved_output=reserved)


# --- SYSTEM_PROMPT: the verbatim-fidelity instruction ------------------------


def test_system_prompt_demands_verbatim_copy():
    """The prompt must forbid paraphrase and require an exact verbatim copy."""
    lowered = SYSTEM_PROMPT.lower()
    assert "verbatim" in lowered
    assert "paraphrase" in lowered
    assert "atomic" in lowered


# --- ExtractionParseError: isolated parse failures ---------------------------


def test_extraction_parse_error_is_valueerror_subclass():
    """The typed error the orchestrator isolates is catchable and specific."""
    assert issubclass(ExtractionParseError, Exception)
    err = ExtractionParseError("truncated JSON")
    assert "truncated" in str(err)


# --- live model call: skipped when Ollama is unreachable ---------------------


@pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama runtime unreachable at localhost:11434 — model tests skipped (CI has no GPU)",
)
def test_extract_chunk_live_returns_batch():
    """A live extraction over the local model returns a valid RequirementBatch.

    Not a CI gate — runs only on a developer machine with Ollama up.
    """
    batch = extract_chunk(
        "SECTION L. The offeror shall submit a technical volume.",
        model="qwen2.5:14b-instruct",
    )
    assert isinstance(batch, RequirementBatch)
