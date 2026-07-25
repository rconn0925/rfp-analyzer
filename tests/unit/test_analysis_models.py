"""The Phase 3 analysis contract: what an exported matrix is allowed to claim."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    ComplianceJudgment,
    ComplianceMatrix,
    CrossMapping,
    OutlineNode,
)


class TestCrossMapping:
    def test_gap_kinds_are_closed(self):
        """Gap kinds are an enum: an unmapped requirement must land in a named
        bucket, never a free-text status nobody filters on."""
        with pytest.raises(ValidationError):
            CrossMapping(requirement_id="r1", gap_kind="probably_fine")

    @pytest.mark.parametrize(
        "kind", ["l_without_m", "m_without_l", "sow_without_either", "mapped"]
    )
    def test_each_gap_kind_is_representable(self, kind):
        assert CrossMapping(requirement_id="r1", gap_kind=kind).gap_kind == kind

    def test_unmapped_defaults_to_no_counterparts_and_zero_score(self):
        cm = CrossMapping(requirement_id="r1", gap_kind="l_without_m")
        assert cm.counterpart_ids == []
        assert cm.score == 0.0


class TestComplianceJudgment:
    def test_rationale_is_required(self):
        """A verdict without a reason is not actionable, so it cannot be built."""
        with pytest.raises(ValidationError):
            ComplianceJudgment(requirement_id="r1", verdict="fully_compliant", confidence="high")

    def test_confidence_is_required(self):
        with pytest.raises(ValidationError):
            ComplianceJudgment(
                requirement_id="r1", verdict="fully_compliant", rationale="covered"
            )

    def test_unknown_verdict_exists_so_the_judge_can_decline(self):
        """Declining must be cheaper than guessing — a fabricated 'fully compliant'
        is the costliest failure mode in this product."""
        j = ComplianceJudgment(
            requirement_id="r1",
            verdict="unknown",
            rationale="profile says nothing about pest control licensing",
            confidence="low",
        )
        assert j.verdict == "unknown"

    def test_verdicts_are_closed(self):
        with pytest.raises(ValidationError):
            ComplianceJudgment(
                requirement_id="r1", verdict="mostly", rationale="x", confidence="high"
            )


class TestCapabilityProfile:
    def test_defaults_to_fictional(self):
        """The demo profile must be labelled fictional by default: a judgment
        against invented capabilities must never read as a real assessment."""
        assert CapabilityProfile().is_fictional is True


class TestComplianceMatrix:
    def test_round_trips_through_json(self):
        m = ComplianceMatrix(
            package_name="primary-ucf",
            cross_mappings=[CrossMapping(requirement_id="r1", gap_kind="mapped")],
            outline=[OutlineNode(node_id="L.1", title="Volume I")],
            requirement_outline={"r1": "L.1"},
            judgments=[
                ComplianceJudgment(
                    requirement_id="r1",
                    verdict="partially_compliant",
                    rationale="partial coverage",
                    confidence="medium",
                )
            ],
        )
        again = ComplianceMatrix.model_validate_json(m.model_dump_json())
        assert again.requirement_outline == {"r1": "L.1"}
        assert again.judgments[0].verdict == "partially_compliant"

    def test_empty_matrix_is_valid(self):
        assert ComplianceMatrix().requirements == []
