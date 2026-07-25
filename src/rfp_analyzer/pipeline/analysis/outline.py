"""The proposal outline, derived from the RFP's own structure (ANLZ-02).

A compliance matrix is only actionable if every requirement points at the place
in *your* proposal where it gets answered. That outline is not invented: a
federal solicitation already dictates it, in two layers.

- **Section L's subsection tree** (L.1 Contractor Proposal Certification, L.3
  Inquiries, L.5 Content of Proposal…) is the instruction skeleton, and Phase 1
  already detected it.
- **The evaluation factors** ("Factor 1 - Management Approach", "Factor 2 -
  Corporate Experience"…) are how the proposal must actually be tabbed and how
  it will be scored. This RFP says so directly: "Include only information in
  response to Factors 1, 2, and 3 separated by tabs."

Factors are therefore the load-bearing nodes and Section L subsections are the
scaffolding around them. Both come from the document; nothing here is invented,
and requirements that fit nowhere land in an explicit ``UNASSIGNED`` node rather
than disappearing — an unplaced requirement is a finding, not a rounding error.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rfp_analyzer.pipeline.models import DocumentMap, OutlineNode, Requirement

UNASSIGNED_ID = "UNASSIGNED"
"""Node for requirements no rule could place.

Exists so "every requirement is mapped" is literally true without pretending.
A silently dropped requirement is the failure mode this whole product exists to
prevent, so an unplaceable row stays visible and countable.
"""

EVAL_CRITERIA_ID = "EVAL-CRITERIA"
"""Node for Government evaluation criteria — reference, not proposal content.

"Price is evaluated on total price" is a real, useful matrix row: a writer needs
to know how the work is scored. But nobody writes it into a volume, so filing it
under a proposal section would be a lie about what the row is for.
"""

POST_AWARD_ID = "POST-AWARD"
"""Node for SOW/PWS performance obligations that are not proposal content.

A statement of work duty ("Provide janitorial services for the facilities") is a
real requirement, but it is not something you WRITE in a volume — you perform it
after award. Filing those under a proposal section would be wrong, and dumping
them in UNASSIGNED would bury the genuinely unplaceable rows among 137 correctly
handled ones. They get their own honest destination.
"""

NON_PRICE_VOLUME = "Non-Price Proposal"
PRICE_VOLUME = "Price Proposal"

_FACTOR = re.compile(
    r"Factor\s+(\d+)\s*[-–—:]\s*([A-Z][A-Za-z][A-Za-z /&'-]{2,40})",
)
"""Matches the RFP's own factor declarations, e.g. "Factor 2 - Corporate Experience".

Requires a capitalised title so prose references ("submitted under Factor 2,
Corporate Experience") do not mint duplicate nodes with truncated titles.
"""

_PERFORMANCE_TYPES = {"sow_pws", "special_requirements", "clause", "attachment"}
"""Requirement types that are performed after award rather than written into a
proposal volume."""

_PRICE_HINTS = re.compile(
    r"\b(price|pricing|cost|CLIN|SF1449|invoice|exhibit line item)\b", re.IGNORECASE
)


def _section_text(document_map: DocumentMap, letters: tuple[str, ...]) -> str:
    """Concatenated ok-page text of the named top-level sections, across files."""
    parts: list[str] = []
    for file in document_map.files:
        if file.parse_status != "ok":
            continue
        pages = {p.page_number: p for p in file.pages if p.quality == "ok"}
        for node in file.sections:
            if node.label not in letters:
                continue
            loc = node.locator
            if loc.kind != "pages" or loc.page_start is None:
                continue
            for num in range(loc.page_start, (loc.page_end or loc.page_start) + 1):
                page = pages.get(num)
                if page and page.text:
                    parts.append(page.text)
    return "\n".join(parts)


def discover_factors(document_map: DocumentMap) -> list[tuple[str, str]]:
    """Return ``(number, title)`` for each evaluation factor the RFP declares.

    Read from Sections L and M together: the factor list can be declared in
    either, and this package declares it in M while L points at it.
    """
    text = _section_text(document_map, ("L", "M"))
    seen: dict[str, str] = {}
    for number, title in _FACTOR.findall(text):
        cleaned = " ".join(title.split()).rstrip(" -–—:,")
        # Keep the first (declaration-site) spelling; later prose references are
        # often truncated by a line break.
        if number not in seen or len(cleaned) > len(seen[number]):
            seen[number] = cleaned
    return sorted(seen.items(), key=lambda kv: int(kv[0]))


def derive_outline(document_map: DocumentMap) -> list[OutlineNode]:
    """Build the proposal outline from Section L's tree plus the evaluation factors.

    Shape: two volume roots (non-price / price), the declared factors under the
    non-price volume, every Section L subsection as a node, and ``UNASSIGNED``.
    """
    nodes: list[OutlineNode] = [
        OutlineNode(node_id="VOL-NONPRICE", title=NON_PRICE_VOLUME, volume=NON_PRICE_VOLUME),
        OutlineNode(node_id="VOL-PRICE", title=PRICE_VOLUME, volume=PRICE_VOLUME),
    ]

    for number, title in discover_factors(document_map):
        nodes.append(
            OutlineNode(
                node_id=f"FACTOR-{number}",
                title=f"Factor {number} - {title}",
                volume=NON_PRICE_VOLUME,
                parent_node_id="VOL-NONPRICE",
            )
        )

    # Amendments re-issue Section L, so the same subsection appears in more than
    # one file. De-duplicate by label and prefer the base solicitation, whose
    # numbering is the one a proposal is actually built against.
    seen_labels: set[str] = set()
    files = sorted(
        (f for f in document_map.files if f.parse_status == "ok"),
        key=lambda f: f.doc_role != "base_solicitation",
    )
    for file in files:
        for node in file.sections:
            if node.label != "L":
                continue
            for child in node.children:
                if child.label in seen_labels:
                    continue
                seen_labels.add(child.label)
                loc = child.locator
                is_price = bool(_PRICE_HINTS.search(child.title))
                nodes.append(
                    OutlineNode(
                        node_id=child.label,
                        title=" ".join(child.title.split()).rstrip(":") or child.label,
                        volume=PRICE_VOLUME if is_price else NON_PRICE_VOLUME,
                        parent_node_id="VOL-PRICE" if is_price else "VOL-NONPRICE",
                        source_page=loc.page_start if loc.kind == "pages" else None,
                    )
                )

    nodes.append(
        OutlineNode(
            node_id=EVAL_CRITERIA_ID,
            title="Evaluation criteria — how the Government scores, not proposal content",
            volume="",
        )
    )
    nodes.append(
        OutlineNode(
            node_id=POST_AWARD_ID,
            title="Post-award performance — not proposal content",
            volume="",
        )
    )
    nodes.append(
        OutlineNode(
            node_id=UNASSIGNED_ID,
            title="Unassigned — no outline node matched",
            volume="",
        )
    )
    return nodes


def _factor_matcher(nodes: Iterable[OutlineNode]) -> list[tuple[str, re.Pattern[str]]]:
    """Build (node_id, pattern) pairs matching each factor's distinctive title words."""
    out: list[tuple[str, re.Pattern[str]]] = []
    for node in nodes:
        if not node.node_id.startswith("FACTOR-"):
            continue
        number = node.node_id.split("-", 1)[1]
        title = node.title.split("-", 1)[-1].strip()
        # Match the factor's title words OR an explicit "Factor N" reference —
        # rows like "Limit the Factor 1 narrative to 25 single-sided pages" name
        # the number without repeating the title, and they are exactly the rows a
        # writer needs filed under that factor.
        alts = [re.escape(w) for w in re.findall(r"[A-Za-z]{4,}", title)]
        alts.append(r"Factor\s+" + re.escape(number) + r"(?![0-9])")
        out.append((node.node_id, re.compile("|".join(alts), re.I)))
    return out


def map_requirements(
    requirements: Iterable[Requirement], outline: Iterable[OutlineNode]
) -> dict[str, str]:
    """Map every requirement to an outline node id. Never drops a requirement.

    Resolution order, most specific first:

    1. **Factor keywords** in the requirement text — the proposal is tabbed by
       factor, so this is the placement a writer actually needs.
    2. **Its own Section L subsection** (a requirement in L.3 belongs under L.3).
    3. **Price signals** for price-side obligations that name no factor.
    4. ``POST-AWARD`` for SOW/PWS-type performance duties — real requirements,
       but performed rather than written, so no proposal section owns them.
    5. ``EVAL-CRITERIA`` for Government evaluation actions — reference rows a
       writer needs to see, but not content anyone drafts.
    6. ``UNASSIGNED`` — explicit, so genuinely unplaced rows stay countable.
    """
    nodes = list(outline)
    node_ids = {n.node_id for n in nodes}
    factor_patterns = _factor_matcher(nodes)

    mapping: dict[str, str] = {}
    for req in requirements:
        text = f"{req.verbatim_text} {req.atomic_obligation}"
        placed: str | None = None

        for node_id, pattern in factor_patterns:
            if pattern.search(text):
                placed = node_id
                break

        if placed is None:
            label = req.source_ref.section_label or ""
            if label in node_ids and label != UNASSIGNED_ID:
                placed = label

        if placed is None and _PRICE_HINTS.search(text):
            placed = "VOL-PRICE"

        if placed is None and req.req_type in _PERFORMANCE_TYPES:
            placed = POST_AWARD_ID

        if placed is None and req.req_type == "evaluation":
            placed = EVAL_CRITERIA_ID

        mapping[req.requirement_id] = placed or UNASSIGNED_ID
    return mapping


def outline_coverage(mapping: dict[str, str]) -> dict[str, int]:
    """Count requirements per node id, including ``UNASSIGNED`` — the honesty check."""
    counts: dict[str, int] = {}
    for node_id in mapping.values():
        counts[node_id] = counts.get(node_id, 0) + 1
    return counts
