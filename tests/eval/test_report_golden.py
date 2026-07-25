"""Success criterion 5 at the report surface: recall and precision, every run.

The scorer being correct (test_metrics.py) is only half of it — the numbers have
to actually reach the operator. These tests pin that the report always says
something about accuracy, including when nothing scored the run.
"""

from __future__ import annotations

import json

from rfp_analyzer.cli import NO_GOLDEN_LINE, render_requirements_report
from rfp_analyzer.pipeline.models import (
    Requirement,
    RequirementSet,
    SourceRef,
)

FILE_ID = "475828d11085-solicitation-n4008526r0033"
SENTENCE = "The offeror shall submit a technical proposal not exceeding 30 pages."
OTHER = "All questions shall be submitted in writing to the Contracting Officer."


def _req(text: str, page: int = 49, req_id: str = "REQ-aaaaaaaaaa") -> Requirement:
    return Requirement(
        requirement_id=req_id,
        display_label="L-1",
        verbatim_text=text,
        atomic_obligation="Do the thing.",
        binding_keyword="shall",
        req_type="instruction",
        verified=True,
        source_ref=SourceRef(
            file_id=FILE_ID,
            filename="Solicitation.pdf",
            section_label="L",
            doc_role="base_solicitation",
            page=page,
            verified=True,
            match="exact",
            score=100.0,
        ),
    )


def _set(reqs: list[Requirement], package: str = "primary-ucf") -> RequirementSet:
    return RequirementSet(package_name=package, model_name="claude-code", requirements=reqs)


def _golden_file(tmp_path, entries: list[dict], package: str = "primary-ucf"):
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps({"package": package, "requirements": entries}), encoding="utf-8"
    )
    return path


def _entry(text: str, page: int = 49) -> dict:
    return {"file_id": FILE_ID, "page": page, "verbatim_text": text}


def test_report_prints_precision_and_recall_separately(tmp_path):
    golden = _golden_file(tmp_path, [_entry(SENTENCE)])
    report = render_requirements_report(_set([_req(SENTENCE)]), golden_path=str(golden))
    assert "precision=" in report
    assert "recall=" in report
    assert "F1=" in report


def test_report_numbers_reflect_a_partial_run(tmp_path):
    """One of two golden rows found -> recall 0.5, precision 1.0, stated apart."""
    golden = _golden_file(tmp_path, [_entry(SENTENCE), _entry(OTHER, page=50)])
    report = render_requirements_report(_set([_req(SENTENCE)]), golden_path=str(golden))
    assert "precision=1.000" in report
    assert "recall=0.500" in report


def test_report_without_golden_says_so_explicitly(tmp_path):
    """Absence of a score must be visible, never a silently missing line."""
    report = render_requirements_report(_set([_req(SENTENCE)]))
    assert NO_GOLDEN_LINE in report


def test_missing_golden_file_is_reported_not_silently_skipped(tmp_path):
    report = render_requirements_report(
        _set([_req(SENTENCE)]), golden_path=str(tmp_path / "absent.json")
    )
    assert "ERROR" in report and "not found" in report


def test_unreadable_golden_file_is_reported(tmp_path):
    bad = tmp_path / "golden.json"
    bad.write_text("{not json", encoding="utf-8")
    report = render_requirements_report(_set([_req(SENTENCE)]), golden_path=str(bad))
    assert "ERROR" in report


def test_mismatched_package_is_warned_not_silently_scored(tmp_path):
    """Scoring against another package's ground truth is meaningless — say so."""
    golden = _golden_file(tmp_path, [_entry(SENTENCE)], package="some-other-package")
    report = render_requirements_report(_set([_req(SENTENCE)]), golden_path=str(golden))
    assert "WARNING" in report
    assert "some-other-package" in report


def test_unextracted_chunks_are_warned_in_the_report():
    """A coverage hole must not read as a clean run (T-02-20)."""
    rs = _set([_req(SENTENCE)])
    rs.metrics.chunks_total = 10
    rs.metrics.chunks_unextracted = 3
    report = render_requirements_report(rs)
    assert "chunks extracted: 7/10" in report
    assert "WARNING" in report
    assert "recall is understated" in report


def test_full_coverage_reports_no_warning():
    rs = _set([_req(SENTENCE)])
    rs.metrics.chunks_total = 10
    rs.metrics.chunks_unextracted = 0
    report = render_requirements_report(rs)
    assert "chunks extracted: 10/10" in report
    assert "recall is understated" not in report
