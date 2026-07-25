"""Evaluation-factor anchoring — the join key for L<->M cross-mapping."""

from __future__ import annotations

from rfp_analyzer.pipeline.analysis.crossmap import cross_map
from rfp_analyzer.pipeline.analysis.factors import (
    FACTOR_HEADING,
    assign_factors,
    factor_anchors,
    factor_coverage,
)
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    PageInfo,
    PageSpan,
    ParsedFile,
    Requirement,
    SectionNode,
    SourceRef,
)

PAGE_59 = (
    "M.2 Evaluation Factors for Award\n"
    "Award will be made to the responsible Offeror whose offer conforms.\n"
    "(1) Factor 1, Management Approach:\n"
    "Your narrative for this Factor shall be no more than 25 single-sided pages.\n"
)
PAGE_66 = (
    "(3) Factor 3, Safety:\n"
    "The Technical Approach to Safety narrative shall be limited to seven pages.\n"
    "Contracts submitted under Factor 2, Corporate Experience are not relevant here.\n"
)


def _map(pages: dict[int, str]) -> DocumentMap:
    return DocumentMap(
        package_name="synthetic",
        classification="full_ucf",
        files=[
            ParsedFile(
                file_id="f1",
                filename="Solicitation.pdf",
                sha256="0" * 64,
                file_type="pdf",
                parse_status="ok",
                doc_role="base_solicitation",
                page_count=max(pages),
                pages=[
                    PageInfo(page_number=n, quality="ok", char_count=len(t), text=t)
                    for n, t in sorted(pages.items())
                ],
                sections=[
                    SectionNode(
                        label="M", title="EVALUATION", role="evaluation",
                        detection="heading",
                        locator=PageSpan(page_start=min(pages), page_end=max(pages)),
                    )
                ],
            )
        ],
    )


def _req(rid: str, text: str, page: int, req_type: str = "evaluation") -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=rid,
        verbatim_text=text,
        atomic_obligation=text,
        binding_keyword="shall",
        req_type=req_type,
        verified=True,
        source_ref=SourceRef(
            file_id="f1", filename="Solicitation.pdf", section_label="M.2",
            doc_role="base_solicitation", page=page, verified=True,
            match="exact", score=100.0,
        ),
    )


class TestHeadingPattern:
    def test_matches_a_parenthesised_factor_heading(self):
        assert FACTOR_HEADING.search("(1) Factor 1, Management Approach:")

    def test_ignores_a_mid_sentence_reference(self):
        """A Factor 2 mention inside Factor 4's section must not re-anchor."""
        assert not FACTOR_HEADING.search(
            "for Contracts submitted under Factor 2, Corporate Experience."
        )

    def test_ignores_the_bare_declaration_list(self):
        """The enumeration on the factors page names them but starts no section."""
        assert not FACTOR_HEADING.search("Factor 1 - Management Approach")


class TestAnchors:
    def test_finds_one_anchor_per_factor_section(self):
        anchors = factor_anchors(_map({59: PAGE_59, 66: PAGE_66}))
        found = [(page, factor) for page, _off, factor in anchors["f1"]]
        assert found == [(59, "FACTOR-1"), (66, "FACTOR-3")]

    def test_no_headings_yields_no_anchors(self):
        assert factor_anchors(_map({59: "Just prose about evaluation."})) == {}


class TestAssignment:
    def test_row_after_a_heading_on_the_same_page_gets_the_factor(self):
        dm = _map({59: PAGE_59})
        text = "Your narrative for this Factor shall be no more than 25 single-sided pages."
        req = _req("r1", text, 59)
        assigned = assign_factors([req], factor_anchors(dm), dm)
        assert assigned["r1"] == "FACTOR-1"

    def test_row_before_the_heading_on_the_same_page_gets_no_factor(self):
        """The award-mechanics preamble shares page 59 with the Factor 1 heading.

        Comparing a chunk-relative offset against a page-relative one tagged all
        of it Factor 1; this pins the corrected frame.
        """
        dm = _map({59: PAGE_59})
        req = _req("r1", "Award will be made to the responsible Offeror whose offer conforms.", 59)
        assert assign_factors([req], factor_anchors(dm), dm) == {}

    def test_row_on_a_later_page_inherits_the_preceding_factor(self):
        dm = _map({59: PAGE_59, 66: PAGE_66})
        req = _req("r1", "Some later obligation.", 62)
        # not locatable on its page, but the page ordering alone is unambiguous
        assert assign_factors([req], factor_anchors(dm), dm)["r1"] == "FACTOR-1"

    def test_unlocatable_row_sharing_a_heading_page_is_left_unassigned(self):
        """Unknown order must mean unassigned, never a guess."""
        dm = _map({59: PAGE_59})
        req = _req("r1", "Text that does not appear on the page at all.", 59)
        assert assign_factors([req], factor_anchors(dm), dm) == {}

    def test_coverage_reports_the_unanchored_remainder(self):
        assert factor_coverage({"r1": "FACTOR-1"}, total=4)["no factor"] == 3


class TestCrossMapGating:
    def _rows(self):
        # Same shape, different factors — the pair that scored 88 and linked falsely.
        l_row = _req(
            "L1", "Limit the Factor 1 narrative to 25 single-sided pages.", 59, "instruction"
        )
        m_row = _req(
            "M1", "Limit the Technical Approach to Safety narrative to seven pages.", 66
        )
        return l_row, m_row

    def test_without_factors_the_false_pair_links(self):
        l_row, m_row = self._rows()
        by_id = {m.requirement_id: m for m in cross_map([l_row, m_row])}
        assert by_id["L1"].gap_kind == "mapped"

    def test_factor_gate_blocks_the_cross_factor_link(self):
        l_row, m_row = self._rows()
        factors = {"L1": "FACTOR-1", "M1": "FACTOR-3"}
        by_id = {m.requirement_id: m for m in cross_map([l_row, m_row], factors=factors)}
        assert by_id["L1"].gap_kind == "l_without_m"
        assert by_id["L1"].counterpart_ids == []

    def test_same_factor_still_links(self):
        l_row, m_row = self._rows()
        factors = {"L1": "FACTOR-1", "M1": "FACTOR-1"}
        by_id = {m.requirement_id: m for m in cross_map([l_row, m_row], factors=factors)}
        assert by_id["L1"].gap_kind == "mapped"

    def test_a_row_without_a_factor_is_not_gated_out(self):
        """A gate cannot be applied to information that is not there."""
        l_row, m_row = self._rows()
        by_id = {
            m.requirement_id: m
            for m in cross_map([l_row, m_row], factors={"M1": "FACTOR-3"})
        }
        assert by_id["L1"].gap_kind == "mapped"


def test_unanchored_evaluation_row_is_process_not_a_gap():
    """Award mechanics describe how the competition runs; calling them a gap
    sends a proposal team looking for an instruction that should not exist."""
    row = _req("M1", "Price is evaluated on total price.", 58)
    mapping = cross_map([row], factors={})[0]
    assert mapping.gap_kind == "evaluation_process"


def test_anchored_evaluation_row_with_no_counterpart_is_still_a_gap():
    row = _req("M1", "The Government evaluates the phase-in plan feasibility.", 60)
    mapping = cross_map([row], factors={"M1": "FACTOR-1"})[0]
    assert mapping.gap_kind == "m_without_l"
