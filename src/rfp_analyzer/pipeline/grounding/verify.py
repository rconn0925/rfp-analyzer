"""Verbatim grounding: locate a quote in page text and compute its SourceRef.

The EXTR-02 honesty backbone. A requirement's ``verbatim_text`` must locate
inside its source page text after normalization; a quote that cannot be located
is flagged ``verified=False`` — never silently dropped, never assigned an
invented page. No model-emitted citation ever reaches output: every page number
is computed from the chunk's ``page_map``.

Pure library code — no HTTP, queue, or CLI imports.
"""

from rapidfuzz import fuzz

from rfp_analyzer.pipeline.grounding.normalize import normalize

# rapidfuzz partial_ratio score at/above which a fuzzy hit is accepted. Starting
# point from RESEARCH A2 (92.0); a module-level constant so the eval can tune it.
DEFAULT_THRESHOLD: float = 92.0


def ground(
    verbatim: str,
    page_text: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[str, int, int, float] | None:
    """Locate ``verbatim`` inside ``page_text`` and return a scored span.

    Both sides are normalized (NFKC + de-hyphenation + whitespace collapse) so a
    model quote and its wrapped/ligatured page text compare equal (Pitfall 5).
    An exact substring hit scores 100.0; otherwise a rapidfuzz
    ``partial_ratio_alignment`` hit at/above ``threshold`` is accepted as fuzzy.

    Returns ``(match_kind, start, end, score)`` where ``match_kind`` is
    ``"exact"`` or ``"fuzzy"`` and ``start``/``end`` index the **normalized**
    ``page_text``. Returns ``None`` when the quote is empty/whitespace-only or
    cannot be located above the threshold — the caller flags it, never invents a
    position.
    """
    q = normalize(verbatim)
    if not q:
        return None
    hay = normalize(page_text)
    if not hay:
        return None

    idx = hay.find(q)
    if idx != -1:
        return ("exact", idx, idx + len(q), 100.0)

    # partial_ratio_alignment(query, haystack): dest_start/dest_end index the
    # haystack (page text), src_start/src_end index the query. We need the
    # position inside the page to map back through page_map, so use dest_*.
    ali = fuzz.partial_ratio_alignment(q, hay)
    if ali is not None and ali.score >= threshold:
        return ("fuzzy", ali.dest_start, ali.dest_end, ali.score)
    return None
