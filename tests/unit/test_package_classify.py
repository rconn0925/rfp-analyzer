"""Unit tests for four-way package classification (01-05 Task 3).

Honest degradation must be articulate: every classification carries evidence,
and every non-full_ucf outcome carries at least one human-readable warning
(T-01-14 — never a silent enum).
"""

from rfp_analyzer.pipeline.classify.package import classify_package
from rfp_analyzer.pipeline.models import PageInfo, PageSpan, ParsedFile, SectionNode


def section(
    label: str,
    start: int,
    end: int,
    *,
    role: str | None = None,
    detection: str = "heading",
    title: str = "",
) -> SectionNode:
    return SectionNode(
        label=label,
        title=title or f"Section {label}",
        role=role,
        locator=PageSpan(page_start=start, page_end=end),
        detection=detection,
    )


def make_file(
    filename: str,
    sections: list[SectionNode] | None = None,
    page1_text: str = "",
) -> ParsedFile:
    return ParsedFile(
        file_id="abc123def456-" + filename.rsplit(".", 1)[0].lower(),
        filename=filename,
        sha256="0" * 64,
        file_type="pdf",
        parse_status="ok",
        page_count=60,
        pages=[PageInfo(page_number=1, quality="ok", char_count=len(page1_text), text=page1_text)],
        sections=sections or [],
    )


SF1449_TEXT = "SOLICITATION/CONTRACT/ORDER FOR COMMERCIAL PRODUCTS AND COMMERCIAL SERVICES"


def full_ucf_sections() -> list[SectionNode]:
    return [
        section("C", 8, 19, role="sow_pws"),
        section("L", 40, 49, role="instructions"),
        section("M", 50, 52, role="evaluation"),
    ]


class TestClassifyPackage:
    def test_l_m_c_yields_full_ucf(self):
        base = make_file("base.pdf", full_ucf_sections(), "SOLICITATION, OFFER AND AWARD")
        classification, evidence, warnings = classify_package([base])
        assert classification == "full_ucf"
        assert evidence
        assert any("Section L" in e for e in evidence)

    def test_sow_role_attachment_completes_full_ucf(self):
        # C may arrive as a sow_pws-role node in a separate attachment.
        base = make_file(
            "base.pdf",
            [section("L", 40, 49, role="instructions"), section("M", 50, 52, role="evaluation")],
        )
        sow = make_file(
            "pws.pdf",
            [section("SOW", 1, 30, role="sow_pws", detection="role_title")],
        )
        classification, evidence, _warnings = classify_package([base, sow])
        assert classification == "full_ucf"
        assert evidence

    def test_missing_c_yields_partial_with_named_warning(self):
        base = make_file(
            "base.pdf",
            [section("L", 40, 49, role="instructions"), section("M", 50, 52, role="evaluation")],
        )
        classification, evidence, warnings = classify_package([base])
        assert classification == "partial_ucf"
        assert evidence
        assert any("SOW" in w or "Section C" in w for w in warnings)

    def test_missing_m_yields_partial_with_named_warning(self):
        base = make_file("base.pdf", [section("L", 40, 49, role="instructions")])
        classification, _evidence, warnings = classify_package([base])
        assert classification == "partial_ucf"
        assert any("Section M" in w for w in warnings)

    def test_sf1449_with_detected_lm_is_partial_not_non_ucf(self):
        # Open Question 1: form signal and structure signal are independent.
        base = make_file(
            "base.pdf",
            [section("L", 10, 19, role="instructions"), section("M", 20, 24, role="evaluation")],
            SF1449_TEXT,
        )
        classification, evidence, warnings = classify_package([base])
        assert classification == "partial_ucf"
        assert any("SF1449" in e for e in evidence)
        assert warnings

    def test_sf1449_without_ucf_sections_is_non_ucf_commercial(self):
        base = make_file("base.pdf", [], SF1449_TEXT)
        classification, evidence, warnings = classify_package([base])
        assert classification == "non_ucf_commercial"
        assert any("SF1449" in e for e in evidence)
        assert warnings

    def test_combined_synopsis_markers_are_non_ucf_commercial(self):
        notice = make_file(
            "notice.pdf",
            [],
            "This notice constitutes a combined synopsis/solicitation for commercial "
            "items prepared in accordance with the format in Subpart 12.6.",
        )
        classification, evidence, warnings = classify_package([notice])
        assert classification == "non_ucf_commercial"
        assert any("synopsis" in e.lower() for e in evidence)
        assert warnings

    def test_nothing_detected_is_unknown(self):
        blob = make_file("scan.pdf", [], "")
        classification, evidence, warnings = classify_package([blob])
        assert classification == "unknown"
        assert evidence
        assert warnings

    def test_every_classification_is_articulate(self):
        # T-01-14: evidence never empty; non-full outcomes always warn.
        scenarios = [
            [make_file("base.pdf", full_ucf_sections())],
            [make_file("base.pdf", [section("L", 40, 49, role="instructions")])],
            [make_file("base.pdf", [], SF1449_TEXT)],
            [make_file("scan.pdf", [], "")],
        ]
        seen = set()
        for files in scenarios:
            classification, evidence, warnings = classify_package(files)
            seen.add(classification)
            assert evidence, f"empty evidence for {classification}"
            if classification != "full_ucf":
                assert warnings, f"no warnings for {classification}"
        assert seen == {"full_ucf", "partial_ucf", "non_ucf_commercial", "unknown"}
