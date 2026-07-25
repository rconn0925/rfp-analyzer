"""Unit tests for the extraction entry point and the ``extract`` CLI subcommand.

Everything here is CI-safe: ``run_extraction`` is driven with an injected fake
``extract_fn`` (the engine is always injected), and the CLI paths run over
hand-built artifacts. The end-to-end corpus proof lives in
``tests/integration/test_extract_corpus.py`` (skipif corpus).
"""

import argparse
import json

import pytest

from rfp_analyzer.cli import (
    NO_GOLDEN_LINE,
    _run_extract,
    build_parser,
    render_requirements_report,
)
from rfp_analyzer.pipeline.extraction.run_extraction import DEFAULT_MODEL, run_extraction
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    MissedCandidate,
    PageInfo,
    ParsedFile,
    Requirement,
    RequirementBatch,
    RequirementDraft,
    RequirementSet,
    SourceRef,
)


def _single_page_map(page_text: str, *, doc_role: str = "base_solicitation") -> DocumentMap:
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
                doc_role=doc_role,
                page_count=1,
                pages=[
                    PageInfo(page_number=1, quality="ok", char_count=len(page_text), text=page_text)
                ],
            )
        ],
    )


def _fake_fn(batch: RequirementBatch):
    """An extract_fn that returns a fixed batch for any chunk (Ollama-free)."""

    def fn(chunk_text: str, model: str, seed: int) -> RequirementBatch:
        return batch

    return fn


class TestRunExtraction:
    def test_composes_pipeline_into_metricized_requirement_set(self):
        # Page carries two binding sentences; the model only extracts the first,
        # with a deliberately-wrong binding_keyword ("should").
        shall_sentence = "The offeror shall submit a technical volume by the deadline."
        must_sentence = "The contractor must provide a payment bond before award."
        page_text = f"{shall_sentence} {must_sentence}"
        dmap = _single_page_map(page_text)

        batch = RequirementBatch(
            requirements=[
                RequirementDraft(
                    verbatim_text=shall_sentence,
                    atomic_obligation="Submit a technical volume.",
                    binding_keyword="should",  # wrong on purpose — sweep must override
                    type_guess="instruction",
                )
            ]
        )

        result = run_extraction(dmap, model="fake-model", extract_fn=_fake_fn(batch))

        # model_name recorded on the set; local inference cost stays zero.
        assert result.model_name == "fake-model"
        assert result.package_name == "synthetic"
        assert result.metrics.estimated_cost_usd == 0.0
        # Stage timings captured for the three composed stages.
        assert {"extract", "sweep", "amendments"} <= set(result.metrics.stage_timings)

        # One grounded requirement, with the sweep's authoritative keyword.
        assert len(result.requirements) == 1
        req = result.requirements[0]
        assert req.verified is True
        assert req.source_ref.page == 1
        assert req.binding_keyword == "shall", "sweep keyword must override the model guess"

        # The uncovered "must" sentence surfaces as a missed candidate (EXTR-05).
        assert result.missed_candidates, "uncovered sweep hit not surfaced"
        assert any(mc.binding_keyword == "must" for mc in result.missed_candidates)
        assert all(mc.file_id == "ffffffffffff-solicitation" for mc in result.missed_candidates)

    def test_ungroundable_draft_retained_and_no_false_missed_coverage(self):
        # The model hallucinates a requirement absent from the page: it is kept
        # (verified=False) and cannot "cover" any sweep hit.
        page_text = "The offeror shall submit a technical volume by the deadline."
        dmap = _single_page_map(page_text)
        batch = RequirementBatch(
            requirements=[
                RequirementDraft(
                    verbatim_text="The contractor shall deliver a widget never mentioned here.",
                    atomic_obligation="Deliver a widget.",
                    binding_keyword="shall",
                    type_guess="other",
                )
            ]
        )

        result = run_extraction(dmap, model="fake-model", extract_fn=_fake_fn(batch))

        assert len(result.requirements) == 1
        assert result.requirements[0].verified is False
        # The real page sentence was never extracted -> it stays a missed candidate.
        assert any("technical volume" in mc.verbatim_sentence for mc in result.missed_candidates)

    def test_default_model_used_when_unspecified(self):
        dmap = _single_page_map("The offeror shall provide a cover letter.")
        batch = RequirementBatch(requirements=[])
        result = run_extraction(dmap, extract_fn=_fake_fn(batch))
        assert result.model_name == DEFAULT_MODEL


# --- CLI: build_parser, report rendering, artifact + exit codes ----------------


def _source_ref(section_label: str, page: int | None, *, doc_role: str = "base_solicitation"):
    verified = page is not None
    return SourceRef(
        file_id="ffffffffffff-solicitation",
        filename="Solicitation.pdf",
        section_label=section_label,
        page=page,
        char_start=0 if verified else None,
        char_end=10 if verified else None,
        match="exact" if verified else "none",
        score=100.0 if verified else 0.0,
        verified=verified,
        doc_role=doc_role,
    )


def _requirement(
    rid: str,
    *,
    req_type: str,
    section_label: str,
    page: int | None,
    keyword: str = "shall",
    is_amendment_change: bool = False,
    possibly_modified: bool = False,
    doc_role: str = "base_solicitation",
) -> Requirement:
    return Requirement(
        requirement_id=rid,
        display_label=f"{section_label}-1",
        verbatim_text=f"The offeror {keyword} do the thing described in {section_label}.",
        atomic_obligation="Do the thing.",
        binding_keyword=keyword,
        req_type=req_type,
        source_ref=_source_ref(section_label, page, doc_role=doc_role),
        verified=page is not None,
        is_amendment_change=is_amendment_change,
        possibly_modified=possibly_modified,
    )


def _synthetic_requirement_set() -> RequirementSet:
    return RequirementSet(
        package_name="primary-ucf",
        model_name="claude-code",
        requirements=[
            _requirement("r1", req_type="instruction", section_label="L", page=49),
            _requirement("r2", req_type="evaluation", section_label="M", page=58),
            _requirement("r3", req_type="sow_pws", section_label="C", page=12),
            # ungroundable row (verified=False) — must be counted, never hidden.
            _requirement("r4", req_type="other", section_label="C", page=None),
            _requirement(
                "r5",
                req_type="other",
                section_label="L",
                page=3,
                keyword="shall",
                is_amendment_change=True,
                doc_role="amendment",
            ),
            _requirement(
                "r6",
                req_type="instruction",
                section_label="L",
                page=49,
                possibly_modified=True,
            ),
        ],
        missed_candidates=[
            MissedCandidate(
                file_id="ffffffffffff-solicitation",
                page=52,
                verbatim_sentence="The contractor must provide a payment bond before award.",
                binding_keyword="must",
            )
        ],
        metrics=RunMetrics(
            stage_timings={"extract": 42.5, "sweep": 0.3, "amendments": 0.01},
            llm_calls=11,
            input_tokens=120000,
            output_tokens=8000,
        ),
    )


class TestBuildParserExtract:
    def test_extract_subcommand_defaults(self):
        parser = build_parser()
        args = parser.parse_args(
            ["extract", "artifacts/primary-ucf", "--drafts", "d.jsonl"]
        )
        assert args.command == "extract"
        assert args.artifacts_dir == "artifacts/primary-ucf"
        assert args.drafts == "d.jsonl"
        assert args.model == DEFAULT_MODEL
        assert args.seed == 7
        assert args.out is None
        assert args.golden is None

    def test_extract_without_drafts_is_a_usage_error(self):
        """There is no in-process engine — a driftless run must not look valid."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["extract", "artifacts/primary-ucf"])

    def test_chunks_subcommand_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["chunks", "artifacts/primary-ucf"])
        assert args.command == "chunks"
        assert args.out is None

    def test_extract_subcommand_accepts_flags(self):
        parser = build_parser()
        args = parser.parse_args(
            ["extract", "artifacts/x", "--drafts", "d.jsonl", "--model",
             "claude-code-manual", "--seed", "3", "--out", "o",
             "--golden", "g.json"]
        )
        assert args.model == "claude-code-manual"
        assert args.seed == 3
        assert args.out == "o"
        assert args.golden == "g.json"


class TestRenderRequirementsReport:
    def test_report_carries_all_load_bearing_lines(self):
        report = render_requirements_report(_synthetic_requirement_set())

        assert "Package: primary-ucf" in report
        assert "Model: claude-code" in report

        # Verified vs unverified breakdown (T-02-15): 5 verified, 1 ungroundable.
        assert "verified (grounded): 5" in report
        assert "unverified (ungroundable): 1" in report

        # By-type and by-section breakdowns.
        assert "By type:" in report
        assert "instruction: 2" in report
        assert "By section:" in report
        assert "L: 3" in report
        assert "M: 1" in report

        # INTK-03 amendment rows.
        assert "Amendment change rows: 1" in report
        assert "possibly-modified base rows: 1" in report

        # EXTR-05 missed candidate surfaced with its keyword.
        assert "Missed candidates (sweep hits not extracted): 1" in report
        assert "must" in report
        assert "payment bond" in report

        # Local metrics footer.
        assert "LLM calls: 11" in report
        assert "LLM cost: $0.00" in report

        # Success criterion 5: the scoring line is present on EVERY run, even
        # when nothing scores it — an unmeasured run must not look measured.
        assert NO_GOLDEN_LINE in report


class TestRunExtractExitCodes:
    def _write_map(self, artifacts_dir, dmap: DocumentMap) -> None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "document_map.json").write_text(
            dmap.model_dump_json(indent=2), encoding="utf-8"
        )

    def test_missing_document_map_returns_exit_2(self, tmp_path):
        artifacts = tmp_path / "primary-ucf"
        artifacts.mkdir()
        args = argparse.Namespace(
            artifacts_dir=str(artifacts), model="fake", seed=7, out=None,
            drafts="unused.jsonl", golden=None,
        )
        assert _run_extract(args) == 2

    def test_nonexistent_dir_returns_exit_2(self, tmp_path):
        args = argparse.Namespace(
            artifacts_dir=str(tmp_path / "nope"), model="fake", seed=7, out=None,
            drafts="unused.jsonl", golden=None,
        )
        assert _run_extract(args) == 2

    def test_incompatible_schema_version_returns_exit_2(self, tmp_path):
        artifacts = tmp_path / "primary-ucf"
        artifacts.mkdir()
        # A document_map.json from a future contract major version.
        (artifacts / "document_map.json").write_text(
            json.dumps({"schema_version": "2.0", "package_name": "x", "files": []}),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            artifacts_dir=str(artifacts), model="fake", seed=7, out=None,
            drafts="unused.jsonl", golden=None,
        )
        assert _run_extract(args) == 2

    def test_success_writes_requirements_json_and_exits_0(self, tmp_path, monkeypatch):
        artifacts = tmp_path / "primary-ucf"
        self._write_map(artifacts, _single_page_map("The offeror shall provide a cover letter."))
        # Stub the extraction entry so the CLI path stays a pure unit test.
        drafts_path = tmp_path / "drafts.jsonl"
        drafts_path.write_text(
            json.dumps({"chunk_key": "CHK-any", "requirements": []}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "rfp_analyzer.cli.run_extraction",
            lambda dmap, model, seed, extract_fn: _synthetic_requirement_set(),
        )
        args = argparse.Namespace(
            artifacts_dir=str(artifacts), model="fake", seed=7, out=None,
            drafts=str(drafts_path), golden=None,
        )
        assert _run_extract(args) == 0

        # requirements.json written next to the map and re-validates against schema.
        out_path = artifacts / "requirements.json"
        assert out_path.exists()
        RequirementSet.model_validate_json(out_path.read_text(encoding="utf-8"))
