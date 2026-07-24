"""UCF heading signals: regexes, role titles, and per-page candidate scan.

Implements RESEARCH Pattern 3's three signal classes as pure functions over
page text (no file I/O):

1. Heading regexes — ``SECTION L``, ``PART I—THE SCHEDULE`` (line-start
   anchored, case/dash/colon tolerant).
2. Paragraph numbering — ``L.1``, ``L.4.2`` leading-position paragraph IDs.
3. Role titles — official FAR 15.204-1 section titles (plus the
   attachment-style "PROPOSAL SUBMISSION INSTRUCTIONS") mapped to
   :class:`~rfp_analyzer.pipeline.models.SectionNode` role values, so a
   package whose instructions live in an attachment titled "Proposal
   Submission Instructions" still gets role-tagged (Pitfall 3).

Assumption A5: the exact heading forms encoded here are hypotheses — the
3-package corpus (plan 01-06) exists to falsify and tune them.

Threat note (T-01-12): all patterns are line-anchored with bounded
quantifiers (``.{0,120}`` / ``.{0,80}`` caps, bounded digit runs) — no
nested unbounded groups, so hostile text cannot trigger catastrophic
backtracking. Task 1's adversarial timing test enforces this.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

SECTION_HEADING = re.compile(
    r"^\s*SECTION\s+([A-M])\b\s*[—–\-:.]?\s*(.{0,120})$",
    re.IGNORECASE | re.MULTILINE,
)
"""``SECTION L - TITLE`` style headings (A5). Group 1 = section letter,
group 2 = trailing title text (bounded at 120 chars)."""

PART_HEADING = re.compile(
    r"^\s*PART\s+(I{1,3}|IV)\b\s*[—–\-:.]?\s*(.{0,80})$",
    re.IGNORECASE | re.MULTILINE,
)
"""``PART I—THE SCHEDULE`` .. ``PART IV`` UCF part headings (A5). Group 1 =
roman numeral, group 2 = trailing title (bounded at 80 chars)."""

PARA_NUMBER = re.compile(r"^\s*([A-M])((?:\.\d{1,4}){1,6})\b", re.MULTILINE)
"""Leading-position paragraph IDs: ``L.1``, ``L.4.2``, ``M.3.1.2`` (A5).
Group 1 = section letter, group 2 = dotted numeric tail (bounded: at most
six components of at most four digits each)."""

ROLE_TITLES: dict[str, str] = {
    # Official FAR 15.204-1 section titles (RESEARCH Pattern 3).
    "INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS": "instructions",
    "EVALUATION FACTORS FOR AWARD": "evaluation",
    "STATEMENT OF WORK": "sow_pws",
    "PERFORMANCE WORK STATEMENT": "sow_pws",
    "SPECIAL CONTRACT REQUIREMENTS": "special_requirements",
    # Attachment-style title with no "SECTION L" literal (Pitfall 3).
    "PROPOSAL SUBMISSION INSTRUCTIONS": "instructions",
}
"""Normalized title substrings -> SectionNode.role values."""

ROLE_LABELS: dict[str, str] = {
    "instructions": "INSTRUCTIONS",
    "evaluation": "EVALUATION",
    "sow_pws": "SOW",
    "special_requirements": "SPECIAL REQS",
}
"""Honest labels for role-title-only nodes (no fabricated section letters)."""

_DASHES = str.maketrans({"–": "-", "—": "-"})

Signal = Literal["heading", "role_title", "paragraph_numbering"]


def normalize_line(s: str) -> str:
    """Fold a physical line to its matching form.

    Collapses whitespace runs to single spaces, unifies en/em dashes to
    ``-``, uppercases, and strips (RESEARCH Pattern 3 normalization note).
    """
    return " ".join(s.translate(_DASHES).split()).upper()


def match_role_title(line: str) -> str | None:
    """Role for a line matching a known section role title, else None.

    Substring match against the normalized line, so mixed case and wrapped
    whitespace survive.
    """
    normalized = normalize_line(line)
    if not normalized:
        return None
    for title, role in ROLE_TITLES.items():
        if title in normalized:
            return role
    return None


@dataclass(frozen=True)
class HeadingCandidate:
    """One heading-signal match on a single line of page/block text."""

    line_index: int
    signal: Signal
    label: str
    title: str
    letter: str | None = None
    components: tuple[int, ...] = field(default=())
    role: str | None = None


def find_heading_candidates(page_text: str) -> list[HeadingCandidate]:
    """Scan normalized lines of one page's text for heading signals.

    Returns every match with its signal class, in line order. Per-line
    priority: SECTION heading > PART heading > paragraph numbering > role
    title (a line yields at most one candidate). Empty text yields an
    empty list — scanned pages (``text == ""``) contribute nothing.
    """
    candidates: list[HeadingCandidate] = []
    for index, raw_line in enumerate(page_text.splitlines()):
        line = normalize_line(raw_line)
        if not line:
            continue

        m = SECTION_HEADING.match(line)
        if m:
            letter = m.group(1).upper()
            title = m.group(2).strip()
            candidates.append(
                HeadingCandidate(
                    line_index=index,
                    signal="heading",
                    label=letter,
                    title=title,
                    letter=letter,
                    role=match_role_title(title),
                )
            )
            continue

        m = PART_HEADING.match(line)
        if m:
            numeral = m.group(1).upper()
            candidates.append(
                HeadingCandidate(
                    line_index=index,
                    signal="heading",
                    label=f"PART {numeral}",
                    title=m.group(2).strip(),
                )
            )
            continue

        m = PARA_NUMBER.match(line)
        if m:
            letter = m.group(1).upper()
            components = tuple(int(part) for part in m.group(2).split(".") if part)
            candidates.append(
                HeadingCandidate(
                    line_index=index,
                    signal="paragraph_numbering",
                    label=f"{letter}{m.group(2)}",
                    title=line[m.end() :].strip(),
                    letter=letter,
                    components=components,
                )
            )
            continue

        role = match_role_title(line)
        if role:
            candidates.append(
                HeadingCandidate(
                    line_index=index,
                    signal="role_title",
                    label=ROLE_LABELS[role],
                    title=line,
                    role=role,
                )
            )
    return candidates
