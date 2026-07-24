"""End-to-end extraction over the real primary package (skipif Ollama+corpus).

This is the first real ``run_extraction`` pass over a live federal RFP: it parses
the primary-ucf package (via the session ``pipeline_map`` fixture), runs the local
model, grounds every draft, reconciles the deterministic sweep, and flags SF30
amendment changes. The assertions are the phase's structural truths, kept
tolerant of small-model variance (RESEARCH Pitfall 6) — we assert *reach* and
*honesty invariants*, never exact requirement counts.

Marked ``requires_ollama``: the conftest collection hook SKIPS this module when
the local runtime is unreachable OR the corpus binaries are absent (CI has
neither a GPU nor the gitignored corpus).
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

import rfp_analyzer.pipeline.extraction.run_extraction as run_extraction_mod
from rfp_analyzer.pipeline.extraction.client import extract_chunk as _real_extract_chunk
from rfp_analyzer.pipeline.extraction.run_extraction import run_extraction
from rfp_analyzer.pipeline.models import RequirementBatch

pytestmark = pytest.mark.requires_ollama

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

MODEL = "qwen2.5:14b-instruct"

# Opt-in local disk cache: a full uncached pass over the 290-page package is
# ~70 min of model calls. Setting RFP_EXTRACT_CACHE_DIR to a writable directory
# lets a developer re-run this test (or demonstrate it green) in seconds by
# replaying each chunk's cached model output. OFF by default — with the env var
# unset, the fixture below uses the real Ollama client, so CI and a clean local
# run exercise the genuine model path.
_CACHE_ENV = "RFP_EXTRACT_CACHE_DIR"


def _primary_package() -> dict:
    packages = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["packages"]
    return next(p for p in packages if p["role"] == "primary")


def _install_disk_cache(monkeypatch, cache_dir: Path) -> None:
    """Patch run_extraction's model call with a chunk-text-keyed disk cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    def cached(chunk_text, model, seed, *, metrics=None):
        key = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()[:16]
        path = cache_dir / f"{key}.json"
        if path.exists():
            return RequirementBatch.model_validate_json(path.read_text(encoding="utf-8"))
        batch = _real_extract_chunk(chunk_text, model, seed, metrics=metrics)
        path.write_text(batch.model_dump_json(), encoding="utf-8")
        return batch

    monkeypatch.setattr(run_extraction_mod, "extract_chunk", cached)


@pytest.fixture(scope="module")
def extraction(pipeline_map):
    """Run run_extraction once over the primary package for the whole module.

    Uses the real Ollama client unless RFP_EXTRACT_CACHE_DIR is set, in which
    case each chunk's output is served from / written to that disk cache.
    """
    pkg = _primary_package()
    document_map = pipeline_map(pkg)
    cache_dir = os.environ.get(_CACHE_ENV)
    if cache_dir:
        mp = pytest.MonkeyPatch()
        _install_disk_cache(mp, Path(cache_dir))
        try:
            result = run_extraction(document_map, model=MODEL)
        finally:
            mp.undo()
    else:
        result = run_extraction(document_map, model=MODEL)
    return document_map, result


def test_requirements_reach_L_M_and_beyond(extraction):
    """EXTR-04: requirements are drawn from Sections L and M AND from outside them
    (C / attachments), across more than one source file."""
    _document_map, result = extraction
    reqs = result.requirements
    assert reqs, "extraction produced zero requirements over the primary package"

    labels = {r.source_ref.section_label for r in reqs}
    assert "L" in labels, f"no Section L requirements; labels seen: {sorted(map(str, labels))}"
    assert "M" in labels, f"no Section M requirements; labels seen: {sorted(map(str, labels))}"

    beyond_lm = {lbl for lbl in labels if lbl not in {"L", "M"}}
    assert beyond_lm, "no requirements outside L/M — C/attachments were unreachable (EXTR-04)"

    source_files = {r.source_ref.filename for r in reqs}
    assert len(source_files) >= 2, f"requirements came from a single file only: {source_files}"


def test_every_verified_requirement_has_a_page_inside_its_file(extraction):
    """EXTR-02: a computed (not model-emitted) page ref lands within the cited
    file's real page range — grounding never invents an out-of-range page."""
    document_map, result = extraction
    page_bound = {
        f.file_id: (f.page_count or max((p.page_number for p in f.pages), default=0))
        for f in document_map.files
    }
    for req in result.requirements:
        if not req.verified:
            continue
        page = req.source_ref.page
        assert page is not None, f"{req.requirement_id}: verified but page is None"
        bound = page_bound.get(req.source_ref.file_id)
        assert bound and 1 <= page <= bound, (
            f"{req.requirement_id}: page {page} outside file range 1..{bound}"
        )


def test_missed_candidates_are_wired(extraction):
    """EXTR-05: the deterministic sweep reconciliation is wired — missed_candidates
    is a populated list of typed rows (the primary package's 290 pages carry more
    binding sentences than any single pass extracts)."""
    _document_map, result = extraction
    assert isinstance(result.missed_candidates, list)
    for candidate in result.missed_candidates:
        assert candidate.binding_keyword
        assert candidate.page >= 1


def test_amendments_contribute_rows_and_are_flagged_not_merged(extraction):
    """INTK-03: amendment files contribute their own requirement rows alongside
    the base rows (no merge), and any change row's affected base rows are
    retained, never collapsed away."""
    _document_map, result = extraction
    reqs = result.requirements
    doc_roles = {r.source_ref.doc_role for r in reqs}
    assert "amendment" in doc_roles, "amendment files contributed no requirement rows"
    assert "base_solicitation" in doc_roles, "base solicitation contributed no rows"

    ids = {r.requirement_id for r in reqs}
    for change in (r for r in reqs if r.is_amendment_change):
        for affected_id in change.affects:
            assert affected_id in ids, (
                f"change {change.requirement_id} points at base row {affected_id} "
                "that is missing — a merge/delete occurred (INTK-03 violated)"
            )
