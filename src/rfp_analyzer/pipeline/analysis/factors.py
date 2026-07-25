"""Which evaluation factor a requirement belongs to.

The anchor that makes L↔M cross-mapping mean something. Paraphrase similarity
cannot tell "Limit the Factor 1 narrative to 25 single-sided pages" from "Limit
the Technical Approach to Safety narrative to seven single-sided pages" — they
score 88 against each other and are about different factors entirely. A federal
proposal is organised BY factor, so the factor is the join key, not the wording.

Factor identity is read from position, not from text mentions. Section M opens
each factor with a line-anchored heading:

    (1) Factor 1, Management Approach:
    (2) Factor 2, Corporate Experience:

while prose references ("submitted under Factor 2, Corporate Experience") appear
mid-line and must NOT anchor — a Factor 2 reference inside Factor 4's section
would file the row under the wrong factor. Requiring the parenthesised ordinal at
the start of a line separates the two cleanly.

A requirement then inherits the factor whose heading most recently precedes its
grounded ``(page, char_start)`` position — provenance we already compute and
verify, so the assignment is as trustworthy as the citation itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.models import DocumentMap, Requirement

FACTOR_HEADING = re.compile(
    r"^[ \t]*\(\s*\d+\s*\)\s*Factor\s+(\d+)\s*[,:\-–—]",
    re.IGNORECASE | re.MULTILINE,
)
"""A factor SECTION heading — parenthesised ordinal, at the start of a line.

Deliberately stricter than "mentions Factor N": the mid-sentence references are
far more common than the headings, and treating them as anchors mis-files rows.
"""


def factor_anchors(document_map: DocumentMap) -> dict[str, list[tuple[int, int, str]]]:
    """Return ``{file_id: [(page, normalized_offset, factor_id), ...]}`` in reading order.

    Offsets are positions in the page's NORMALIZED text, because that is the only
    frame a requirement can be located in too. ``SourceRef.char_start`` is a
    *chunk* offset, not a page offset — comparing the two directly silently
    mis-files every row that shares a page with a factor heading, which is exactly
    how the Section M award-mechanics preamble first came out tagged Factor 1.
    """
    anchors: dict[str, list[tuple[int, int, str]]] = {}
    for file in document_map.files:
        if file.parse_status != "ok":
            continue
        found: list[tuple[int, int, str]] = []
        for page in file.pages:
            if page.quality != "ok" or not page.text:
                continue
            for match in FACTOR_HEADING.finditer(page.text):
                offset = len(normalize(page.text[: match.start()]))
                found.append((page.page_number, offset, f"FACTOR-{match.group(1)}"))
        if found:
            found.sort()
            anchors[file.file_id] = found
    return anchors


def _page_text_index(document_map: DocumentMap) -> dict[tuple[str, int], str]:
    """Normalized text of every ok page, keyed by ``(file_id, page_number)``."""
    index: dict[tuple[str, int], str] = {}
    for file in document_map.files:
        if file.parse_status != "ok":
            continue
        for page in file.pages:
            if page.quality == "ok" and page.text:
                index[(file.file_id, page.page_number)] = normalize(page.text)
    return index


def assign_factors(
    requirements: Iterable[Requirement],
    anchors: dict[str, list[tuple[int, int, str]]],
    document_map: DocumentMap | None = None,
) -> dict[str, str]:
    """Map requirement_id -> factor id, omitting rows that precede any heading.

    A requirement's position is found by locating its verbatim span in its own
    page's normalized text — the same frame the anchors use. Without
    ``document_map`` the comparison degrades to page granularity, and a row
    sharing a page with a heading is left unassigned rather than guessed.

    Absence is meaningful and is represented by absence: Section L rows and the
    Section M "basis for award" preamble genuinely belong to no factor, and
    inventing one for them would create false counterpart links — the exact
    failure this module exists to prevent.
    """
    pages = _page_text_index(document_map) if document_map is not None else {}
    out: dict[str, str] = {}
    for req in requirements:
        ref = req.source_ref
        file_anchors = anchors.get(ref.file_id)
        if not file_anchors or ref.page is None:
            continue

        page_text = pages.get((ref.file_id, ref.page))
        offset: int | None = None
        if page_text is not None:
            found = page_text.find(normalize(req.verbatim_text))
            offset = found if found >= 0 else None

        current: str | None = None
        for page, char, factor in file_anchors:
            if page < ref.page:
                current = factor
            elif page == ref.page:
                # Same page: only an offset can order them. Unknown offset means
                # unknown order, and a guess here is a mis-filed requirement.
                if offset is None:
                    current = None
                    break
                if char <= offset:
                    current = factor
            else:
                break
        if current is not None:
            out[req.requirement_id] = current
    return out


def factor_coverage(assignments: dict[str, str], total: int) -> dict[str, int]:
    """Counts per factor plus the unanchored remainder."""
    counts: dict[str, int] = {}
    for factor in assignments.values():
        counts[factor] = counts.get(factor, 0) + 1
    counts["no factor"] = max(total - len(assignments), 0)
    return counts
