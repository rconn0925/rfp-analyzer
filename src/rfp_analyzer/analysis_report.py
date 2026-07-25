"""Human-readable report for an analysis run — the `analyze` half of dual output.

Presentation only; no library imports the other way. Leads with the numbers a
proposal manager acts on (gaps, unplaced rows, judgment coverage) and states
absences explicitly, so an unjudged or unmapped run can never be mistaken for a
clean one.
"""

from __future__ import annotations

from rfp_analyzer.pipeline.analysis.crossmap import gap_summary
from rfp_analyzer.pipeline.analysis.judge import judgment_summary
from rfp_analyzer.pipeline.analysis.outline import (
    EVAL_CRITERIA_ID,
    POST_AWARD_ID,
    UNASSIGNED_ID,
    outline_coverage,
)
from rfp_analyzer.pipeline.models import ComplianceMatrix

_GAP_TEXT = {
    "l_without_m": "L without M (instructed but not scored)",
    "m_without_l": "M without L (scored but not instructed)",
    "sow_without_either": "SOW without L or M (performed, never pre-award visible)",
    "evaluation_process": "evaluation mechanics (not a gap)",
}

_VERDICT_TEXT = {
    "fully_compliant": "fully compliant",
    "partially_compliant": "partially compliant",
    "non_compliant": "non-compliant",
    "unknown": "unknown (judge declined)",
    "not_judged": "NOT JUDGED",
}


def render_matrix_report(matrix: ComplianceMatrix) -> str:
    """Render the analysis report for stdout."""
    lines: list[str] = []
    total = len(matrix.requirements)
    lines.append(f"Package: {matrix.package_name}")
    lines.append(f"Requirements analyzed: {total}")

    profile = matrix.profile
    label = " [FICTIONAL DEMO PROFILE]" if profile.is_fictional else ""
    lines.append(f"Profile: {profile.company_name}{label}")

    # Cross-mapping — gaps first, they are the finding.
    gaps = gap_summary(matrix.cross_mappings)
    lines.append("")
    lines.append(f"Cross-mapping (factor-anchored): {gaps.get('mapped', 0)} mapped")
    for kind, text in _GAP_TEXT.items():
        lines.append(f"  {text}: {gaps.get(kind, 0)}")

    # Outline placement — unplaced rows are a finding too.
    coverage = outline_coverage(matrix.requirement_outline)
    unassigned = coverage.get(UNASSIGNED_ID, 0)
    lines.append("")
    lines.append(f"Proposal outline: {len(matrix.outline)} nodes")
    lines.append(
        f"  written into the proposal: "
        f"{total - unassigned - coverage.get(POST_AWARD_ID, 0) - coverage.get(EVAL_CRITERIA_ID, 0)}"
    )
    lines.append(
        f"  post-award performance (not proposal content): {coverage.get(POST_AWARD_ID, 0)}"
    )
    lines.append(f"  evaluation criteria (reference only): {coverage.get(EVAL_CRITERIA_ID, 0)}")
    lines.append(f"  UNASSIGNED (no node matched): {unassigned}")

    # Judgment coverage — "not judged" must never read as "compliant".
    verdicts = judgment_summary(matrix.judgments, total)
    lines.append("")
    lines.append(f"Compliance judgment: {len(matrix.judgments)}/{total} judged")
    for key in ("fully_compliant", "partially_compliant", "non_compliant", "unknown"):
        lines.append(f"  {_VERDICT_TEXT[key]}: {verdicts.get(key, 0)}")
    if verdicts.get("not_judged"):
        lines.append(
            f"  {_VERDICT_TEXT['not_judged']}: {verdicts['not_judged']} "
            "— absent from the matrix, NOT assumed compliant"
        )

    # Grounding integrity carries forward from extraction.
    ungrounded = sum(1 for r in matrix.requirements if not r.verified)
    lines.append("")
    lines.append(f"Grounding: {total - ungrounded}/{total} verified against source pages")
    if ungrounded:
        lines.append(f"  WARNING: {ungrounded} ungrounded row(s) — flagged in the workbook")

    metrics = matrix.metrics
    if metrics.chunks_unextracted:
        lines.append(
            f"  WARNING: extraction covered {metrics.chunks_total - metrics.chunks_unextracted}"
            f"/{metrics.chunks_total} chunks — this matrix is not the whole package"
        )

    timing = "  ".join(f"{name}: {secs:.2f}s" for name, secs in metrics.stage_timings.items())
    if timing:
        lines.append("")
        lines.append(f"Stages: {timing}")
    return "\n".join(lines)
