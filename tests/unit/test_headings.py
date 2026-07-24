"""Unit tests for UCF heading regexes, role-title matching, and per-page
candidate detection (plan 01-05 Task 1).

Synthetic text only — no corpus needed, CI-safe. The exact heading forms are
assumption A5 (corpus-falsifiable); these tests pin the intended behavior of
the regexes themselves.
"""

import time

from rfp_analyzer.pipeline.sectioning.headings import (
    PARA_NUMBER,
    PART_HEADING,
    SECTION_HEADING,
    find_heading_candidates,
    match_role_title,
    normalize_line,
)


class TestSectionHeadingRegex:
    def test_plain_dash_variant_matches_letter_l(self):
        m = SECTION_HEADING.match("SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS")
        assert m is not None
        assert m.group(1).upper() == "L"

    def test_em_dash_variant_matches(self):
        m = SECTION_HEADING.match("SECTION L—INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS")
        assert m is not None
        assert m.group(1).upper() == "L"

    def test_lowercase_colon_variant_matches(self):
        m = SECTION_HEADING.match("section l: instructions")
        assert m is not None
        assert m.group(1).upper() == "L"

    def test_mid_sentence_section_reference_does_not_match(self):
        # Line-start anchoring: cross-references must never look like headings.
        text = "Offerors must see SECTION L for details on proposal format."
        assert SECTION_HEADING.search(text) is None
        assert find_heading_candidates(text) == []


class TestPartAndParagraphRegexes:
    def test_part_headings_match(self):
        for line, numeral in [
            ("PART I—THE SCHEDULE", "I"),
            ("PART II - CONTRACT CLAUSES", "II"),
            ("PART III - LIST OF DOCUMENTS, EXHIBITS AND OTHER ATTACHMENTS", "III"),
            ("PART IV", "IV"),
        ]:
            m = PART_HEADING.match(line)
            assert m is not None, line
            assert m.group(1).upper() == numeral

    def test_para_number_matches_letter_and_components(self):
        m = PARA_NUMBER.match("L.4.2 Content of the technical volume")
        assert m is not None
        assert m.group(1) == "L"
        candidates = find_heading_candidates("L.4.2 Content of the technical volume")
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.signal == "paragraph_numbering"
        assert cand.letter == "L"
        assert cand.components == (4, 2)
        assert cand.label == "L.4.2"

    def test_numeric_paragraph_does_not_match(self):
        assert PARA_NUMBER.match("1.4.2 General information") is None


class TestRoleTitles:
    def test_far_15_204_1_role_titles_map(self):
        assert match_role_title("INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS") == (
            "instructions"
        )
        assert match_role_title("EVALUATION FACTORS FOR AWARD") == "evaluation"
        assert match_role_title("STATEMENT OF WORK") == "sow_pws"
        assert match_role_title("PERFORMANCE WORK STATEMENT") == "sow_pws"
        assert match_role_title("SPECIAL CONTRACT REQUIREMENTS") == "special_requirements"

    def test_proposal_submission_instructions_maps_to_instructions(self):
        # Pitfall-3 class: attachment files titled like this carry Section L
        # content without any "SECTION L" literal.
        assert match_role_title("Proposal Submission Instructions") == "instructions"

    def test_matching_survives_normalization(self):
        assert match_role_title("  statement \t  of   work  ") == "sow_pws"
        assert match_role_title("Evaluation  Factors\tFor Award") == "evaluation"
        assert normalize_line("Statement—of \t work") == "STATEMENT-OF WORK"


class TestFindHeadingCandidates:
    def test_page_with_heading_and_paragraph_yields_both_signals(self):
        page_text = "\n".join(
            [
                "SECTION L - INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                "",
                "L.1 General",
                "The contractor shall submit proposals per the instructions below.",
            ]
        )
        candidates = find_heading_candidates(page_text)
        signals = {c.signal for c in candidates}
        assert "heading" in signals
        assert "paragraph_numbering" in signals

        heading = next(c for c in candidates if c.signal == "heading")
        assert heading.line_index == 0
        assert heading.letter == "L"
        assert heading.role == "instructions"
        assert "INSTRUCTIONS" in heading.title

        para = next(c for c in candidates if c.signal == "paragraph_numbering")
        assert para.line_index == 2
        assert para.letter == "L"
        assert para.components == (1,)

    def test_standalone_role_title_yields_role_title_candidate(self):
        candidates = find_heading_candidates("PERFORMANCE WORK STATEMENT\nThe contractor shall...")
        assert len(candidates) == 1
        assert candidates[0].signal == "role_title"
        assert candidates[0].role == "sow_pws"

    def test_empty_text_yields_no_candidates(self):
        assert find_heading_candidates("") == []


class TestAdversarialTiming:
    def test_regexes_complete_instantly_on_hostile_input(self):
        # T-01-12: bounded quantifiers / anchored patterns must stay linear.
        hostile_line = "SECTION " + "L" * 50_000
        near_matches = "\n".join(
            "SECTION L " + "-" * 60 + " NEAR MISS TITLE PADDING " + "X" * 80 + str(i)
            for i in range(10_000)
        )
        start = time.perf_counter()
        SECTION_HEADING.search(hostile_line)
        PART_HEADING.search(hostile_line)
        PARA_NUMBER.search(hostile_line)
        find_heading_candidates(hostile_line)
        list(SECTION_HEADING.finditer(near_matches))
        find_heading_candidates(near_matches)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"adversarial matching took {elapsed:.2f}s"
