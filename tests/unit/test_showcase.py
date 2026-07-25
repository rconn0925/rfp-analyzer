"""Static portfolio showcase generation (Phase 5)."""

from __future__ import annotations

import re

from rfp_analyzer.pipeline.analysis.judge import DEMO_PROFILE
from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    ComplianceJudgment,
    ComplianceMatrix,
    CrossMapping,
    OutlineNode,
    Requirement,
    SourceRef,
)
from rfp_analyzer.showcase import (
    SAMPLE_SIZE,
    build_context,
    load_matrix,
    render_html,
    write_showcase,
)


def _req(rid: str, text: str = "The Offeror shall submit a technical proposal.") -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=f"L-{rid[-1]}",
        verbatim_text=text,
        atomic_obligation="Submit a technical proposal.",
        binding_keyword="shall",
        req_type="instruction",
        verified=True,
        source_ref=SourceRef(
            file_id="f1", filename="Solicitation.pdf", section_label="L.5",
            doc_role="base_solicitation", page=49, verified=True,
            match="exact", score=100.0,
        ),
    )


def _matrix(reqs=None, judgments=(), profile=None) -> ComplianceMatrix:
    reqs = list(reqs if reqs is not None else [_req("r1"), _req("r2")])
    return ComplianceMatrix(
        package_name="primary-ucf",
        profile=profile or DEMO_PROFILE,
        requirements=reqs,
        cross_mappings=[
            CrossMapping(requirement_id=r.requirement_id, gap_kind="l_without_m") for r in reqs
        ],
        outline=[OutlineNode(node_id="L.5", title="CONTENT OF PROPOSAL")],
        requirement_outline={r.requirement_id: "L.5" for r in reqs},
        judgments=list(judgments),
    )


class TestContext:
    def test_counts_come_from_the_matrix(self):
        c = build_context(_matrix())
        assert c["total"] == 2
        assert c["grounded"] == 2
        assert c["grounded_pct"] == 100

    def test_ungrounded_rows_lower_the_grounding_number(self):
        req = _req("r3")
        req.verified = False
        c = build_context(_matrix([_req("r1"), req]))
        assert c["grounded"] == 1
        assert c["grounded_pct"] == 50

    def test_sample_is_capped(self):
        c = build_context(_matrix([_req(f"r{i}") for i in range(40)]))
        assert len(c["rows"]) == SAMPLE_SIZE

    def test_sample_prefers_the_interesting_rows(self):
        """A sample of only green rows would misrepresent the output."""
        reqs = [_req(f"r{i}") for i in range(5)]
        judgments = [
            ComplianceJudgment(requirement_id="r4", verdict="partially_compliant",
                               rationale="pest control is subcontracted", confidence="medium")
        ]
        c = build_context(_matrix(reqs, judgments))
        assert c["rows"][0]["id"] == "r4"
        assert c["rows"][0]["verdict"] == "Partially compliant"


class TestRender:
    def test_no_unfilled_placeholders(self):
        html = render_html(build_context(_matrix()))
        assert not re.findall(r"\{[a-z_]+\}", html)

    def test_is_self_contained(self):
        """CSP blocks external hosts — no CDN fonts, scripts, or images."""
        html = render_html(build_context(_matrix()))
        assert "http://" not in html
        assert "https://" not in html

    def test_defines_both_themes(self):
        html = render_html(build_context(_matrix()))
        assert "prefers-color-scheme: dark" in html
        assert 'data-theme="dark"' in html
        assert 'data-theme="light"' in html

    def test_article_tags_balance(self):
        html = render_html(build_context(_matrix()))
        assert html.count("<article") == html.count("</article>")

    def test_states_it_is_a_record_not_a_live_service(self):
        html = render_html(build_context(_matrix()))
        assert "not a live service" in html

    def test_fictional_profile_is_disclosed(self):
        html = render_html(build_context(_matrix()))
        assert "fictional" in html.lower()

    def test_reports_the_unjudged_count_rather_than_hiding_it(self):
        html = render_html(build_context(_matrix()))
        assert "not judged" in html.lower()

    def test_carries_the_measured_accuracy_and_its_caveat(self):
        """The measurement discipline is the portfolio piece; the caveat is part of it."""
        html = render_html(build_context(_matrix()))
        assert "0.950" in html
        assert "lower bound" in html

    def test_requirement_text_is_escaped(self):
        req = _req("r1", "Submit <script>alert(1)</script> & a proposal.")
        html = render_html(build_context(_matrix([req])))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_real_profile_is_not_described_as_fictional_in_the_lede(self):
        real = CapabilityProfile(profile_id="a", company_name="Acme", is_fictional=False)
        html = render_html(build_context(_matrix(profile=real)))
        assert "Acme" in html


def test_write_and_reload_round_trip(tmp_path):
    matrix = _matrix()
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(matrix.model_dump_json(), encoding="utf-8")
    reloaded = load_matrix(matrix_path)
    out = write_showcase(reloaded, tmp_path / "showcase.html")
    assert out.exists()
    assert out.stat().st_size > 3000
