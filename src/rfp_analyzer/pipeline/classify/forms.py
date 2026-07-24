"""SF form-page signatures, the SF30 amendment ladder, and doc-role assignment.

Implements RESEARCH Pattern 4: SF33/SF1449/SF30 all have verified, greppable
first-page titles; FAR 12.603 combined synopsis/solicitations use *no form
at all* — text markers are the only signal for them.

SF30 detection ladder (Pitfall 5 — a scanned SF30 must never silently pass
as a plain attachment):

1. Page-1 SF30 title text → ``amendment`` with evidence ``form_text``;
   amendment number extracted near the Block 2 label (``None`` accepted).
2. No page-1 text layer AND the filename matches amendment patterns →
   ``amendment`` with evidence ``filename`` (rendered downstream as
   "unverified — scanned, matched by filename"; T-01-13: this rung fires
   ONLY when there is no text layer, and form-text evidence always wins).
3. Neither → ``base_solicitation`` when SF33/SF1449 matched (or the file
   carries FAR 12.603 combined-synopsis markers — the notice text IS the
   solicitation), else ``attachment``.
"""

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Literal

from rfp_analyzer.pipeline.models import ParsedFile

FormName = Literal["sf33", "sf1449", "sf30"]

FORM_SIGNATURES: list[tuple[FormName, str]] = [
    ("sf33", "SOLICITATION, OFFER AND AWARD"),
    ("sf1449", "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES"),
    # Pre-2021 FAR rewrite title revision — both variants must match.
    ("sf1449", "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL ITEMS"),
    ("sf30", "AMENDMENT OF SOLICITATION/MODIFICATION OF CONTRACT"),
]
"""Normalized (whitespace-collapsed, slash-tightened, uppercased) page-1
title substrings per RESEARCH Pattern 4's verified table."""

COMBINED_SYNOPSIS_MARKERS: list[str] = [
    "COMBINED SYNOPSIS/SOLICITATION",
    "SUBPART 12.6",
    "FAR 12.603",
]
"""FAR 12.603 packages use NO form — these text markers are the only signal."""

AMENDMENT_FILENAME_RE = re.compile(
    r"""
    (?:
        sf[\s_-]?30                          # sf30, SF-30, sf_30
      | amend                                # amendment, amend_01
      | amdt                                 # amdt2
      | (?:^|[\s_-]) mod (?=[\s_-]|\d|$)     # mod_3 (bounded: not "model")
      | (?:^|[\s_-]) [ap]?\d{4,6} (?=[\s_-]|$)  # 0001 / P00001 / A00002 suffixes
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
"""Amendment-style filename tokens for ladder rung 2. Applied to the stem
(no extension). Attacker-controlled filenames only ever produce an
explicitly unverified ``filename``-evidence label (T-01-13)."""

_AMENDMENT_NUMBER_RE = re.compile(
    r"AMENDMENT/MODIFICATION\s+NO\.?\s*:?\s*([A-Z0-9][A-Z0-9-]{0,19})"
)
"""Amendment number token near the SF30 Block 2 label (Open Question 3),
matched against normalized text."""


@dataclass(frozen=True)
class FormMatch:
    """A recognized SF form title on a file's first page."""

    form: FormName
    signature: str
    source: Literal["text", "layout_text"]


def _normalize(s: str) -> str:
    """Whitespace-collapse, tighten slashes, and uppercase for matching."""
    return re.sub(r"\s*/\s*", "/", " ".join(s.split()).upper())


def _page1_text(file: ParsedFile) -> str:
    """Default-mode first-page text (PDF) or leading block text (DOCX)."""
    if file.file_type == "pdf":
        return file.pages[0].text if file.pages else ""
    if file.file_type == "docx":
        return "\n".join(b.text for b in file.blocks if b.ordinal < 40 and b.text)
    return ""


def _has_page1_text(file: ParsedFile) -> bool:
    return bool(_page1_text(file).strip()) or bool((file.first_page_layout_text or "").strip())


def detect_form(file: ParsedFile) -> FormMatch | None:
    """Recognized SF form on page 1, or None.

    Matches against whitespace-collapsed page-1 text first; falls back to
    layout-mode text (``first_page_layout_text``) because form layouts split
    titles across extracted words (RESEARCH Pattern 4 note).
    """
    for source, raw in (
        ("text", _page1_text(file)),
        ("layout_text", file.first_page_layout_text or ""),
    ):
        normalized = _normalize(raw)
        if not normalized:
            continue
        for form, signature in FORM_SIGNATURES:
            if signature in normalized:
                return FormMatch(form=form, signature=signature, source=source)  # type: ignore[arg-type]
    return None


def detect_combined_synopsis(file: ParsedFile) -> str | None:
    """First matched FAR 12.603 combined-synopsis marker, or None."""
    for raw in (_page1_text(file), file.first_page_layout_text or ""):
        normalized = _normalize(raw)
        for marker in COMBINED_SYNOPSIS_MARKERS:
            if marker in normalized:
                return marker
    return None


def _extract_amendment_number(file: ParsedFile) -> str | None:
    for raw in (_page1_text(file), file.first_page_layout_text or ""):
        m = _AMENDMENT_NUMBER_RE.search(_normalize(raw))
        if m:
            return m.group(1)
    return None


def assign_doc_role(file: ParsedFile) -> ParsedFile:
    """Assign ``doc_role`` (and amendment fields) via the Pattern 4 ladder."""
    if file.parse_status != "ok":
        return file

    match = detect_form(file)

    # Rung 1: SF30 title text — form-text evidence always wins.
    if match is not None and match.form == "sf30":
        file.doc_role = "amendment"
        file.amendment_evidence = "form_text"
        file.amendment_number = _extract_amendment_number(file)
        return file

    # Rung 2: no page-1 text layer (scanned SF30 specimen) + filename match.
    if not _has_page1_text(file) and AMENDMENT_FILENAME_RE.search(PurePath(file.filename).stem):
        file.doc_role = "amendment"
        file.amendment_evidence = "filename"
        return file

    # Rung 3: not an amendment.
    if match is not None:  # sf33 or sf1449
        file.doc_role = "base_solicitation"
    elif detect_combined_synopsis(file) is not None:
        # FAR 12.603: the notice text IS the solicitation.
        file.doc_role = "base_solicitation"
    else:
        file.doc_role = "attachment"
    return file
