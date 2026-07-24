"""Unit tests for the extraction entry point and the ``extract`` CLI subcommand.

Everything here is CI-safe: ``run_extraction`` is driven with an injected fake
``extract_fn`` (no Ollama), and the CLI paths run over hand-built artifacts. The
end-to-end corpus proof lives in ``tests/integration/test_extract_corpus.py``
(skipif Ollama+corpus).
"""

from rfp_analyzer.pipeline.extraction.run_extraction import run_extraction
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    PageInfo,
    ParsedFile,
    RequirementBatch,
    RequirementDraft,
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
        assert result.model_name == "qwen2.5:14b-instruct"
