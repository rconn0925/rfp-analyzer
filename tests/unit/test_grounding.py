"""Behavior tests for the EXTR-02 grounding backbone (verify.py).

``ground(verbatim, page_text)`` — normalize both sides, locate the quote in the
page (exact substring, then rapidfuzz fuzzy), return a scored span into the
*normalized page text* or ``None``. This is the hallucination gate: a quote that
cannot be located returns ``None`` and is never given an invented position.
"""

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.grounding.verify import ground

# --- ground(): normalize, locate, score --------------------------------------


def test_ground_exact_substring_scores_100():
    """A verbatim quote present in the page grounds exact with score 100.0."""
    page = "SECTION L. The offeror shall submit a technical volume by the due date."
    kind, start, end, score = ground("The offeror shall submit a technical volume", page)
    assert kind == "exact"
    assert score == 100.0
    # The returned span indexes the normalized page text.
    assert normalize(page)[start:end] == normalize("The offeror shall submit a technical volume")


def test_ground_ligature_and_hyphenation_still_exact():
    """A quote differing only by ligature/soft-hyphen grounds exact (both normalized)."""
    # Page text carries a fi-ligature and a soft line-break hyphen; the model quote
    # is the clean form. Normalization on both sides makes them identical.
    page = "The contractor shall provide the ﬁnal deliver-\nables to the Government."
    result = ground("The contractor shall provide the final deliverables", page)
    assert result is not None
    kind, _start, _end, score = result
    assert kind == "exact"
    assert score == 100.0


def test_ground_noisy_quote_matches_fuzzy_above_threshold():
    """Residual noise (a stray typo) still grounds fuzzy above the default threshold."""
    page = "The offeror shall submit the final technical volume no later than 3:00 PM."
    # 'finol' instead of 'final' — one edit, well above 92 partial_ratio.
    result = ground("The offeror shall submit the finol technical volume", page)
    assert result is not None
    kind, start, end, score = result
    assert kind == "fuzzy"
    assert score >= 92.0
    assert 0 <= start < end <= len(normalize(page))


def test_ground_absent_quote_returns_none():
    """A quote that is nowhere on the page returns None (below threshold)."""
    page = "The offeror shall submit a technical volume and a price volume."
    assert ground("Payment terms are net thirty days after invoice receipt", page) is None


def test_ground_empty_quote_returns_none():
    """An empty quote never spuriously grounds."""
    page = "The offeror shall submit a technical volume."
    assert ground("", page) is None


def test_ground_whitespace_only_quote_returns_none():
    """A whitespace-only quote never spuriously grounds."""
    page = "The offeror shall submit a technical volume."
    assert ground("   \n\t  ", page) is None
