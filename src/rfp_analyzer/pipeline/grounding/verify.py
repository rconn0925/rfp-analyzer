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
from rfp_analyzer.pipeline.models import Chunk, SourceRef

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


def _page_for_offset(page_map: list[tuple[int, int, int]], offset: int) -> int | None:
    """Return the page number whose char band contains ``offset``, else None.

    ``page_map`` bands are ``(char_start, char_end, page_number)`` over the
    normalized chunk text, ``char_end`` exclusive. The page is taken ONLY from
    this map — never from any caller- or model-supplied value.
    """
    for char_start, char_end, page_number in page_map:
        if char_start <= offset < char_end:
            return page_number
    # Fall back to the last band that starts at/before the offset (guards an
    # offset landing exactly on the final band's exclusive end).
    for char_start, _char_end, page_number in reversed(page_map):
        if offset >= char_start:
            return page_number
    return None


def build_source_ref(
    verbatim: str,
    chunk: Chunk,
    threshold: float = DEFAULT_THRESHOLD,
) -> SourceRef:
    """Compute a verified :class:`SourceRef` for ``verbatim`` within ``chunk``.

    Grounds ``verbatim`` against the chunk's text; on a hit, the matched char
    offset is translated into a real page number by scanning ``chunk.page_map``
    (the page is NEVER taken from model output). On a miss the requirement is
    retained and flagged (``verified=False``, ``match="none"``, ``page=None``) —
    per the "never drop silently" rule.

    ``doc_role`` is copied from the chunk on BOTH paths so an ungroundable
    amendment quote still records that it came from an amendment, keeping INTK-03
    amendment gating correct downstream.
    """
    result = ground(verbatim, chunk.text, threshold)

    if result is None:
        return SourceRef(
            file_id=chunk.file_id,
            filename=chunk.filename,
            section_label=chunk.section_label,
            page=None,
            char_start=None,
            char_end=None,
            match="none",
            score=0.0,
            verified=False,
            doc_role=chunk.doc_role,
        )

    match_kind, start, end, score = result
    page = _page_for_offset(chunk.page_map, start)
    return SourceRef(
        file_id=chunk.file_id,
        filename=chunk.filename,
        section_label=chunk.section_label,
        page=page,
        char_start=start,
        char_end=end,
        match=match_kind,
        score=score,
        verified=True,
        doc_role=chunk.doc_role,
    )
