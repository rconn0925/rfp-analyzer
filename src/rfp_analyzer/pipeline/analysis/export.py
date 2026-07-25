"""Excel workbook and CSV export — the artifact a proposal team actually uses.

EXPT-01..04. Three sheets, because a shred serves three different jobs:

- **Compliance Matrix** — the practitioner-standard row-per-requirement view:
  ID, section, page, verbatim text, the single duty, binding keyword, proposal
  outline location, cross-map disposition, and the compliance verdict.
- **Cross-Reference** — the L/M/SOW linkage and, more importantly, the gaps.
- **Shred Checklist** — the writer's working list: only rows someone must
  actually respond to, with a blank Status/Owner/Notes column set to fill in.

Formatting choices are the ones that make a 277-row sheet usable: frozen header,
autofilter, wrapped verbatim text with generous row height, and conditional
colouring on the verdict column so gaps are visible while scrolling.

Two honesty rules are enforced here rather than left to the reader:

- A row with no recorded verdict says **"NOT JUDGED"**, never an empty cell that
  skims as acceptable.
- A fictional capabilities profile is stamped on every sheet, so an exported
  workbook can never be mistaken for an assessment of a real company.
"""

from __future__ import annotations

import csv
from pathlib import Path

import xlsxwriter

from rfp_analyzer.pipeline.analysis.outline import EVAL_CRITERIA_ID, POST_AWARD_ID
from rfp_analyzer.pipeline.models import ComplianceMatrix

NOT_JUDGED = "NOT JUDGED"

_VERDICT_LABEL = {
    "fully_compliant": "Fully Compliant",
    "partially_compliant": "Partially Compliant",
    "non_compliant": "Non-Compliant",
    "unknown": "Unknown (judge declined)",
}

_GAP_LABEL = {
    "mapped": "Mapped",
    "l_without_m": "GAP: L without M",
    "m_without_l": "GAP: M without L",
    "sow_without_either": "GAP: SOW without L or M",
}

MATRIX_HEADERS = [
    "Requirement ID",
    "Label",
    "Document",
    "Section",
    "Page",
    "Type",
    "Keyword",
    "Requirement (verbatim)",
    "Atomic Obligation",
    "Proposal Location",
    "Cross-Map",
    "Compliance",
    "Confidence",
    "Rationale",
    "Grounded",
]


def _rows(matrix: ComplianceMatrix) -> list[list]:
    """One export row per requirement, in extraction order."""
    judged = {j.requirement_id: j for j in matrix.judgments}
    gaps = {m.requirement_id: m for m in matrix.cross_mappings}
    node_titles = {n.node_id: n.title for n in matrix.outline}

    rows: list[list] = []
    for req in matrix.requirements:
        judgment = judged.get(req.requirement_id)
        gap = gaps.get(req.requirement_id)
        node_id = matrix.requirement_outline.get(req.requirement_id, "")
        rows.append(
            [
                req.requirement_id,
                req.display_label,
                req.source_ref.filename,
                req.source_ref.section_label or "",
                req.source_ref.page if req.source_ref.page is not None else "",
                req.req_type,
                req.binding_keyword,
                " ".join(req.verbatim_text.split()),
                req.atomic_obligation,
                node_titles.get(node_id, node_id),
                _GAP_LABEL.get(gap.gap_kind, "") if gap else "",
                _VERDICT_LABEL[judgment.verdict] if judgment else NOT_JUDGED,
                judgment.confidence if judgment else "",
                judgment.rationale if judgment else "",
                "yes" if req.verified else "NO — ungrounded",
            ]
        )
    return rows


def _profile_banner(matrix: ComplianceMatrix) -> str:
    """The line stamped on every sheet identifying what judged this."""
    if matrix.profile.is_fictional:
        return (
            f"Capabilities profile: {matrix.profile.company_name} — "
            "FICTIONAL DEMO PROFILE. Compliance verdicts are illustrative only and "
            "are NOT an assessment of any real company."
        )
    return f"Capabilities profile: {matrix.profile.company_name}"


def write_workbook(matrix: ComplianceMatrix, path: Path | str) -> Path:
    """Write the three-sheet .xlsx compliance workbook. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(str(path), {"constant_memory": False})

    fmt_title = book.add_format({"bold": True, "font_size": 14})
    fmt_banner = book.add_format({"italic": True, "font_color": "#B00020", "text_wrap": True})
    fmt_header = book.add_format(
        {"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1,
         "text_wrap": True, "valign": "vcenter"}
    )
    fmt_wrap = book.add_format({"text_wrap": True, "valign": "top"})
    fmt_plain = book.add_format({"valign": "top"})

    _matrix_sheet(book, matrix, fmt_title, fmt_banner, fmt_header, fmt_wrap, fmt_plain)
    _crossref_sheet(book, matrix, fmt_title, fmt_header, fmt_wrap, fmt_plain)
    _checklist_sheet(book, matrix, fmt_title, fmt_banner, fmt_header, fmt_wrap, fmt_plain)

    book.close()
    return path


def _matrix_sheet(book, matrix, fmt_title, fmt_banner, fmt_header, fmt_wrap, fmt_plain):
    sheet = book.add_worksheet("Compliance Matrix")
    sheet.write(0, 0, f"Compliance Matrix — {matrix.package_name}", fmt_title)
    sheet.write(1, 0, _profile_banner(matrix), fmt_banner)

    header_row = 3
    for col, name in enumerate(MATRIX_HEADERS):
        sheet.write(header_row, col, name, fmt_header)

    rows = _rows(matrix)
    for r, row in enumerate(rows, start=header_row + 1):
        for c, value in enumerate(row):
            sheet.write(r, c, value, fmt_wrap if c in (7, 8, 13) else fmt_plain)

    widths = [16, 8, 26, 10, 6, 14, 10, 60, 44, 26, 22, 20, 11, 40, 16]
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width)
    sheet.freeze_panes(header_row + 1, 0)
    sheet.autofilter(header_row, 0, header_row + len(rows), len(MATRIX_HEADERS) - 1)

    last = header_row + len(rows)
    compliance_col = MATRIX_HEADERS.index("Compliance")
    for text, colour in (
        ("Non-Compliant", "#FFC7CE"),
        ("Partially Compliant", "#FFEB9C"),
        ("Fully Compliant", "#C6EFCE"),
        (NOT_JUDGED, "#D9D9D9"),
    ):
        sheet.conditional_format(
            header_row + 1, compliance_col, last, compliance_col,
            {"type": "cell", "criteria": "==", "value": f'"{text}"',
             "format": book.add_format({"bg_color": colour})},
        )
    # Ungrounded rows are a data-integrity problem, not a compliance one — flag
    # them in their own column so they cannot hide behind a green verdict.
    grounded_col = MATRIX_HEADERS.index("Grounded")
    sheet.conditional_format(
        header_row + 1, grounded_col, last, grounded_col,
        {"type": "text", "criteria": "begins with", "value": "NO",
         "format": book.add_format({"bg_color": "#FFC7CE", "bold": True})},
    )


def _crossref_sheet(book, matrix, fmt_title, fmt_header, fmt_wrap, fmt_plain):
    sheet = book.add_worksheet("Cross-Reference")
    sheet.write(0, 0, "L / M / SOW Cross-Reference and Gaps", fmt_title)
    sheet.write(
        1, 0,
        "ADVISORY: gap detection is similarity-based and not yet factor-anchored. "
        "Review gaps before acting on them (see crossmap.py STATUS).",
        book.add_format({"italic": True, "font_color": "#B00020", "text_wrap": True}),
    )

    headers = ["Requirement ID", "Section", "Type", "Disposition", "Counterparts",
               "Match Score", "Obligation", "Rationale"]
    header_row = 3
    for col, name in enumerate(headers):
        sheet.write(header_row, col, name, fmt_header)

    by_id = {r.requirement_id: r for r in matrix.requirements}
    # Gaps first — the point of the sheet is what is missing.
    order = {"m_without_l": 0, "l_without_m": 1, "sow_without_either": 2, "mapped": 3}
    mappings = sorted(matrix.cross_mappings, key=lambda m: (order.get(m.gap_kind, 9),
                                                           m.requirement_id))
    for r, mapping in enumerate(mappings, start=header_row + 1):
        req = by_id.get(mapping.requirement_id)
        sheet.write(r, 0, mapping.requirement_id, fmt_plain)
        sheet.write(r, 1, (req.source_ref.section_label or "") if req else "", fmt_plain)
        sheet.write(r, 2, req.req_type if req else "", fmt_plain)
        sheet.write(r, 3, _GAP_LABEL.get(mapping.gap_kind, mapping.gap_kind), fmt_plain)
        sheet.write(r, 4, ", ".join(mapping.counterpart_ids[:5]), fmt_wrap)
        sheet.write(r, 5, round(mapping.score, 1), fmt_plain)
        sheet.write(r, 6, req.atomic_obligation if req else "", fmt_wrap)
        sheet.write(r, 7, mapping.rationale, fmt_wrap)

    for col, width in enumerate([16, 10, 14, 24, 30, 12, 46, 50]):
        sheet.set_column(col, col, width)
    sheet.freeze_panes(header_row + 1, 0)
    sheet.autofilter(header_row, 0, header_row + len(mappings), len(headers) - 1)


def _checklist_sheet(book, matrix, fmt_title, fmt_banner, fmt_header, fmt_wrap, fmt_plain):
    """The writer's working list: only rows someone must actually respond to."""
    sheet = book.add_worksheet("Shred Checklist")
    sheet.write(0, 0, "Shred Checklist — rows requiring a proposal response", fmt_title)
    sheet.write(
        1, 0,
        "Excludes post-award performance duties and Government evaluation criteria; "
        "those are in the Compliance Matrix sheet.",
        fmt_banner,
    )

    headers = ["Requirement ID", "Proposal Location", "Page", "Keyword",
               "Obligation", "Compliance", "Status", "Owner", "Notes"]
    header_row = 3
    for col, name in enumerate(headers):
        sheet.write(header_row, col, name, fmt_header)

    judged = {j.requirement_id: j for j in matrix.judgments}
    node_titles = {n.node_id: n.title for n in matrix.outline}

    count = 0
    for req in matrix.requirements:
        node_id = matrix.requirement_outline.get(req.requirement_id, "")
        if node_id in (POST_AWARD_ID, EVAL_CRITERIA_ID):
            continue
        judgment = judged.get(req.requirement_id)
        r = header_row + 1 + count
        sheet.write(r, 0, req.requirement_id, fmt_plain)
        sheet.write(r, 1, node_titles.get(node_id, node_id), fmt_plain)
        sheet.write(r, 2, req.source_ref.page if req.source_ref.page is not None else "", fmt_plain)
        sheet.write(r, 3, req.binding_keyword, fmt_plain)
        sheet.write(r, 4, req.atomic_obligation, fmt_wrap)
        sheet.write(r, 5, _VERDICT_LABEL[judgment.verdict] if judgment else NOT_JUDGED, fmt_plain)
        sheet.write_blank(r, 6, None, fmt_plain)
        sheet.write_blank(r, 7, None, fmt_plain)
        sheet.write_blank(r, 8, None, fmt_wrap)
        count += 1

    for col, width in enumerate([16, 28, 6, 10, 60, 20, 14, 14, 40]):
        sheet.set_column(col, col, width)
    sheet.freeze_panes(header_row + 1, 0)
    if count:
        sheet.autofilter(header_row, 0, header_row + count, len(headers) - 1)


def write_csv(matrix: ComplianceMatrix, path: Path | str) -> Path:
    """Write the compliance matrix as raw CSV (EXPT-04). Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(MATRIX_HEADERS)
        writer.writerows(_rows(matrix))
    return path
