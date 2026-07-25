"""End-to-end: real package -> populated compliance workbook (Phase 3 criterion 5).

The phase's headline claim is "package in, populated matrix workbook out, no
manual steps". This proves it against the real federal RFP, replaying the
committed Claude Code drafts so it needs no GPU, no API key, and no network —
only the gitignored corpus binaries, which is the sole skip condition.
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.analysis.export import (
    MATRIX_HEADERS,
    NOT_JUDGED,
    write_csv,
    write_workbook,
)
from rfp_analyzer.pipeline.analysis.judge import load_verdicts
from rfp_analyzer.pipeline.analysis.outline import UNASSIGNED_ID
from rfp_analyzer.pipeline.analysis.run_analysis import run_analysis
from rfp_analyzer.pipeline.extraction.replay import load_drafts, replay_extract_fn
from rfp_analyzer.pipeline.extraction.run_extraction import run_extraction

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
DRAFTS_PATH = Path("tests/eval/fixtures/golden_drafts.jsonl")


def _primary_package() -> dict:
    packages = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["packages"]
    return next(p for p in packages if p["role"] == "primary")


@pytest.fixture(scope="module")
def analysis(pipeline_map):
    """Parse -> extract (replayed) -> analyze, once for the whole module."""
    document_map = pipeline_map(_primary_package())
    engine = replay_extract_fn(load_drafts(DRAFTS_PATH))
    requirement_set = run_extraction(document_map, model="claude-code", extract_fn=engine)
    return run_analysis(document_map, requirement_set)


def test_matrix_covers_every_extracted_requirement(analysis):
    """No requirement is lost between extraction and the matrix."""
    assert analysis.requirements
    assert len(analysis.cross_mappings) == len(analysis.requirements)
    assert len(analysis.requirement_outline) == len(analysis.requirements)


def test_every_requirement_lands_on_an_outline_node(analysis):
    """ANLZ-02: mapped means mapped — including to the explicit UNASSIGNED node."""
    node_ids = {n.node_id for n in analysis.outline}
    for req in analysis.requirements:
        placed = analysis.requirement_outline[req.requirement_id]
        assert placed in node_ids, f"{req.requirement_id} points at unknown node {placed}"


def test_outline_is_derived_from_the_rfps_own_factors(analysis):
    """The outline is read out of the solicitation, not invented."""
    titles = {n.title for n in analysis.outline}
    assert any("Management Approach" in t for t in titles)
    assert any("Corporate Experience" in t for t in titles)


def test_unassigned_stays_a_small_minority(analysis):
    """A mapper that placed nothing would still satisfy 'every row is mapped'."""
    total = len(analysis.requirements)
    unassigned = sum(1 for v in analysis.requirement_outline.values() if v == UNASSIGNED_ID)
    assert unassigned / total < 0.20, f"{unassigned}/{total} unplaced — mapping regressed"


def test_cross_mapping_names_every_disposition(analysis):
    kinds = {m.gap_kind for m in analysis.cross_mappings}
    assert kinds <= {"mapped", "l_without_m", "m_without_l", "sow_without_either"}


def test_workbook_and_csv_are_written_and_wellformed(analysis, tmp_path):
    xlsx = write_workbook(analysis, tmp_path / "matrix.xlsx")
    csv_path = write_csv(analysis, tmp_path / "matrix.csv")

    with zipfile.ZipFile(xlsx) as book:
        assert book.testzip() is None
        workbook_xml = book.read("xl/workbook.xml").decode()
    for sheet in ("Compliance Matrix", "Cross-Reference", "Shred Checklist"):
        assert sheet in workbook_xml

    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    assert rows[0] == MATRIX_HEADERS
    assert len(rows) - 1 == len(analysis.requirements)


def test_unjudged_rows_say_so_rather_than_reading_as_compliant(analysis, tmp_path):
    """Run without verdicts: every compliance cell must be an explicit NOT JUDGED."""
    csv_path = write_csv(analysis, tmp_path / "matrix.csv")
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    column = MATRIX_HEADERS.index("Compliance")
    assert all(r[column] == NOT_JUDGED for r in rows[1:])


def test_recorded_verdicts_flow_into_the_matrix(pipeline_map, tmp_path):
    """The judgment seam works end-to-end when a verdict recording exists."""
    verdicts_path = Path("artifacts/primary-ucf/verdicts.jsonl")
    if not verdicts_path.exists():
        pytest.skip("no recorded verdicts artifact available")

    document_map = pipeline_map(_primary_package())
    engine = replay_extract_fn(load_drafts(DRAFTS_PATH))
    requirement_set = run_extraction(document_map, model="claude-code", extract_fn=engine)
    matrix = run_analysis(document_map, requirement_set, verdicts=load_verdicts(verdicts_path))

    assert matrix.judgments, "recorded verdicts did not reach the matrix"
    csv_path = write_csv(matrix, tmp_path / "matrix.csv")
    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    column = MATRIX_HEADERS.index("Compliance")
    judged = [r for r in rows[1:] if r[column] != NOT_JUDGED]
    assert len(judged) == len(matrix.judgments)
    # Every judged row carries a rationale — a bare verdict is not actionable.
    rationale = MATRIX_HEADERS.index("Rationale")
    assert all(r[rationale].strip() for r in judged)


def test_fictional_profile_is_stamped_on_the_real_export(analysis, tmp_path):
    """A demo workbook must never be mistakable for a real company assessment."""
    xlsx = write_workbook(analysis, tmp_path / "matrix.xlsx")
    with zipfile.ZipFile(xlsx) as book:
        shared = book.read("xl/sharedStrings.xml").decode()
    assert "FICTIONAL DEMO PROFILE" in shared
