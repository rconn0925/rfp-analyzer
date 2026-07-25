"""End-to-end extraction over the real primary package (skipif corpus).

The first real ``run_extraction`` pass over a live federal RFP: it parses the
primary-ucf package (via the session ``pipeline_map`` fixture), replays the
committed Claude Code drafts recording, grounds every draft, reconciles the
deterministic sweep, and flags SF30 amendment changes.

Formerly gated on a live local-model runtime. That gate is GONE: the engine is a
committed artifact replayed in pure Python, so this needs no GPU, no API key, and
no network. The corpus binaries remain the only skip condition (gitignored, D-02),
which is why it still skips in CI.

The assertions are the phase's structural truths — *reach* and *honesty
invariants*. Exact requirement counts are deliberately not asserted; the accuracy
numbers live in EVAL.md, where they can be discussed with their caveats.
"""

import json
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.extraction.replay import load_drafts, replay_extract_fn
from rfp_analyzer.pipeline.extraction.run_extraction import run_extraction

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
DRAFTS_PATH = Path("tests/eval/fixtures/golden_drafts.jsonl")

MODEL = "claude-code"


def _primary_package() -> dict:
    packages = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["packages"]
    return next(p for p in packages if p["role"] == "primary")


@pytest.fixture(scope="module")
def extraction(pipeline_map):
    """Run run_extraction once over the primary package for the whole module.

    Replays the recorded drafts, so this is fast and exactly reproducible.
    """
    document_map = pipeline_map(_primary_package())
    engine = replay_extract_fn(load_drafts(DRAFTS_PATH))
    return document_map, run_extraction(document_map, model=MODEL, extract_fn=engine)


def test_requirements_reach_L_M_and_beyond(extraction):
    """EXTR-04: requirements are drawn from Sections L and M AND from outside them
    (C / attachments), across more than one source file."""
    _document_map, result = extraction
    reqs = result.requirements
    assert reqs, "extraction produced zero requirements over the primary package"

    labels = {r.source_ref.section_label for r in reqs}
    # Compare on the top-level section letter: de-duplication now keeps the
    # DEEPEST section path, so Section L rows are labelled "L.1"/"L.5" rather
    # than the coarse "L" the parent chunk carried.
    heads = {(lbl or "").split(".", 1)[0] for lbl in labels}
    assert "L" in heads, f"no Section L requirements; labels seen: {sorted(map(str, labels))}"
    assert "M" in heads, f"no Section M requirements; labels seen: {sorted(map(str, labels))}"

    beyond_lm = {h for h in heads if h not in {"L", "M"}}
    assert beyond_lm, "no requirements outside L/M — C/attachments were unreachable (EXTR-04)"

    source_files = {r.source_ref.filename for r in reqs}
    assert len(source_files) >= 2, f"requirements came from a single file only: {source_files}"


def test_every_verified_requirement_has_a_page_inside_its_file(extraction):
    """EXTR-02: a computed (not engine-emitted) page ref lands within the cited
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
    binding sentences than this scoped extraction covers)."""
    _document_map, result = extraction
    assert isinstance(result.missed_candidates, list)
    for candidate in result.missed_candidates:
        assert candidate.binding_keyword
        assert candidate.page >= 1


def test_partial_coverage_is_surfaced_not_hidden(extraction):
    """T-02-20: the recording covers only the golden-annotated scope, and the run
    must SAY so rather than let 79 unextracted chunks pass for 'nothing found'."""
    _document_map, result = extraction
    metrics = result.metrics
    assert metrics.chunks_total > 0
    assert metrics.chunks_unextracted > 0, "expected the scoped recording to leave gaps"
    assert metrics.chunks_unextracted < metrics.chunks_total


def test_replay_is_reproducible(pipeline_map):
    """The property EVAL.md's numbers rest on: same artifact, identical result."""
    document_map = pipeline_map(_primary_package())
    first = run_extraction(
        document_map, model=MODEL, extract_fn=replay_extract_fn(load_drafts(DRAFTS_PATH))
    )
    second = run_extraction(
        document_map, model=MODEL, extract_fn=replay_extract_fn(load_drafts(DRAFTS_PATH))
    )
    assert first.model_dump_json(exclude={"metrics"}) == second.model_dump_json(
        exclude={"metrics"}
    )


def test_no_llm_cost_is_claimed(extraction):
    """The engine ran in a Claude Code session, not this process — reporting
    tokens or dollars here would be a fabricated measurement."""
    _document_map, result = extraction
    assert result.metrics.llm_calls == 0
    assert result.metrics.estimated_cost_usd == 0.0
