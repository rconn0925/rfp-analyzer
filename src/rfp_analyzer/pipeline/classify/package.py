"""Package classification: full_ucf / partial_ucf / non_ucf_commercial / unknown.

Aggregates per-file section trees (``ParsedFile.sections``, built by the
sectioning stage) and form signals (:mod:`~rfp_analyzer.pipeline.classify.forms`)
into the honest four-way classification (RESEARCH Pattern 6).

Honesty contract (T-01-14, success criterion 2): every classification
carries non-empty human-readable evidence, and every non-``full_ucf``
outcome carries at least one warning. An empty section tree plus explicit
warnings is a legal answer; a fabricated UCF tree never is.

Open Question 1 rule: form signal and structure signal are independent — an
SF1449/combined-synopsis package WITH detected L/M sections is
``partial_ucf``, never ``non_ucf_commercial``.
"""

from typing import Literal

from rfp_analyzer.pipeline.classify.forms import detect_combined_synopsis, detect_form
from rfp_analyzer.pipeline.models import ParsedFile, SectionNode

Classification = Literal["full_ucf", "partial_ucf", "non_ucf_commercial", "unknown"]

_MISSING_WARNINGS = {
    "L": "No Section L heading found; downstream results may be incomplete.",
    "M": "No Section M heading found; downstream results may be incomplete.",
    "C": "No Section C / SOW / PWS content found; downstream results may be incomplete.",
}


def _span_description(node: SectionNode) -> str:
    locator = node.locator
    if locator.kind == "pages":
        return f"pages {locator.page_start}-{locator.page_end}"
    return f"blocks {locator.block_start}-{locator.block_end}"


def _section_key(node: SectionNode) -> str | None:
    """Map a top-level node to the classification slot it satisfies."""
    if node.label == "L" or node.role == "instructions":
        return "L"
    if node.label == "M" or node.role == "evaluation":
        return "M"
    if node.label == "C" or node.role == "sow_pws":
        return "C"
    return None


def _is_letter_node(node: SectionNode) -> bool:
    return len(node.label) == 1 and "A" <= node.label <= "M"


def classify_package(
    files: list[ParsedFile],
) -> tuple[Classification, list[str], list[str]]:
    """Classify a package from its files' section trees and form signals.

    Returns ``(classification, evidence, warnings)`` — evidence is never
    empty, and warnings are never empty unless the package is ``full_ucf``.
    """
    evidence: list[str] = []
    warnings: list[str] = []

    commercial_signal = False
    for file in files:
        match = detect_form(file)
        if match is not None:
            evidence.append(
                f"{match.form.upper()} title matched on {file.filename} page 1"
                + (" (layout text)" if match.source == "layout_text" else "")
            )
            if match.form == "sf1449":
                commercial_signal = True
        marker = detect_combined_synopsis(file)
        if marker is not None:
            evidence.append(
                f"Combined synopsis/solicitation marker '{marker}' found in {file.filename}"
            )
            commercial_signal = True

    detected: dict[str, list[tuple[ParsedFile, SectionNode]]] = {"L": [], "M": [], "C": []}
    any_letter_sections = False
    for file in files:
        for node in file.sections:
            if _is_letter_node(node):
                any_letter_sections = True
            key = _section_key(node)
            if key is None:
                continue
            detected[key].append((file, node))
            name = (
                f"Section {node.label}"
                if _is_letter_node(node)
                else (f"{node.title or node.label} (role {node.role})")
            )
            evidence.append(f"{name} found at {_span_description(node)} of {file.filename}")

    ucf_structure = any_letter_sections or any(detected.values())
    has = {key: bool(nodes) for key, nodes in detected.items()}

    # Sane-ordering check: L must not start after M within the same file.
    disordered = False
    for file in files:
        starts: dict[str, int] = {}
        for node in file.sections:
            if node.label in ("L", "M") and node.locator.kind == "pages":
                starts[node.label] = node.locator.page_start
        if "L" in starts and "M" in starts and starts["M"] < starts["L"]:
            disordered = True
            warnings.append(
                f"Section M starts before Section L in {file.filename}; "
                "section ordering is not sane UCF order."
            )

    if commercial_signal and not ucf_structure:
        warnings.append(
            "Non-UCF commercial package (SF1449 or FAR 12.603 combined synopsis); "
            "no Section L/M/C structure exists to extract — matrix columns that "
            "depend on UCF sections will be incomplete."
        )
        return "non_ucf_commercial", evidence, warnings

    if commercial_signal and ucf_structure:
        warnings.append(
            "Commercial-form signal (SF1449/combined synopsis) found alongside "
            "detected UCF sections; classifying partial_ucf — form and structure "
            "signals are independent (verify package format)."
        )
        warnings.extend(_MISSING_WARNINGS[key] for key in ("L", "M", "C") if not has[key])
        return "partial_ucf", evidence, warnings

    if has["L"] and has["M"] and has["C"]:
        if disordered:
            return "partial_ucf", evidence, warnings
        return "full_ucf", evidence, warnings

    if any(has.values()):
        warnings.extend(_MISSING_WARNINGS[key] for key in ("L", "M", "C") if not has[key])
        return "partial_ucf", evidence, warnings

    if ucf_structure:
        # Letter sections exist but none of L/M/C — still partial evidence.
        warnings.extend(_MISSING_WARNINGS[key] for key in ("L", "M", "C"))
        return "partial_ucf", evidence, warnings

    evidence.append(
        f"No UCF section headings and no recognized form pages found across {len(files)} file(s)"
    )
    warnings.append(
        "Package structure unrecognized; downstream extraction has no section anchors to work from."
    )
    return "unknown", evidence, warnings
