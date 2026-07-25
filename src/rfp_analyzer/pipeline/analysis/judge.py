"""Graded compliance judgment against a capabilities profile (ANLZ-04).

The one analysis step that needs judgment rather than computation, so the only
one that goes through the engine — and it uses the same file-mediated replay seam
extraction does, for the same reason: Claude Code runs on a personal
subscription, which cannot be called in-process.

    rfp-analyzer judgments <artifacts> --out judgments.jsonl   # what to judge
    (Claude Code reads them and writes verdicts.jsonl)
    rfp-analyzer analyze <artifacts> --verdicts verdicts.jsonl

A recorded verdict file replays to an identical matrix, so a judgment can be
re-derived and argued with rather than re-rolled.

**Unjudged is not the same as compliant.** Rows with no recorded verdict are
simply absent from ``judgments``; the matrix reports judged-vs-total, and the
export shows an explicit "not judged" rather than an empty cell a reader would
skim past as fine. This is the failure mode that matters most here: a proposal
team that believes it is compliant because nobody looked.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    ComplianceJudgment,
    Requirement,
)

DEMO_PROFILE = CapabilityProfile(
    profile_id="demo-fictional",
    company_name="Beaufort Facility Partners LLC (FICTIONAL)",
    is_fictional=True,
    narrative=(
        "A fictional mid-size facilities services contractor used to demonstrate "
        "compliance judgment. Nothing here describes a real company, and no verdict "
        "produced against this profile is an assessment of anyone's real capability."
    ),
    capabilities=[
        "CAP-01 Base operations support on DoD installations, 12 years, 3 prior NAVFAC contracts",
        "CAP-02 Facility investment and recurring maintenance, annual value $8M-$14M",
        "CAP-03 Electrical maintenance with licensed journeyman electricians on staff",
        "CAP-04 Base support vehicle and equipment (BSVE) fleet maintenance",
        "CAP-05 ISO 9001-aligned quality management system with a dedicated Quality Manager",
        "CAP-06 Safety program with a full-time SSHO; DART 1.4 and TCR 2.9 over the last 5 CY",
        "CAP-07 Active SAM registration, current FAPIIS, VETS-4212 filed for the 2025 cycle",
        "CAP-08 CMMC Level 2 assessment complete with SPRS registration and a current CMMC UID",
        "CAP-09 Phase-in experience: 4 transitions completed within a 90-day window",
        "CAP-10 CPARS Very Good overall quality on the two most recent BOS contracts",
        "NO-CAP Pest control is subcontracted; no in-house pest control license",
        "NO-CAP No prior contract above $20M annual value",
    ],
)
"""A deliberately mixed fictional profile.

It has real gaps (no in-house pest control, no contract above $20M) so the demo
produces genuine partially- and non-compliant verdicts. A profile that satisfied
everything would make the judgment column look impressive and prove nothing.
"""


class CorruptVerdictsError(ValueError):
    """The verdicts file is malformed. Fails the run rather than silently under-judging."""


def judgment_tasks(
    requirements: Iterable[Requirement], profile: CapabilityProfile
) -> list[dict]:
    """Build the judging worklist: one record per requirement, plus the profile.

    Carries the verbatim text (what the RFP actually demands) and the atomic
    obligation (the single duty), because a verdict rendered against a paraphrase
    alone can drift from what the solicitation requires.
    """
    return [
        {
            "requirement_id": req.requirement_id,
            "display_label": req.display_label,
            "req_type": req.req_type,
            "section": req.source_ref.section_label,
            "page": req.source_ref.page,
            "verbatim_text": req.verbatim_text,
            "atomic_obligation": req.atomic_obligation,
            "profile_id": profile.profile_id,
        }
        for req in requirements
    ]


def load_verdicts(path: Path | str) -> dict[str, ComplianceJudgment]:
    """Load a JSONL verdict recording into ``{requirement_id: ComplianceJudgment}``.

    A malformed line, a missing id, or a verdict failing schema validation raises
    :class:`CorruptVerdictsError` naming the 1-indexed line — a bad recording must
    fail loudly rather than quietly leave requirements unjudged.
    """
    path = Path(path)
    if not path.exists():
        raise CorruptVerdictsError(f"verdicts file not found: {path}")

    out: dict[str, ComplianceJudgment] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptVerdictsError(f"{path}:{lineno}: not valid JSON: {exc}") from exc
        try:
            judgment = ComplianceJudgment.model_validate(record)
        except ValidationError as exc:
            raise CorruptVerdictsError(
                f"{path}:{lineno}: not a valid ComplianceJudgment: {exc}"
            ) from exc
        if judgment.requirement_id in out:
            raise CorruptVerdictsError(
                f"{path}:{lineno}: duplicate verdict for {judgment.requirement_id}"
            )
        out[judgment.requirement_id] = judgment
    if not out:
        raise CorruptVerdictsError(f"{path}: no verdicts found (empty recording)")
    return out


def apply_verdicts(
    requirements: Iterable[Requirement], verdicts: dict[str, ComplianceJudgment]
) -> list[ComplianceJudgment]:
    """Return verdicts for the requirements present, in requirement order.

    Requirements with no recorded verdict are OMITTED rather than defaulted.
    Inventing a verdict — even a neutral one — would put a value in the matrix
    that no one actually judged, and "unjudged" must stay distinguishable from
    "judged and found acceptable".
    """
    out: list[ComplianceJudgment] = []
    for req in requirements:
        judgment = verdicts.get(req.requirement_id)
        if judgment is not None:
            out.append(judgment)
    return out


def judgment_summary(
    judgments: Iterable[ComplianceJudgment], total_requirements: int
) -> dict[str, int]:
    """Verdict counts plus the unjudged remainder — the coverage honesty check."""
    counts = {
        "fully_compliant": 0,
        "partially_compliant": 0,
        "non_compliant": 0,
        "unknown": 0,
    }
    judged = 0
    for judgment in judgments:
        counts[judgment.verdict] = counts.get(judgment.verdict, 0) + 1
        judged += 1
    counts["not_judged"] = max(total_requirements - judged, 0)
    return counts
