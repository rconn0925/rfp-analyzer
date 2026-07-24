"""Deterministic binding-keyword sweep + reconciliation (EXTR-03/05).

RESEARCH Pattern 6. A pure-Python pass — zero model involvement — that finds
every binding-keyword sentence in cleaned page text, then reconciles those hits
against the model's extraction:

- ``sweep_hits`` segments a page into sentences (abbreviation-guarded) and keeps
  those carrying a binding keyword, tagging each with the strongest keyword
  present (``shall not`` outranks ``shall``).
- ``reconcile`` marks each hit covered when some extracted requirement's
  normalized verbatim overlaps it on the same page; uncovered hits become
  :class:`MissedCandidate` rows (the surfaced model misses), and covered
  requirements adopt the sweep's source-derived ``binding_keyword`` (authoritative
  over the model's guess).
- ``flag_over_extractions`` is the precision side: requirements with no
  supporting sweep keyword on their page are returned as possible hallucinations.

The sweep **over-generates by design** (definitions, quoted clauses, "the
Government will" non-obligations all match). It is a recall floor and a candidate
surface, never ground truth — its value is catching what the model dropped.
"""

import re
from dataclasses import dataclass

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.models import MissedCandidate, Requirement

BINDING = re.compile(
    r"\b(shall not|shall|must|will|should|is required to|are required to)\b",
    re.IGNORECASE,
)
"""Binding-keyword pattern (RESEARCH Pattern 6). ``shall not`` precedes ``shall``
in the alternation so the longer phrase wins at a shared position."""

_KEYWORD_PRECEDENCE = [
    "shall not",
    "must",
    "shall",
    "will",
    "should",
    "is required to",
    "are required to",
]
"""When a sentence carries several binding keywords, the strongest (lowest index)
is reported. ``shall not`` outranks ``shall`` per the EXTR-05 contract."""

_ABBREVIATIONS = frozenset(
    {
        "no",
        "nos",
        "u.s",
        "u.s.a",
        "e.g",
        "i.e",
        "etc",
        "vs",
        "mr",
        "mrs",
        "ms",
        "dr",
        "sec",
        "art",
        "para",
        "fig",
        "inc",
        "co",
        "corp",
        "govt",
        "dept",
        "approx",
    }
)
"""Tokens whose trailing period is an abbreviation dot, not a sentence end."""

_BOUNDARY = re.compile(r"[.?!]\s+")
"""A candidate sentence break: terminal punctuation followed by whitespace.
Internal dots (``L.4.2``) are not followed by whitespace and never match."""


@dataclass(frozen=True)
class SweepHit:
    """One binding-keyword sentence found on a page by the deterministic sweep."""

    page: int
    verbatim_sentence: str
    binding_keyword: str
    file_id: str = ""


def sweep_hits(page_text: str, page_number: int, file_id: str = "") -> list[SweepHit]:
    """Return every binding-keyword sentence on a page (over-generates by design).

    ``page_text`` is normalized (the shared grounding normalizer) before
    segmentation so hits compare consistently with grounded requirement spans.
    ``file_id`` threads through to any :class:`MissedCandidate` produced during
    reconciliation.
    """
    normalized = normalize(page_text)
    hits: list[SweepHit] = []
    for sentence in _split_sentences(normalized):
        keyword = _strongest_keyword(sentence)
        if keyword is not None:
            hits.append(
                SweepHit(
                    page=page_number,
                    verbatim_sentence=sentence,
                    binding_keyword=keyword,
                    file_id=file_id,
                )
            )
    return hits


def reconcile(
    requirements: list[Requirement], hits: list[SweepHit]
) -> tuple[list[Requirement], list[MissedCandidate]]:
    """Reconcile extraction against the sweep (EXTR-05).

    Returns the requirements (with ``binding_keyword`` set from the covering
    sweep hit) and the list of uncovered hits as :class:`MissedCandidate` rows.
    A hit is *covered* when some requirement's normalized verbatim overlaps the
    hit sentence on the same page.
    """
    covered: set[int] = set()
    updated: list[Requirement] = []
    for req in requirements:
        req_norm = normalize(req.verbatim_text)
        page = req.source_ref.page
        keyword: str | None = None
        for i, hit in enumerate(hits):
            if hit.page != page:
                continue
            if _overlaps(req_norm, normalize(hit.verbatim_sentence)):
                covered.add(i)
                if keyword is None:
                    keyword = hit.binding_keyword
        if keyword is not None:
            req = req.model_copy(update={"binding_keyword": keyword})
        updated.append(req)

    missed = [
        MissedCandidate(
            file_id=hit.file_id,
            page=hit.page,
            verbatim_sentence=hit.verbatim_sentence,
            binding_keyword=hit.binding_keyword,
        )
        for i, hit in enumerate(hits)
        if i not in covered
    ]
    return updated, missed


def flag_over_extractions(
    requirements: list[Requirement], hits: list[SweepHit]
) -> list[Requirement]:
    """Return requirements with no supporting sweep keyword on their page.

    The precision counterpart to ``reconcile`` (Pattern 6, reverse check): a
    model-extracted obligation the deterministic sweep never saw on that page is
    a possible over-extraction (hallucination) and is surfaced for review. The
    requirement objects are returned unchanged — flagging is the caller's call.
    """
    flagged: list[Requirement] = []
    for req in requirements:
        req_norm = normalize(req.verbatim_text)
        page = req.source_ref.page
        if not any(
            hit.page == page and _overlaps(req_norm, normalize(hit.verbatim_sentence))
            for hit in hits
        ):
            flagged.append(req)
    return flagged


def _split_sentences(text: str) -> list[str]:
    """Segment normalized text into sentences, guarding common abbreviations.

    Splits only on terminal punctuation followed by whitespace, and suppresses a
    split when the preceding token is a known abbreviation (``No.``, ``U.S.``,
    ``e.g.``) or a dotted alphanumeric reference (``L.4.2``, ``52.212-4``).
    """
    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        preceding = text[start : m.start()]
        token = preceding.rsplit(" ", 1)[-1] if preceding else ""
        if _is_guarded(token):
            continue
        piece = text[start : m.end()].strip()
        if piece:
            sentences.append(piece)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _is_guarded(token: str) -> bool:
    """True if ``token``'s trailing period is an abbreviation/reference dot."""
    if not token:
        return False
    if token.lower().rstrip(".") in _ABBREVIATIONS:
        return True
    # Dotted alphanumeric reference (section number, FAR clause, decimal): a dot
    # plus a digit somewhere in the token means the period is structural.
    return "." in token and any(ch.isdigit() for ch in token)


def _strongest_keyword(sentence: str) -> str | None:
    """The highest-precedence binding keyword in a sentence, or None."""
    found = {m.group(1).lower() for m in BINDING.finditer(sentence)}
    for keyword in _KEYWORD_PRECEDENCE:
        if keyword in found:
            return keyword
    return None


def _overlaps(a: str, b: str) -> bool:
    """Coverage test: one normalized span contains the other (same-page)."""
    if not a or not b:
        return False
    return a in b or b in a
