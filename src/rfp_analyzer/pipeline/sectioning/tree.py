"""TOC disambiguation and the section tree builder.

Consumes :func:`~rfp_analyzer.pipeline.sectioning.headings.find_heading_candidates`
output over a quality-cleaned :class:`~rfp_analyzer.pipeline.models.ParsedFile`
and emits :class:`~rfp_analyzer.pipeline.models.SectionNode` trees with
``PageSpan`` locators (PDF) or ``BlockSpan`` locators (DOCX — never
synthesized page numbers).

TOC disambiguation (RESEARCH Pattern 3, Pitfall 1): the SF33 Block 9 / TOC
page lists every section title on one page — a page is treated as a TOC when
it has >= :data:`TOC_MIN_DISTINCT_HEADINGS` distinct top-level section-letter
headings, OR a majority of its (2+) heading lines end in a dot-leader /
trailing page-number pattern. TOC pages never seed section starts.

Start-page rule (assumption A7, corpus-tunable): a section starts on the
page where its heading appears as a leading line on a non-TOC page,
preferring the LAST such occurrence that still precedes at least one
subsequent distinct section heading; when no occurrence qualifies (e.g. the
final section), the first occurrence wins. Last-wins guards against
contents-style listing pages that fall under the TOC threshold (the page-1
TOC proper is already excluded before occurrences are built).

Last-wins cannot guard against mid-document cross-references — it actively
prefers them — so those are filtered out beforehand instead: a ``SECTION X``
match whose captured title reads on as prose ("SECTION L *of this
solicitation is amended as follows*") is a sentence about the section, not
its heading, and never becomes an occurrence.

Honesty invariant (success criterion 2): a node is only ever emitted for a
matched signal — a file with zero heading candidates returns an empty list,
and scanned pages (``text == ""``) contribute no candidates.
"""

import re
from dataclasses import dataclass

from rfp_analyzer.pipeline.models import BlockSpan, PageSpan, ParsedFile, SectionNode
from rfp_analyzer.pipeline.sectioning.headings import HeadingCandidate, find_heading_candidates

TOC_MIN_DISTINCT_HEADINGS = 4
"""A page with at least this many distinct section-letter headings is a TOC
page even without dot leaders (A7 — corpus-tunable)."""

LEADING_LINE_LIMIT = 10
"""A top-level section heading must appear within the first this-many lines
of its page to count as a section start (A7 — corpus-tunable)."""

_TOC_TRAILING_RE = re.compile(r"(\.{3,}\s*\d{1,4}|\s\d{1,4})\s*$")
"""Dot-leader (``... 40``) or trailing standalone page-number TOC-line tails."""

_CROSS_REFERENCE_TAIL_RE = re.compile(
    r"^(?:,"
    r"|OF|IS|ARE|WAS|WERE|WILL|SHALL|MAY|HAS|HAVE|HEREBY"
    r"|ABOVE|BELOW|AND|TO|IN|THEREOF|ENTITLED"
    r")\b"
)
"""A ``SECTION X`` match whose captured title reads on as prose is a
cross-reference sentence ("SECTION L *of this solicitation is amended as
follows*"), not a section start (A7 — corpus-tunable). Anchored alternation
of bare literals: no nesting, no unbounded quantifier (T-01-12)."""

CANONICAL_LETTER_ROLES: dict[str, str] = {
    "C": "sow_pws",
    "H": "special_requirements",
    "I": "clauses",
    "J": "attachments_list",
    "L": "instructions",
    "M": "evaluation",
}
"""FAR 15.204-1 canonical roles per UCF section letter (fallback when the
heading's own title text does not carry a role title)."""


@dataclass(frozen=True)
class _Occurrence:
    """One heading candidate located at a comparable document position.

    ``pos`` is ``(page_number, line_index)`` for PDFs and
    ``(block_ordinal, line_index)`` for DOCX; ``pos[0]`` is the span unit.
    """

    pos: tuple[int, int]
    candidate: HeadingCandidate


def _is_cross_reference(candidate: HeadingCandidate) -> bool:
    """True when a letter-section heading match is really prose about it.

    ``SECTION L of this solicitation is amended as follows`` is line-start
    anchored and matches SECTION_HEADING with the whole sentence tail
    captured as the "title". Left in, it competes with the real heading for
    the section start — and since the start rule prefers the LAST qualifying
    occurrence, the cross-reference wins and the section's span and title
    both come out wrong.
    """
    return bool(candidate.letter) and bool(_CROSS_REFERENCE_TAIL_RE.match(candidate.title))


def _is_toc_page(candidates: list[HeadingCandidate]) -> bool:
    letters = [c for c in candidates if c.signal == "heading" and c.letter]
    if len({c.letter for c in letters}) >= TOC_MIN_DISTINCT_HEADINGS:
        return True
    if len(letters) >= 2:
        trailing = sum(1 for c in letters if _TOC_TRAILING_RE.search(c.title))
        return trailing * 2 > len(letters)
    return False


def _pdf_page_candidates(file: ParsedFile) -> dict[int, list[HeadingCandidate]]:
    return {
        page.page_number: find_heading_candidates(page.text) for page in file.pages if page.text
    }


def find_toc_pages(file: ParsedFile) -> list[int]:
    """Page numbers of TOC pages in a parsed PDF (always [] for DOCX)."""
    if file.file_type != "pdf":
        return []
    return sorted(
        number for number, cands in _pdf_page_candidates(file).items() if _is_toc_page(cands)
    )


def _choose_start(occs: list[_Occurrence], all_letter_occs: list[_Occurrence]) -> _Occurrence:
    """A7 start rule over one letter's sorted occurrences.

    Cross-reference occurrences are already filtered out by
    :func:`_is_cross_reference` before this runs, so "last qualifying" here
    only ever chooses between plausible real headings.
    """
    qualifying = [
        occ
        for occ in occs
        if any(
            other.candidate.letter != occ.candidate.letter and other.pos > occ.pos
            for other in all_letter_occs
        )
    ]
    return qualifying[-1] if qualifying else occs[0]


def _assemble_paragraph_nodes(
    entries: list[_Occurrence],
    parent_end_unit: int,
    make_locator,
) -> list[SectionNode]:
    """Nest sorted same-letter paragraph occurrences by dotted-component depth."""
    nodes: list[SectionNode] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        depth = len(entry.candidate.components)
        j = i + 1
        while j < len(entries) and len(entries[j].candidate.components) > depth:
            j += 1
        end_unit = entries[j].pos[0] - 1 if j < len(entries) else parent_end_unit
        end_unit = max(end_unit, entry.pos[0])
        nodes.append(
            SectionNode(
                label=entry.candidate.label,
                title=entry.candidate.title,
                role=None,
                locator=make_locator(entry.pos[0], end_unit),
                detection="paragraph_numbering",
                children=_assemble_paragraph_nodes(entries[i + 1 : j], end_unit, make_locator),
            )
        )
        i = j
    return nodes


def _build_tree(
    heading_occs: list[_Occurrence],
    role_occs: list[_Occurrence],
    para_occs: list[_Occurrence],
    last_unit: int,
    make_locator,
) -> list[SectionNode]:
    """Shared tree assembly over comparable positions (pages or blocks)."""
    letter_occs = [o for o in heading_occs if o.candidate.letter]

    starts: list[_Occurrence] = []
    for letter in {o.candidate.letter for o in letter_occs}:
        occs = [o for o in letter_occs if o.candidate.letter == letter]
        starts.append(_choose_start(occs, letter_occs))
    starts.sort(key=lambda o: o.pos)

    sections: list[SectionNode] = []
    for idx, occ in enumerate(starts):
        start_unit = occ.pos[0]
        if idx + 1 < len(starts):
            end_unit = max(starts[idx + 1].pos[0] - 1, start_unit)
        else:
            end_unit = max(last_unit, start_unit)
        letter = occ.candidate.letter or ""
        children_entries = sorted(
            (
                o
                for o in para_occs
                if o.candidate.letter == letter and occ.pos <= o.pos and o.pos[0] <= end_unit
            ),
            key=lambda o: o.pos,
        )
        sections.append(
            SectionNode(
                label=letter,
                title=occ.candidate.title,
                role=occ.candidate.role or CANONICAL_LETTER_ROLES.get(letter),
                locator=make_locator(start_unit, end_unit),
                detection="heading",
                children=_assemble_paragraph_nodes(children_entries, end_unit, make_locator),
            )
        )

    if sections:
        return sections

    # No letter sections: role-title nodes are the honest top level (e.g. a
    # "Proposal Submission Instructions" attachment — Pitfall 3).
    role_sorted = sorted(role_occs, key=lambda o: o.pos)
    role_nodes: list[SectionNode] = []
    for idx, occ in enumerate(role_sorted):
        start_unit = occ.pos[0]
        if idx + 1 < len(role_sorted):
            end_unit = max(role_sorted[idx + 1].pos[0] - 1, start_unit)
        else:
            end_unit = max(last_unit, start_unit)
        role_nodes.append(
            SectionNode(
                label=occ.candidate.label,
                title=occ.candidate.title,
                role=occ.candidate.role,
                locator=make_locator(start_unit, end_unit),
                detection="role_title",
                children=[],
            )
        )
    return role_nodes


def build_section_tree(file: ParsedFile) -> list[SectionNode]:
    """Detected section hierarchy for one parsed file (may be empty).

    PDF: candidates come from per-page cleaned text; TOC pages are excluded;
    top-level headings must be leading lines (A7). DOCX: candidates come
    from block text — style names are unreliable in federal documents
    (Pitfall 4), so text heuristics run on every block regardless of style,
    with TOC-style lines (dot leaders / trailing page numbers) skipped.
    Never emits a node without a matched signal.
    """
    if file.parse_status != "ok":
        return []

    if file.file_type == "pdf":
        by_page = _pdf_page_candidates(file)
        toc_pages = {number for number, cands in by_page.items() if _is_toc_page(cands)}
        heading_occs: list[_Occurrence] = []
        role_occs: list[_Occurrence] = []
        para_occs: list[_Occurrence] = []
        for number, cands in by_page.items():
            if number in toc_pages:
                continue
            for cand in cands:
                if _is_cross_reference(cand):
                    continue  # prose about a section, not the section itself
                occ = _Occurrence(pos=(number, cand.line_index), candidate=cand)
                if cand.signal == "heading" and cand.line_index < LEADING_LINE_LIMIT:
                    heading_occs.append(occ)
                elif cand.signal == "role_title" and cand.line_index < LEADING_LINE_LIMIT:
                    role_occs.append(occ)
                elif cand.signal == "paragraph_numbering":
                    para_occs.append(occ)
        last_unit = file.page_count or max((p.page_number for p in file.pages), default=0)
        return _build_tree(
            heading_occs,
            role_occs,
            para_occs,
            last_unit,
            lambda start, end: PageSpan(page_start=start, page_end=end),
        )

    if file.file_type == "docx":
        heading_occs = []
        role_occs = []
        para_occs = []
        for block in file.blocks:
            if block.kind != "paragraph" or not block.text:
                continue
            for cand in find_heading_candidates(block.text):
                if _is_cross_reference(cand):
                    continue  # prose about a section, not the section itself
                if cand.signal == "heading" and _TOC_TRAILING_RE.search(cand.title):
                    continue  # Word-generated TOC line, not a section start
                occ = _Occurrence(pos=(block.ordinal, cand.line_index), candidate=cand)
                if cand.signal == "heading":
                    heading_occs.append(occ)
                elif cand.signal == "role_title":
                    role_occs.append(occ)
                else:
                    para_occs.append(occ)
        last_unit = max((b.ordinal for b in file.blocks), default=0)
        return _build_tree(
            heading_occs,
            role_occs,
            para_occs,
            last_unit,
            lambda start, end: BlockSpan(block_start=start, block_end=end),
        )

    return []
