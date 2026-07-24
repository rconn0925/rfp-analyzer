"""Corpus-driven assertions for all four Phase 1 success criteria.

Every expectation is read from ``tests/corpus/manifest.json`` fields
(``dir``, ``role``, ``expected_classification``, ``has_amendment``,
``has_scanned_pages``, ``files``) — no hardcoded solicitation numbers, so
the suite is corpus-portable. Skipping without the corpus is handled by
``conftest.pytest_collection_modifyitems``.

Success criteria under test:

- SC1: multi-file package -> document map with per-file entries, page
  numbers, and a schema-valid serialization round-trip
- SC2: UCF boundaries on the primary package (TOC guard: L/M never start on
  page 1); the non-UCF package is flagged, never mis-sectioned
- SC3: scanned/low-quality pages are caught, flagged, and text-emptied
- SC4: SF30 amendments identified with articulate evidence
"""

import json
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.models import DocumentMap

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

BAD_QUALITY = {"scanned", "empty", "low_text", "gibberish"}


def _load_packages() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["packages"]


PACKAGES = _load_packages()

ALL = [pytest.param(p, id=p["dir"]) for p in PACKAGES]
PRIMARY = [pytest.param(p, id=p["dir"]) for p in PACKAGES if p["role"] == "primary"]
NON_UCF = [pytest.param(p, id=p["dir"]) for p in PACKAGES if p["role"] == "non_ucf"]
SCANNED = [pytest.param(p, id=p["dir"]) for p in PACKAGES if p["has_scanned_pages"]]
WITH_AMENDMENT = [pytest.param(p, id=p["dir"]) for p in PACKAGES if p["has_amendment"]]


@pytest.mark.parametrize("pkg", ALL)
def test_document_map_covers_every_file(pkg, pipeline_map):
    """SC1: one entry per corpus file; ok PDFs carry numbered pages; the map
    serializes and re-validates against the schema."""
    dmap = pipeline_map(pkg)
    expected = {f["name"]: f for f in pkg["files"]}
    assert {f.filename for f in dmap.files} == set(expected)
    for file in dmap.files:
        if file.parse_status == "ok" and file.file_type == "pdf":
            assert file.pages, f"{file.filename}: ok PDF with zero pages"
            assert all(p.page_number >= 1 for p in file.pages)
            assert file.page_count == expected[file.filename]["pages"], (
                f"{file.filename}: page_count mismatch vs manifest"
            )
    DocumentMap.model_validate_json(dmap.model_dump_json())


@pytest.mark.parametrize("pkg", PRIMARY)
def test_primary_package_ucf_boundaries(pkg, pipeline_map):
    """SC2 (standard): L and M sections detected with page_start > 1 (TOC
    guard) plus a C / sow_pws node; classification matches the manifest."""
    dmap = pipeline_map(pkg)
    top = [node for file in dmap.files for node in file.sections]
    l_nodes = [n for n in top if n.label == "L"]
    m_nodes = [n for n in top if n.label == "M"]
    c_nodes = [n for n in top if n.label == "C" or n.role == "sow_pws"]
    assert l_nodes, "no Section L detected in primary package"
    assert m_nodes, "no Section M detected in primary package"
    assert c_nodes, "no Section C / sow_pws content detected in primary package"
    for node in l_nodes + m_nodes:
        assert node.locator.kind == "pages"
        assert node.locator.page_start > 1, (
            f"Section {node.label} starts on page 1 — TOC page leaked into sectioning"
        )
    assert dmap.classification == pkg["expected_classification"]


@pytest.mark.parametrize("pkg", NON_UCF)
def test_non_ucf_package_flagged_not_mis_sectioned(pkg, pipeline_map):
    """SC2 (non-UCF): honest classification with warnings and no fabricated
    L/M sections."""
    dmap = pipeline_map(pkg)
    assert dmap.classification == pkg["expected_classification"]
    assert len(dmap.warnings) >= 1
    fabricated = [
        (file.filename, node.label)
        for file in dmap.files
        for node in file.sections
        if node.label in ("L", "M")
    ]
    assert not fabricated, f"fabricated L/M sections in non-UCF package: {fabricated}"


@pytest.mark.parametrize("pkg", SCANNED)
def test_scanned_pages_flagged_and_emptied(pkg, pipeline_map):
    """SC3: hostile pages are caught by the quality gates and their text is
    emptied so garbage never flows downstream (D-03)."""
    dmap = pipeline_map(pkg)
    flagged = [p for file in dmap.files for p in file.pages if p.quality in BAD_QUALITY]
    assert len(flagged) >= 1, "known-hostile package produced zero flagged pages"
    for page in flagged:
        assert page.text == "", f"flagged page {page.page_number} still carries text"


@pytest.mark.parametrize("pkg", WITH_AMENDMENT)
def test_amendments_identified(pkg, pipeline_map):
    """SC4: packages with SF30s yield >= 1 amendment-role file; every
    amendment carries articulate evidence, and the filename fallback only
    ever fires on files with no page-1 text layer."""
    dmap = pipeline_map(pkg)
    amendments = [f for f in dmap.files if f.doc_role == "amendment"]
    assert amendments, "manifest says has_amendment but no amendment-role file found"
    for file in amendments:
        assert file.amendment_evidence in ("form_text", "filename")
        if file.amendment_evidence == "filename":
            page1 = file.pages[0].text if file.pages else ""
            assert not page1.strip(), (
                f"{file.filename}: filename evidence used despite a page-1 text layer"
            )


@pytest.mark.parametrize("pkg", ALL)
def test_pipeline_total_and_statuses_final(pkg, pipeline_map):
    """The pipeline completes on every corpus package; every file lands in
    exactly one terminal parse_status and no page stays 'pending'."""
    dmap = pipeline_map(pkg)
    assert dmap.files, "pipeline returned an empty file list"
    for file in dmap.files:
        assert file.parse_status in ("ok", "failed", "rejected")
        for page in file.pages:
            assert page.quality != "pending", (
                f"{file.filename} p{page.page_number}: quality left 'pending'"
            )
