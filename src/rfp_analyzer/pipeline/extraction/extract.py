"""Orchestration: turn chunks into grounded, atomic, typed Requirements.

This is the chunk -> ground -> assemble wiring (EXTR-01/02/03). For each chunk it
calls the model (via an injectable ``extract_fn`` so the whole path is
CI-testable without a GPU), grounds every draft's ``verbatim_text`` through
``build_source_ref`` (which threads ``chunk.doc_role`` onto the SourceRef on both
the grounded and the ungroundable path), assigns content-derived stable ids, and
reconciles each row's ``req_type`` from the owning section role.

Honesty invariants preserved from the phase design:

- **Ungroundable drafts are retained, never dropped** (``verified=False``,
  ``page=None``) so hallucination and grounding bugs stay visible.
- **Ids are deterministic and stable across re-runs**, including for ungroundable
  rows (which have no grounded span to order by) — they fall back to the draft's
  index within its chunk's batch.
- **Atomic siblings share one verified SourceRef** but get distinct ids via
  ``atomic_ord``, and link to their group's first row through ``parent_id``.
- **``source_ref.doc_role`` survives onto the Requirement** so INTK-03 amendment
  gating can distinguish amendment rows without re-reading the chunk.
- **A per-chunk parse failure is isolated** — one bad chunk is skipped, the run
  continues.

Pure library code: the engine arrives through the injected ``extract_fn``; this
module imports no engine, web, CLI, or queue code itself.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable

from rfp_analyzer.pipeline.actor import classify_actor
from rfp_analyzer.pipeline.extraction.replay import ExtractionParseError
from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.grounding.verify import build_source_ref
from rfp_analyzer.pipeline.ids import display_label, requirement_id
from rfp_analyzer.pipeline.models import (
    Chunk,
    Requirement,
    RequirementBatch,
    RequirementDraft,
    SourceRef,
)

ExtractFn = Callable[[str, str, int], RequirementBatch]
"""Signature of the engine dependency: ``(chunk_text, model, seed) -> batch``.

Always injected — there is no in-process engine to default to. In production it
is a :class:`~rfp_analyzer.pipeline.extraction.replay.ReplayEngine` over drafts
recorded by Claude Code; tests pass a fake returning canned batches."""

# EXTR-03: the COMPLETE SectionNode.role -> req_type map. Every role value the
# schema allows is mapped explicitly; only role=None ever defers to the model's
# type_guess. No role silently falls through.
_ROLE_TO_REQ_TYPE: dict[str, str] = {
    "instructions": "instruction",
    "evaluation": "evaluation",
    "sow_pws": "sow_pws",
    "special_requirements": "special_requirements",
    "clauses": "clause",
    "attachments_list": "attachment",
    "other": "other",
}


def _is_lm_context(role: str | None, section_label: str | None) -> bool:
    """True when a requirement sits in Section L or M, however the chunk is labelled.

    Checks the section label as well as the role because only the TOP-LEVEL
    section chunk carries a role — ``iter_chunks`` emits "L.5" and "M.2" with
    ``role=None`` — and the deepest chunk is the one that wins de-duplication.
    Keying on the role alone therefore never fires for exactly the nested
    subsections this rule exists to fix.
    """
    if role in ("instructions", "evaluation"):
        return True
    if not section_label:
        return False
    head = section_label.split(".", 1)[0].strip()
    return head in ("L", "M")


def _reconcile_type(
    role: str | None,
    type_guess: str,
    verbatim: str = "",
    section_label: str | None = None,
) -> str:
    """Return the req_type: actor decides inside L/M; the section role decides elsewhere.

    The original rule was "the owning section's role always wins". Measured on
    N4008526R0033 that mistypes a large class of rows: FAR solicitations file
    *submittal instructions* inside Section M under "(i) Solicitation Submittal
    Requirements", and this RFP delegates Section L's content to M wholesale. The
    role rule then labels real offeror duties ``evaluation``, which in turn makes
    cross-mapping report them as scored-but-never-instructed gaps that don't exist.

    So for the two roles where the distinction is load-bearing (instructions and
    evaluation), who owes the duty decides: an offeror duty is an ``instruction``
    wherever it is filed, and a Government evaluation action is an ``evaluation``.
    ``other``-actor rows keep the section's role, since a page-limit note or
    definition belongs with its section. Every other role is unchanged.
    """
    if verbatim and _is_lm_context(role, section_label):
        actor = classify_actor(verbatim)
        if actor == "offeror":
            return "instruction"
        if actor == "government":
            return "evaluation"
        # actor "other": fall through to the section's role below.
    if role is None:
        return type_guess
    # Every enum role value is in the map; an unexpected value degrades to the
    # model guess rather than inventing a type.
    return _ROLE_TO_REQ_TYPE.get(role, type_guess)


def _depth(section_label: str | None) -> int:
    """Nesting depth of a section label ("L" -> 1, "L.5" -> 2). None sorts last."""
    return section_label.count(".") + 1 if section_label else 0


def _root_index(drafts: list[RequirementDraft], i: int) -> int:
    """Return the group-root draft index for draft ``i``.

    A standalone or first-of-group draft (``parent_index is None``) roots itself;
    a sibling points ``parent_index`` at the group's first row. Out-of-range or
    self-referential parents degrade to self-rooting (defensive against a stray
    model index).
    """
    parent = drafts[i].parent_index
    if parent is None:
        return i
    if 0 <= parent < len(drafts) and parent != i:
        return parent
    return i


def _atomic_ords(drafts: list[RequirementDraft]) -> dict[int, int]:
    """Assign each draft its ordinal within its atomic-sibling group (0-based).

    Siblings share one ``verbatim_text``; ``atomic_ord`` is what keeps their
    otherwise-identical stable-id keys distinct. The root (smallest index) gets
    0, later siblings 1, 2, ... in array order.
    """
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(drafts)):
        groups[_root_index(drafts, i)].append(i)
    ords: dict[int, int] = {}
    for members in groups.values():
        for ordinal, i in enumerate(sorted(members)):
            ords[i] = ordinal
    return ords


def _occurrences(drafts: list[RequirementDraft], refs: list[SourceRef]) -> dict[int, int]:
    """Assign each draft its ``occurrence`` index for the stable-id key.

    Two regimes, both deterministic and re-run-stable:

    - GROUNDED (``verified``): rank of the draft's grounded ``(page, char_start)``
      span among the distinct grounded positions of the same normalized verbatim
      within this chunk. Identical verbatims ground to the same span, so they
      share occurrence 0 and collapse under de-duplication — intended for
      overlap-window dupes.
    - UNGROUNDABLE: no grounded span to order by, so fall back to the draft's
      index within the chunk's batch. Chunks come from deterministic
      ``iter_chunks`` order, so unverified rows still get stable, identical ids
      across re-runs and never collide with one another.
    """
    positions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for draft, ref in zip(drafts, refs, strict=True):
        if ref.verified:
            key = (ref.page if ref.page is not None else -1,
                   ref.char_start if ref.char_start is not None else -1)
            bucket = positions[normalize(draft.verbatim_text)]
            if key not in bucket:
                bucket.append(key)
    for bucket in positions.values():
        bucket.sort()

    occ: dict[int, int] = {}
    for i, (draft, ref) in enumerate(zip(drafts, refs, strict=True)):
        if ref.verified:
            key = (ref.page if ref.page is not None else -1,
                   ref.char_start if ref.char_start is not None else -1)
            occ[i] = positions[normalize(draft.verbatim_text)].index(key)
        else:
            occ[i] = i
    return occ


def extract_requirements(
    chunks: Iterable[Chunk],
    model: str,
    seed: int = 7,
    *,
    extract_fn: ExtractFn,
) -> list[Requirement]:
    """Assemble grounded, atomic, stably-identified Requirements from chunks.

    ``extract_fn`` is the injected engine and is REQUIRED — keyword-only so it
    can never be supplied by accident, and with no default because there is no
    in-process model to fall back to. Requirements are returned in
    chunk-then-draft order with de-duplication by ``requirement_id`` (overlap-window
    dupes collapse).
    """
    out: list[Requirement] = []
    seen: dict[str, int] = {}
    section_ordinals: dict[str, int] = defaultdict(int)

    for chunk in chunks:
        try:
            batch = extract_fn(chunk.text, model, seed)
        except ExtractionParseError:
            # Isolated per-chunk failure (Pitfall 3): skip this chunk, keep going.
            continue

        drafts = list(batch.requirements)
        if not drafts:
            continue

        refs = [build_source_ref(d.verbatim_text, chunk) for d in drafts]
        atomic_ord = _atomic_ords(drafts)
        occurrence = _occurrences(drafts, refs)

        # Stable ids for every draft first, so a child can resolve its root's id.
        draft_ids = [
            requirement_id(chunk.file_id, d.verbatim_text, occurrence[i], atomic_ord[i])
            for i, d in enumerate(drafts)
        ]

        for i, draft in enumerate(drafts):
            rid = draft_ids[i]
            if rid in seen:
                # Overlap-window / nested-section duplicate. Collapse — but keep
                # the MOST SPECIFIC section, because iter_chunks walks the parent
                # section before its children, so first-wins would permanently
                # label every row with the coarse "L"/"M" and discard the "L.5" /
                # "M.2" path that cross-mapping needs to anchor on.
                prior = out[seen[rid]]
                if _depth(chunk.section_label) > _depth(prior.source_ref.section_label):
                    prior.source_ref.section_label = chunk.section_label
                    prior.req_type = _reconcile_type(
                        chunk.role, draft.type_guess, draft.verbatim_text, chunk.section_label
                    )
                continue
            seen[rid] = len(out)

            root = _root_index(drafts, i)
            parent_id = draft_ids[root] if root != i else None

            section_ordinals[chunk.section_label] += 1
            label = display_label(chunk.section_label, section_ordinals[chunk.section_label])

            out.append(
                Requirement(
                    requirement_id=rid,
                    display_label=label,
                    verbatim_text=draft.verbatim_text,
                    atomic_obligation=draft.atomic_obligation,
                    binding_keyword=draft.binding_keyword,
                    req_type=_reconcile_type(
                        chunk.role, draft.type_guess, draft.verbatim_text, chunk.section_label
                    ),
                    source_ref=refs[i],
                    verified=refs[i].verified,
                    parent_id=parent_id,
                )
            )

    return out
