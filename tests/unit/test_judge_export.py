"""Compliance judgment seam and workbook/CSV export (ANLZ-04, EXPT-01..04)."""

from __future__ import annotations

import csv
import json
import zipfile

import pytest

from rfp_analyzer.pipeline.analysis.export import (
    MATRIX_HEADERS,
    NOT_JUDGED,
    write_csv,
    write_workbook,
)
from rfp_analyzer.pipeline.analysis.judge import (
    DEMO_PROFILE,
    CorruptVerdictsError,
    apply_verdicts,
    judgment_summary,
    judgment_tasks,
    load_verdicts,
)
from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    ComplianceJudgment,
    ComplianceMatrix,
    CrossMapping,
    OutlineNode,
    Requirement,
    SourceRef,
)


def _req(rid: str, text: str = "Submit a technical proposal.") -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=f"L-{rid[-1]}",
        verbatim_text=text,
        atomic_obligation=text,
        binding_keyword="shall",
        req_type="instruction",
        verified=True,
        source_ref=SourceRef(
            file_id="f1",
            filename="Solicitation.pdf",
            section_label="L.5",
            doc_role="base_solicitation",
            page=49,
            verified=True,
            match="exact",
            score=100.0,
        ),
    )


def _verdict(rid: str, verdict: str = "fully_compliant") -> ComplianceJudgment:
    return ComplianceJudgment(
        requirement_id=rid, verdict=verdict, rationale="covered by CAP-01", confidence="high"
    )


def _matrix(reqs, judgments=(), profile=None) -> ComplianceMatrix:
    return ComplianceMatrix(
        package_name="primary-ucf",
        profile=profile or DEMO_PROFILE,
        requirements=list(reqs),
        cross_mappings=[
            CrossMapping(requirement_id=r.requirement_id, gap_kind="l_without_m") for r in reqs
        ],
        outline=[OutlineNode(node_id="L.5", title="CONTENT OF PROPOSAL")],
        requirement_outline={r.requirement_id: "L.5" for r in reqs},
        judgments=list(judgments),
    )


class TestDemoProfile:
    def test_is_labelled_fictional(self):
        assert DEMO_PROFILE.is_fictional is True
        assert "FICTIONAL" in DEMO_PROFILE.company_name

    def test_has_real_gaps_so_the_demo_can_fail(self):
        """A profile that satisfied everything would prove nothing."""
        gaps = [c for c in DEMO_PROFILE.capabilities if c.startswith("NO-CAP")]
        assert gaps, "demo profile needs genuine gaps to produce non-compliant verdicts"


class TestJudgmentTasks:
    def test_carries_verbatim_and_atomic_text(self):
        """A verdict rendered against a paraphrase alone can drift from the RFP."""
        task = judgment_tasks([_req("r1")], DEMO_PROFILE)[0]
        assert task["verbatim_text"]
        assert task["atomic_obligation"]
        assert task["requirement_id"] == "r1"


class TestLoadVerdicts:
    def _write(self, tmp_path, lines):
        path = tmp_path / "verdicts.jsonl"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_loads_by_requirement_id(self, tmp_path):
        path = self._write(tmp_path, [_verdict("r1").model_dump_json()])
        assert set(load_verdicts(path)) == {"r1"}

    def test_malformed_line_names_the_line_number(self, tmp_path):
        path = self._write(tmp_path, [_verdict("r1").model_dump_json(), "{oops"])
        with pytest.raises(CorruptVerdictsError, match=":2:"):
            load_verdicts(path)

    def test_verdict_missing_rationale_is_rejected(self, tmp_path):
        bad = json.dumps({"requirement_id": "r1", "verdict": "fully_compliant",
                          "confidence": "high"})
        with pytest.raises(CorruptVerdictsError):
            load_verdicts(self._write(tmp_path, [bad]))

    def test_duplicate_verdict_is_rejected(self, tmp_path):
        line = _verdict("r1").model_dump_json()
        with pytest.raises(CorruptVerdictsError, match="duplicate"):
            load_verdicts(self._write(tmp_path, [line, line]))

    def test_empty_recording_is_rejected(self, tmp_path):
        with pytest.raises(CorruptVerdictsError, match="empty"):
            load_verdicts(self._write(tmp_path, []))


class TestApplyVerdicts:
    def test_unjudged_requirements_are_omitted_not_defaulted(self):
        """"Unjudged" must stay distinguishable from "judged and acceptable"."""
        reqs = [_req("r1"), _req("r2")]
        judgments = apply_verdicts(reqs, {"r1": _verdict("r1")})
        assert [j.requirement_id for j in judgments] == ["r1"]

    def test_summary_reports_the_unjudged_remainder(self):
        summary = judgment_summary([_verdict("r1")], total_requirements=5)
        assert summary["fully_compliant"] == 1
        assert summary["not_judged"] == 4


class TestWorkbookExport:
    def test_writes_three_named_sheets(self, tmp_path):
        path = write_workbook(_matrix([_req("r1")]), tmp_path / "m.xlsx")
        with zipfile.ZipFile(path) as book:
            assert book.testzip() is None
            workbook_xml = book.read("xl/workbook.xml").decode()
        for sheet in ("Compliance Matrix", "Cross-Reference", "Shred Checklist"):
            assert sheet in workbook_xml

    def test_is_a_valid_zip_with_content(self, tmp_path):
        path = write_workbook(_matrix([_req("r1"), _req("r2")]), tmp_path / "m.xlsx")
        assert path.stat().st_size > 4000


class TestCsvExport:
    def test_one_row_per_requirement_plus_header(self, tmp_path):
        path = write_csv(_matrix([_req("r1"), _req("r2")]), tmp_path / "m.csv")
        rows = list(csv.reader(path.open(encoding="utf-8")))
        assert rows[0] == MATRIX_HEADERS
        assert len(rows) == 3

    def test_unjudged_row_says_not_judged_never_blank(self, tmp_path):
        """An empty cell skims as acceptable; this is the costliest failure here."""
        path = write_csv(_matrix([_req("r1")]), tmp_path / "m.csv")
        rows = list(csv.reader(path.open(encoding="utf-8")))
        compliance = rows[1][MATRIX_HEADERS.index("Compliance")]
        assert compliance == NOT_JUDGED

    def test_judged_row_carries_verdict_confidence_and_rationale(self, tmp_path):
        matrix = _matrix([_req("r1")], judgments=[_verdict("r1", "partially_compliant")])
        rows = list(csv.reader(write_csv(matrix, tmp_path / "m.csv").open(encoding="utf-8")))
        assert rows[1][MATRIX_HEADERS.index("Compliance")] == "Partially Compliant"
        assert rows[1][MATRIX_HEADERS.index("Confidence")] == "high"
        assert "CAP-01" in rows[1][MATRIX_HEADERS.index("Rationale")]

    def test_ungrounded_row_is_flagged_in_its_own_column(self, tmp_path):
        req = _req("r1")
        req.verified = False
        path = write_csv(_matrix([req]), tmp_path / "m.csv")
        rows = list(csv.reader(path.open(encoding="utf-8")))
        assert rows[1][MATRIX_HEADERS.index("Grounded")].startswith("NO")

    def test_gap_is_labelled_not_left_blank(self, tmp_path):
        path = write_csv(_matrix([_req("r1")]), tmp_path / "m.csv")
        rows = list(csv.reader(path.open(encoding="utf-8")))
        assert "GAP" in rows[1][MATRIX_HEADERS.index("Cross-Map")]


def test_real_profile_is_not_stamped_fictional(tmp_path):
    real = CapabilityProfile(profile_id="acme", company_name="Acme Corp", is_fictional=False)
    matrix = _matrix([_req("r1")], profile=real)
    path = write_workbook(matrix, tmp_path / "m.xlsx")
    with zipfile.ZipFile(path) as book:
        shared = book.read("xl/sharedStrings.xml").decode()
    assert "FICTIONAL DEMO PROFILE" not in shared


def test_fictional_profile_is_stamped_on_the_workbook(tmp_path):
    """An exported workbook must never be mistakable for a real assessment."""
    path = write_workbook(_matrix([_req("r1")]), tmp_path / "m.xlsx")
    with zipfile.ZipFile(path) as book:
        shared = book.read("xl/sharedStrings.xml").decode()
    assert "FICTIONAL DEMO PROFILE" in shared
