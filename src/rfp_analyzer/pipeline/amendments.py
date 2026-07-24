"""SF30 amendment change detection — flag, never merge (INTK-03).

RESEARCH Pattern 7. Amendment files are already labeled ``doc_role="amendment"``
upstream; their requirements carry that provenance on ``source_ref.doc_role``.
``flag_amendments`` gates candidate change statements on that field FIRST — only
amendment-sourced requirements are ever tested for change language, so a base
solicitation's FAR clauses ("...is added in full text...", "...in lieu of the
clause at 52.212-4...") can never be false-flagged (success criterion 4 /
T-02-08). The doc_role gate, not the change-verb regex, is what makes the
decision safe.

A flagged change statement that names a base section (e.g. "Section L.4.2 is
changed to read...") attaches a soft ``affects`` back-pointer to the base
requirements in that section and sets their ``possibly_modified=True``. Both the
change row and the affected base rows are always retained — no automated merge
(explicitly out of scope per REQUIREMENTS.md). Recovering the SF30 Block 2
amendment number via AcroForm is out of scope here (RESEARCH Open Question 3);
``amendment_number=None`` remains an honest outcome and change rows stay valid.
"""

import re

from rfp_analyzer.pipeline.models import Requirement

_CHANGE = re.compile(
    r"is\s+(?:hereby\s+)?(?:changed|revised|amended|deleted|added|replaced)"
    r"|delete[sd]?\b.*?\b(?:insert|substitut)"
    r"|in\s+lieu\s+of"
    r"|is\s+changed\s+to\s+read",
    re.IGNORECASE | re.DOTALL,
)
"""Amendment change-verb family (RESEARCH Pattern 7). Matching is necessary but
NOT sufficient — the doc_role gate in ``flag_amendments`` is the real guard."""

_SECTION_REF = re.compile(
    r"\b(?:Section|Clause|Paragraph|Provision)\s+([A-Z](?:\.[0-9]+)*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
"""Captures a referenced section/paragraph label (``L.4.2``, ``H.1``, ``M``)."""


def flag_amendments(requirements: list[Requirement]) -> list[Requirement]:
    """Flag amendment change statements and mark affected base rows (INTK-03).

    Mutates and returns the same list: amendment-sourced change statements get
    ``is_amendment_change=True``; base rows in a referenced section get
    ``possibly_modified=True`` and the change's id appended to ``affects``. Row
    count never changes — nothing is merged or deleted.
    """
    changes: list[tuple[Requirement, list[str]]] = []
    for req in requirements:
        # GATE: only amendment-sourced rows are candidate change statements.
        if req.source_ref.doc_role != "amendment":
            continue
        if _CHANGE.search(req.verbatim_text):
            req.is_amendment_change = True
            changes.append((req, _referenced_sections(req.verbatim_text)))

    for change_req, labels in changes:
        if not labels:
            continue
        for target in requirements:
            if target is change_req:
                continue
            target_label = target.source_ref.section_label
            if target_label and any(_section_matches(lbl, target_label) for lbl in labels):
                target.possibly_modified = True
                if change_req.requirement_id not in target.affects:
                    target.affects.append(change_req.requirement_id)

    return requirements


def _referenced_sections(text: str) -> list[str]:
    """Uppercased section labels a change statement references, de-duplicated."""
    seen: list[str] = []
    for m in _SECTION_REF.finditer(text):
        label = m.group(1).upper()
        if label not in seen:
            seen.append(label)
    return seen


def _section_matches(ref_label: str, base_label: str) -> bool:
    """True when a referenced label and a base row's label denote the same locus.

    Exact, or one is a dot-boundary prefix of the other (a change to ``L.4.2``
    reaches ``L.4.2.a`` and a whole-``L`` row; a change to ``L`` reaches
    ``L.4.2``). Comparison is case-insensitive.
    """
    ref = ref_label.upper()
    base = base_label.upper()
    if ref == base:
        return True
    return ref.startswith(base + ".") or base.startswith(ref + ".")
