"""The Claude Code engine seam: chunk identity, drafts loading, replay.

The honesty properties under test are the ones that decide whether an extraction
number can be trusted: a missing chunk must be counted rather than read as "no
requirements here", a corrupt recording must fail loudly, and replaying the same
artifact twice must produce the identical RequirementSet.
"""

from __future__ import annotations

import json

import pytest

from rfp_analyzer.pipeline.extraction.chunker import chunk_key
from rfp_analyzer.pipeline.extraction.replay import (
    CorruptDraftsError,
    ExtractionParseError,
    MissingDraftsError,
    ReplayEngine,
    load_drafts,
    replay_extract_fn,
)
from rfp_analyzer.pipeline.extraction.run_extraction import run_extraction
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    PageInfo,
    ParsedFile,
    RequirementBatch,
)

SENTENCE = "The offeror shall submit a technical proposal not exceeding 30 pages."


def _draft(text: str = SENTENCE) -> dict:
    return {
        "verbatim_text": text,
        "atomic_obligation": "Submit a technical proposal of at most 30 pages.",
        "binding_keyword": "shall",
        "type_guess": "instruction",
        "parent_index": None,
    }


def _map(text: str = SENTENCE) -> DocumentMap:
    """A one-file, one-ok-page DocumentMap (no sections -> whole-file fallback chunk)."""
    return DocumentMap(
        package_name="synthetic",
        classification="full_ucf",
        files=[
            ParsedFile(
                file_id="ffffffffffff-solicitation",
                filename="Solicitation.pdf",
                sha256="0" * 64,
                file_type="pdf",
                parse_status="ok",
                doc_role="base_solicitation",
                page_count=1,
                pages=[
                    PageInfo(page_number=1, quality="ok", char_count=len(text), text=text)
                ],
            )
        ],
    )


# --- chunk_key ----------------------------------------------------------------


class TestChunkKey:
    def test_is_deterministic(self):
        assert chunk_key(SENTENCE) == chunk_key(SENTENCE)

    def test_differs_for_different_text(self):
        assert chunk_key(SENTENCE) != chunk_key(SENTENCE + " More.")

    def test_is_normalization_stable(self):
        """Whitespace/hyphenation variants of one chunk must not fork the key."""
        wrapped = "The offeror shall submit a technical  pro-\nposal not exceeding 30 pages."
        assert chunk_key(wrapped) == chunk_key(SENTENCE)

    def test_has_readable_prefix(self):
        assert chunk_key(SENTENCE).startswith("CHK-")


# --- load_drafts --------------------------------------------------------------


class TestLoadDrafts:
    def _write(self, tmp_path, lines):
        path = tmp_path / "drafts.jsonl"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_loads_records_keyed_by_chunk(self, tmp_path):
        key = chunk_key(SENTENCE)
        path = self._write(
            tmp_path, [json.dumps({"chunk_key": key, "requirements": [_draft()]})]
        )
        drafts = load_drafts(path)
        assert set(drafts) == {key}
        assert drafts[key].requirements[0].verbatim_text == SENTENCE

    def test_blank_lines_are_ignored(self, tmp_path):
        key = chunk_key(SENTENCE)
        path = self._write(
            tmp_path,
            ["", json.dumps({"chunk_key": key, "requirements": []}), "", "  "],
        )
        assert set(load_drafts(path)) == {key}

    def test_malformed_json_names_the_line(self, tmp_path):
        path = self._write(tmp_path, ['{"chunk_key": "CHK-a", "requirements": []}', "{oops"])
        with pytest.raises(CorruptDraftsError, match=":2:"):
            load_drafts(path)

    def test_missing_chunk_key_is_rejected(self, tmp_path):
        path = self._write(tmp_path, [json.dumps({"requirements": []})])
        with pytest.raises(CorruptDraftsError, match="chunk_key"):
            load_drafts(path)

    def test_schema_violation_is_rejected(self, tmp_path):
        bad = _draft()
        bad["binding_keyword"] = "perhaps"  # not in the Literal enum
        path = self._write(
            tmp_path, [json.dumps({"chunk_key": "CHK-a", "requirements": [bad]})]
        )
        with pytest.raises(CorruptDraftsError, match="RequirementBatch"):
            load_drafts(path)

    def test_duplicate_chunk_key_is_rejected(self, tmp_path):
        rec = json.dumps({"chunk_key": "CHK-a", "requirements": []})
        with pytest.raises(CorruptDraftsError, match="duplicate"):
            load_drafts(self._write(tmp_path, [rec, rec]))

    def test_empty_recording_is_rejected(self, tmp_path):
        """An empty file would otherwise replay as 'zero requirements found'."""
        with pytest.raises(CorruptDraftsError, match="empty"):
            load_drafts(self._write(tmp_path, []))

    def test_missing_file_is_rejected(self, tmp_path):
        with pytest.raises(CorruptDraftsError, match="not found"):
            load_drafts(tmp_path / "nope.jsonl")


# --- ReplayEngine -------------------------------------------------------------


class TestReplayEngine:
    def test_resolves_a_recorded_chunk(self):
        key = chunk_key(SENTENCE)
        engine = replay_extract_fn({key: RequirementBatch(requirements=[])})
        assert isinstance(engine, ReplayEngine)
        assert engine(SENTENCE, "claude-code", 7).requirements == []
        assert engine.missing_count == 0

    def test_missing_chunk_raises_and_is_counted(self):
        """The coverage hole must be visible, not silently empty (T-02-20)."""
        engine = replay_extract_fn({"CHK-other": RequirementBatch(requirements=[])})
        with pytest.raises(MissingDraftsError):
            engine(SENTENCE, "claude-code", 7)
        assert engine.missing_count == 1

    def test_missing_drafts_is_caught_by_the_isolation_path(self):
        """Subclassing ExtractionParseError keeps 02-05's per-chunk isolation."""
        assert issubclass(MissingDraftsError, ExtractionParseError)

    def test_unused_recordings_are_counted(self):
        """Stale drafts for chunks the pipeline no longer produces are surfaced."""
        engine = replay_extract_fn(
            {
                chunk_key(SENTENCE): RequirementBatch(requirements=[]),
                "CHK-stale": RequirementBatch(),
            }
        )
        engine(SENTENCE, "claude-code", 7)
        assert engine.unused_count == 1


# --- end-to-end through run_extraction ----------------------------------------


class TestReplayThroughRunExtraction:
    def _engine(self, dmap):
        from rfp_analyzer.pipeline.extraction.chunker import iter_chunks

        drafts = {
            chunk_key(c.text): RequirementBatch.model_validate({"requirements": [_draft()]})
            for c in iter_chunks(dmap)
        }
        return replay_extract_fn(drafts)

    def test_replay_produces_a_grounded_requirement(self):
        dmap = _map()
        result = run_extraction(dmap, extract_fn=self._engine(dmap))
        assert len(result.requirements) == 1
        req = result.requirements[0]
        assert req.verified is True
        assert req.source_ref.page == 1

    def test_replay_is_byte_identical_across_runs(self):
        """The reproducibility claim EVAL.md rests on."""
        dmap = _map()
        first = run_extraction(dmap, extract_fn=self._engine(dmap))
        second = run_extraction(dmap, extract_fn=self._engine(dmap))
        assert first.model_dump_json(exclude={"metrics"}) == second.model_dump_json(
            exclude={"metrics"}
        )

    def test_coverage_counters_are_recorded(self):
        dmap = _map()
        result = run_extraction(dmap, extract_fn=self._engine(dmap))
        assert result.metrics.chunks_total >= 1
        assert result.metrics.chunks_unextracted == 0

    def test_unextracted_chunks_are_counted_not_hidden(self):
        dmap = _map()
        empty_engine = replay_extract_fn({"CHK-nothing": RequirementBatch(requirements=[])})
        result = run_extraction(dmap, extract_fn=empty_engine)
        assert result.requirements == []
        assert result.metrics.chunks_unextracted == result.metrics.chunks_total
        assert result.metrics.chunks_total > 0

    def test_llm_counters_stay_zero_on_replay(self):
        """Those tokens were spent in the Claude Code session, not this process —
        reporting them here would be a fabricated measurement."""
        dmap = _map()
        result = run_extraction(dmap, extract_fn=self._engine(dmap))
        assert result.metrics.llm_calls == 0
        assert result.metrics.input_tokens == 0
        assert result.metrics.estimated_cost_usd == 0.0


def test_no_module_imports_ollama():
    """The local-model engine is fully retired — no import can resurrect it."""
    import pathlib

    src = pathlib.Path("src")
    offenders = [
        p for p in src.rglob("*.py") if "ollama" in p.read_text(encoding="utf-8").lower()
    ]
    assert not offenders, f"ollama still referenced in: {offenders}"
