"""Behavior tests for the chunk -> grounded Requirement orchestration (extract.py).

The whole assembly path is exercised without any engine by injecting a fake
``extract_fn`` that returns canned ``RequirementBatch`` objects. This proves the
grounding wiring, atomic-sibling splitting, deterministic ids (including for
ungroundable rows), the full SectionNode.role -> req_type map, per-chunk parse
isolation, and doc_role survival onto the Requirement — all CI-safe, no GPU.
"""

from rfp_analyzer.pipeline.extraction.extract import extract_requirements
from rfp_analyzer.pipeline.extraction.replay import ExtractionParseError
from rfp_analyzer.pipeline.models import (
    Chunk,
    RequirementBatch,
    RequirementDraft,
)

_COMPOUND = (
    "The offeror shall submit a technical volume, a past-performance volume, "
    "and a price volume."
)


def _chunk(
    text: str,
    *,
    role: str | None = None,
    doc_role: str = "base_solicitation",
    file_id: str = "f1",
    section_label: str = "L",
) -> Chunk:
    """A single-page chunk whose page_map maps the whole text to page 1."""
    return Chunk(
        file_id=file_id,
        filename=f"{file_id}.pdf",
        section_label=section_label,
        role=role,
        doc_role=doc_role,
        text=text,
        page_map=[(0, len(text), 1)],
    )


def _draft(
    verbatim: str,
    obligation: str,
    *,
    keyword: str = "shall",
    type_guess: str = "instruction",
    parent_index: int | None = None,
) -> RequirementDraft:
    return RequirementDraft(
        verbatim_text=verbatim,
        atomic_obligation=obligation,
        binding_keyword=keyword,
        type_guess=type_guess,
        parent_index=parent_index,
    )


def _fake_fn(batch_by_text: dict[str, RequirementBatch]):
    """Build an extract_fn that returns a canned batch keyed on chunk text."""

    def fn(chunk_text: str, model: str, seed: int = 7) -> RequirementBatch:
        return batch_by_text[chunk_text]

    return fn


# --- (a) atomic siblings: one verbatim/SourceRef, distinct ids, parent linkage --


def test_compound_yields_three_siblings_sharing_one_source_ref():
    chunk = _chunk(f"SECTION L. {_COMPOUND}")
    batch = RequirementBatch(
        requirements=[
            _draft(_COMPOUND, "Submit a technical volume.", parent_index=None),
            _draft(_COMPOUND, "Submit a past-performance volume.", parent_index=0),
            _draft(_COMPOUND, "Submit a price volume.", parent_index=0),
        ]
    )
    reqs = extract_requirements(
        [chunk], model="fake", extract_fn=_fake_fn({chunk.text: batch})
    )

    assert len(reqs) == 3
    # All three share the same verbatim and the same (verified) SourceRef.
    assert {r.verbatim_text for r in reqs} == {_COMPOUND}
    assert all(r.verified for r in reqs)
    assert len({r.source_ref.model_dump_json() for r in reqs}) == 1
    assert reqs[0].source_ref.page == 1
    # Distinct stable ids.
    assert len({r.requirement_id for r in reqs}) == 3
    # Children link to the first (root) sibling; root has no parent.
    root_id = reqs[0].requirement_id
    assert reqs[0].parent_id is None
    assert reqs[1].parent_id == root_id
    assert reqs[2].parent_id == root_id


# --- (b) ungroundable draft: retained, verified=False, stable id ---------------


def test_ungroundable_draft_retained_with_stable_id():
    chunk = _chunk("SECTION M. The Government will evaluate technical merit.")
    absent = "The contractor shall deliver a widget not mentioned in this chunk."
    batch = RequirementBatch(requirements=[_draft(absent, "Deliver a widget.")])
    fn = _fake_fn({chunk.text: batch})

    first = extract_requirements([chunk], model="fake", extract_fn=fn)
    second = extract_requirements([chunk], model="fake", extract_fn=fn)

    assert len(first) == 1
    row = first[0]
    assert row.verified is False
    assert row.source_ref.verified is False
    assert row.source_ref.page is None
    # Not dropped, and the id is identical across re-runs (draft-index fallback).
    assert [r.requirement_id for r in first] == [r.requirement_id for r in second]


# --- (c) req_type from chunk role (the two previously-omitted roles) -----------


def test_req_type_special_requirements_from_role_overrides_guess():
    verbatim = "The contractor shall comply with all safety requirements."
    chunk = _chunk(verbatim, role="special_requirements", section_label="H")
    # type_guess deliberately wrong to prove the section role wins.
    batch = RequirementBatch(
        requirements=[_draft(verbatim, "Comply with safety requirements.", type_guess="other")]
    )
    reqs = extract_requirements(
        [chunk], model="fake", extract_fn=_fake_fn({chunk.text: batch})
    )
    assert reqs[0].req_type == "special_requirements"


def test_req_type_attachments_list_role_maps_to_attachment():
    verbatim = "Attachment 3 provides the CDRL list the contractor shall deliver."
    chunk = _chunk(verbatim, role="attachments_list", section_label="J")
    batch = RequirementBatch(
        requirements=[_draft(verbatim, "Deliver the CDRLs.", type_guess="other")]
    )
    reqs = extract_requirements(
        [chunk], model="fake", extract_fn=_fake_fn({chunk.text: batch})
    )
    assert reqs[0].req_type == "attachment"


def test_req_type_falls_back_to_guess_when_role_none():
    verbatim = "The offeror shall provide a cover letter."
    chunk = _chunk(verbatim, role=None)
    batch = RequirementBatch(
        requirements=[_draft(verbatim, "Provide a cover letter.", type_guess="instruction")]
    )
    reqs = extract_requirements(
        [chunk], model="fake", extract_fn=_fake_fn({chunk.text: batch})
    )
    assert reqs[0].req_type == "instruction"


# --- (d) per-chunk parse failure is isolated ----------------------------------


def test_parse_error_in_one_chunk_does_not_crash_run():
    good = _chunk("SECTION L. The offeror shall submit a technical volume.", file_id="good")
    bad = _chunk("SECTION M. malformed section triggers a parse failure.", file_id="bad")
    good_verbatim = "The offeror shall submit a technical volume."
    good_batch = RequirementBatch(
        requirements=[_draft(good_verbatim, "Submit a technical volume.")]
    )

    def fn(chunk_text: str, model: str, seed: int = 7) -> RequirementBatch:
        if chunk_text == bad.text:
            raise ExtractionParseError("truncated JSON")
        return good_batch

    reqs = extract_requirements([bad, good], model="fake", extract_fn=fn)

    # The bad chunk is skipped; the good chunk's requirement survives.
    assert len(reqs) == 1
    assert reqs[0].verbatim_text == good_verbatim
    assert reqs[0].source_ref.file_id == "good"


# --- (e) doc_role survives onto an ungroundable amendment row ------------------


def test_ungroundable_amendment_row_keeps_doc_role():
    chunk = _chunk(
        "AMENDMENT 0001. Item 14 changes are described herein.",
        doc_role="amendment",
        file_id="amd",
    )
    absent = "Section L.4.2 is changed to read: the page limit shall be 30 pages."
    batch = RequirementBatch(requirements=[_draft(absent, "Page limit is 30 pages.")])
    reqs = extract_requirements(
        [chunk], model="fake", extract_fn=_fake_fn({chunk.text: batch})
    )
    assert reqs[0].verified is False
    assert reqs[0].source_ref.doc_role == "amendment"
