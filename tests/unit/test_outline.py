"""Proposal outline derivation and requirement placement (ANLZ-02)."""

from __future__ import annotations

from rfp_analyzer.pipeline.analysis.outline import (
    EVAL_CRITERIA_ID,
    POST_AWARD_ID,
    UNASSIGNED_ID,
    _factor_matcher,
    derive_outline,
    discover_factors,
    map_requirements,
    outline_coverage,
)
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    OutlineNode,
    PageInfo,
    PageSpan,
    ParsedFile,
    Requirement,
    SectionNode,
    SourceRef,
)

L_TEXT = (
    "Section L - Instructions\n"
    "L.5 Content of Proposal:\n"
    "The non-price proposal shall include responses to each non-price factor.\n"
    "Factor 1 - Management Approach\n"
    "Factor 2 - Corporate Experience\n"
    "Factor 3 - Safety\n"
)


def _locator(start: int, end: int) -> PageSpan:
    return PageSpan(page_start=start, page_end=end)


def _map(text: str = L_TEXT, *, doc_role: str = "base_solicitation") -> DocumentMap:
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
                doc_role=doc_role,
                page_count=1,
                pages=[PageInfo(page_number=1, quality="ok", char_count=len(text), text=text)],
                sections=[
                    SectionNode(
                        label="L",
                        title="INSTRUCTIONS",
                        role="instructions",
                        detection="heading",
                        locator=_locator(1, 1),
                        children=[
                            SectionNode(
                                label="L.3",
                                title="INQUIRIES:",
                                detection="paragraph_numbering",
                                locator=_locator(1, 1),
                            ),
                            SectionNode(
                                label="L.5",
                                title="CONTENT OF PROPOSAL:",
                                detection="paragraph_numbering",
                                locator=_locator(1, 1),
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def _req(rid: str, text: str, req_type: str = "instruction", section: str = "L.5") -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=rid,
        verbatim_text=text,
        atomic_obligation=text,
        binding_keyword="shall",
        req_type=req_type,
        verified=True,
        source_ref=SourceRef(
            file_id="f1",
            filename="Solicitation.pdf",
            section_label=section,
            doc_role="base_solicitation",
            page=1,
            verified=True,
            match="exact",
            score=100.0,
        ),
    )


class TestFactorDiscovery:
    def test_reads_the_rfps_own_factor_declarations(self):
        assert discover_factors(_map()) == [
            ("1", "Management Approach"),
            ("2", "Corporate Experience"),
            ("3", "Safety"),
        ]

    def test_no_factors_declared_yields_empty(self):
        assert discover_factors(_map("Section L - Instructions\nNothing here.\n")) == []


class TestOutlineDerivation:
    def test_node_ids_are_unique(self):
        """Amendments re-issue Section L; duplicated nodes would double-count."""
        ids = [n.node_id for n in derive_outline(_map())]
        assert len(ids) == len(set(ids))

    def test_carries_volumes_factors_and_l_subsections(self):
        ids = {n.node_id for n in derive_outline(_map())}
        assert {"VOL-NONPRICE", "VOL-PRICE"} <= ids
        assert {"FACTOR-1", "FACTOR-2", "FACTOR-3"} <= ids
        assert {"L.3", "L.5"} <= ids

    def test_always_provides_the_non_proposal_destinations(self):
        ids = {n.node_id for n in derive_outline(_map())}
        assert {POST_AWARD_ID, EVAL_CRITERIA_ID, UNASSIGNED_ID} <= ids

    def test_factors_hang_under_the_non_price_volume(self):
        nodes = {n.node_id: n for n in derive_outline(_map())}
        assert nodes["FACTOR-1"].parent_node_id == "VOL-NONPRICE"


class TestFactorMatching:
    def test_matches_title_words_and_explicit_factor_number(self):
        node = OutlineNode(node_id="FACTOR-1", title="Factor 1 - Management Approach")
        pattern = _factor_matcher([node])[0][1]
        assert pattern.search("describe your management approach")
        assert pattern.search("Limit the Factor 1 narrative to 25 single-sided pages")

    def test_factor_number_does_not_bleed_into_longer_numbers(self):
        node = OutlineNode(node_id="FACTOR-1", title="Factor 1 - Management Approach")
        pattern = _factor_matcher([node])[0][1]
        assert not pattern.search("under Factor 12 rules")


class TestRequirementPlacement:
    def test_every_requirement_is_mapped(self):
        """The load-bearing guarantee: nothing is silently dropped."""
        reqs = [
            _req("r1", "Describe your management approach."),
            _req("r2", "Provide janitorial services for the facilities.", "sow_pws"),
            _req("r3", "Price is evaluated on total price.", "evaluation"),
        ]
        outline = derive_outline(_map())
        mapping = map_requirements(reqs, outline)
        assert set(mapping) == {"r1", "r2", "r3"}

    def test_factor_keyword_wins(self):
        outline = derive_outline(_map())
        mapping = map_requirements([_req("r1", "Describe your management approach.")], outline)
        assert mapping["r1"] == "FACTOR-1"

    def test_explicit_factor_number_places_the_row(self):
        outline = derive_outline(_map())
        mapping = map_requirements(
            [_req("r1", "Limit the Factor 3 narrative to seven pages.")], outline
        )
        assert mapping["r1"] == "FACTOR-3"

    def test_falls_back_to_its_own_l_subsection(self):
        outline = derive_outline(_map())
        mapping = map_requirements(
            [_req("r1", "Submit all questions in writing.", section="L.3")], outline
        )
        assert mapping["r1"] == "L.3"

    def test_sow_duty_goes_to_post_award_not_a_proposal_section(self):
        """A performance duty is real, but nobody writes it into a volume."""
        outline = derive_outline(_map())
        mapping = map_requirements(
            [_req("r1", "Provide janitorial services for the facilities.", "sow_pws", section="C")],
            outline,
        )
        assert mapping["r1"] == POST_AWARD_ID

    def test_evaluation_criterion_goes_to_eval_criteria(self):
        outline = derive_outline(_map())
        mapping = map_requirements(
            [_req("r1", "Award goes to the best value offeror.", "evaluation", section="M.2")],
            outline,
        )
        assert mapping["r1"] == EVAL_CRITERIA_ID

    def test_unplaceable_row_is_explicit_not_dropped(self):
        outline = derive_outline(_map())
        mapping = map_requirements(
            [_req("r1", "An unrelated obligation about nothing.", "instruction", section="Z")],
            outline,
        )
        assert mapping["r1"] == UNASSIGNED_ID

    def test_is_deterministic(self):
        outline = derive_outline(_map())
        reqs = [_req("r1", "Describe your management approach.")]
        assert map_requirements(reqs, outline) == map_requirements(reqs, outline)


def test_outline_coverage_counts_every_node_used():
    outline = derive_outline(_map())
    reqs = [
        _req("r1", "Describe your management approach."),
        _req("r2", "Describe your safety program."),
        _req("r3", "Provide janitorial services.", "sow_pws", section="C"),
    ]
    counts = outline_coverage(map_requirements(reqs, outline))
    assert sum(counts.values()) == 3
