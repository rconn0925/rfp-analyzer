"""Behavior tests for the Phase 2 requirement schema — the extraction contract.

These models extend the Phase 1 document-map contract with the grounded
requirement records every later Phase 2 module reads. Field names are
load-bearing: grounding, ids, sweep, amendments, and the eval harness all key
off them.
"""

import json

from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import (
    Chunk,
    MissedCandidate,
    Requirement,
    RequirementBatch,
    RequirementDraft,
    RequirementSet,
    SourceRef,
)


def _source_ref(**overrides) -> SourceRef:
    base = {
        "file_id": "aaaaaaaaaaaa-base-solicitation",
        "filename": "base_solicitation.pdf",
        "section_label": "L",
        "page": 49,
        "char_start": 100,
        "char_end": 180,
        "match": "exact",
        "score": 100.0,
        "verified": True,
        "doc_role": "base_solicitation",
    }
    base.update(overrides)
    return SourceRef(**base)


def _requirement(**overrides) -> Requirement:
    base = {
        "requirement_id": "REQ-0123456789",
        "display_label": "L-3",
        "verbatim_text": "The offeror shall submit a technical volume.",
        "atomic_obligation": "Submit a technical volume.",
        "binding_keyword": "shall",
        "req_type": "instruction",
        "source_ref": _source_ref(),
        "verified": True,
    }
    base.update(overrides)
    return Requirement(**base)


def test_requirement_json_round_trip():
    """A Requirement survives model_dump_json -> model_validate_json unchanged."""
    original = _requirement(
        parent_id="REQ-aaaaaaaaaa",
        is_amendment_change=True,
        possibly_modified=True,
        affects=["REQ-1111111111", "REQ-2222222222"],
    )
    restored = Requirement.model_validate_json(original.model_dump_json())
    assert restored == original


def test_source_ref_carries_doc_role_provenance():
    """SourceRef.doc_role holds the ParsedFile.doc_role and round-trips preserved.

    This is the provenance INTK-03 amendment gating keys off — an amendment row
    is distinguishable from a base row without re-reading the chunk.
    """
    ref = _source_ref(doc_role="amendment")
    restored = SourceRef.model_validate_json(ref.model_dump_json())
    assert restored.doc_role == "amendment"
    assert restored == ref


def test_source_ref_unverifiable_reference_is_representable():
    """verified=False with page=None validates — never forced to invent a page."""
    ref = _source_ref(
        page=None,
        char_start=None,
        char_end=None,
        section_label=None,
        match="none",
        score=0.0,
        verified=False,
    )
    assert ref.verified is False
    assert ref.page is None
    restored = SourceRef.model_validate_json(ref.model_dump_json())
    assert restored == ref


def test_requirement_set_defaults():
    """RequirementSet defaults: empty lists, default RunMetrics, schema_version 1.0."""
    rset = RequirementSet()
    assert rset.schema_version == "1.0"
    assert rset.package_name == ""
    assert rset.model_name == ""
    assert rset.requirements == []
    assert rset.missed_candidates == []
    assert isinstance(rset.metrics, RunMetrics)
    assert rset.metrics.estimated_cost_usd == 0.0


def test_requirement_set_mutable_defaults_are_independent():
    """Each RequirementSet gets its own list instances (no shared mutable default)."""
    a = RequirementSet()
    b = RequirementSet()
    a.requirements.append(_requirement())
    assert b.requirements == []


def test_requirement_batch_schema_has_no_forbidden_keywords():
    """RequirementBatch is the structured-output schema — must be flat.

    Grammar-constrained decoding rejects constrained numerics and recursive
    $ref cycles; assert the generated schema carries none.
    """
    schema_json = json.dumps(RequirementBatch.model_json_schema())
    assert "minimum" not in schema_json
    assert "maximum" not in schema_json
    assert "minLength" not in schema_json
    assert "maxLength" not in schema_json


def test_requirement_batch_round_trips():
    """RequirementBatch of drafts validates from its own JSON."""
    batch = RequirementBatch(
        requirements=[
            RequirementDraft(
                verbatim_text="The offeror shall submit A, B, and C.",
                atomic_obligation="Submit A.",
                binding_keyword="shall",
                type_guess="instruction",
            ),
            RequirementDraft(
                verbatim_text="The offeror shall submit A, B, and C.",
                atomic_obligation="Submit B.",
                binding_keyword="shall",
                type_guess="instruction",
                parent_index=0,
            ),
        ]
    )
    restored = RequirementBatch.model_validate_json(batch.model_dump_json())
    assert restored == batch
    assert restored.requirements[1].parent_index == 0


def test_chunk_page_map_round_trips():
    """Chunk carries (char_start, char_end, page_number) tuples for grounding."""
    chunk = Chunk(
        file_id="aaaaaaaaaaaa-base-solicitation",
        filename="base_solicitation.pdf",
        section_label="L",
        role="instructions",
        doc_role="base_solicitation",
        text="SECTION L ... The offeror shall submit a technical volume.",
        page_map=[(0, 40, 49), (40, 58, 50)],
    )
    restored = Chunk.model_validate_json(chunk.model_dump_json())
    assert restored.page_map == [(0, 40, 49), (40, 58, 50)]
    assert restored == chunk


def test_missed_candidate_round_trips():
    """MissedCandidate captures a sweep hit with page and binding keyword."""
    mc = MissedCandidate(
        file_id="aaaaaaaaaaaa-base-solicitation",
        page=52,
        verbatim_sentence="The contractor must maintain a QASP.",
        binding_keyword="must",
    )
    restored = MissedCandidate.model_validate_json(mc.model_dump_json())
    assert restored == mc
