"""Cross-mapping: which requirements have counterparts across L, M, and C/SOW.

ANLZ-01. A federal proposal is lost in the gaps, not in the prose:

- **L without M** — the RFP tells you to write something nobody scores. Often a
  compliance trap: cheap to satisfy, and omitting it can still make you
  non-responsive.
- **M without L** — you are scored on something no instruction told you to
  submit. This is the expensive one; teams discover it after the debrief.
- **SOW without either** — a performance obligation that neither instructs nor
  scores, but that you are on the hook to deliver post-award.

Everything here is deterministic string similarity over already-extracted rows.
No engine, no judgment, so a reported gap is reproducible and cannot be
hallucinated — which matters because a *false* gap sends a proposal team chasing
work that does not exist.

STATUS (measured on N4008526R0033, 2026-07-24) — PARTIALLY FIXED
------------------------------------------------------------------------------
The first cut of this module reported mostly FALSE gaps, for a structural reason
rather than a tuning one: this RFP delegates Section L's content to Section M
("responses to each non-price factor as specified in Section M"), so M carries
the real submittal instructions. Typing rows by their section then filed those
offeror duties on the evaluation side and reported them as "scored but never
instructed".

FIXED — requirements are now typed by ACTOR (see ``pipeline.actor``): whoever
owes the duty decides, so an offeror duty in Section M is an ``instruction``
wherever it is filed. 29 Section M rows reclassified (evaluation 83->53,
instruction 57->87), and de-duplication now keeps the deepest section path
(L.5, M.2) instead of the coarse parent, so a section anchor is available at all.
M-without-L rows are now genuinely Government-voice evaluation actions ("Price
is evaluated on total price", "Award goes to the responsible Offeror..."), and
real pairs link correctly ("An incumbent shall tailor the Phase-in Transition
Plan" <-> "An incumbent's Phase-in Transition Plan is evaluated on continuity of
services", score 84).

STILL WEAK — two known problems, so treat gap output as advisory:

1. **No per-factor anchor.** Structurally similar sentences about different
   evaluation factors still link: "Limit the Factor 1 narrative to 25
   single-sided pages" matches "Limit the Technical Approach to Safety narrative
   to seven single-sided pages" at 88. The fix is to anchor on the evaluation
   factor, which needs sub-section structure BELOW M.2 (per-factor headings like
   "(2) Factor 2, Corporate Experience") that the Phase 1 sectioner does not
   currently emit. Explicit "Factor N" text is not a usable substitute: only 2 of
   277 rows contain one.
2. **Award-process statements are not really gaps.** Rows like "Award goes to the
   responsible Offeror whose conforming offer is the best value" are evaluation
   *mechanics*, not criteria an offeror must be instructed toward, yet they land
   in ``m_without_l``. They need a third disposition rather than a gap label.

Until both are addressed, gaps are ADVISORY: useful for a human reviewer,
not yet a column to hand a proposal team unqualified.
"""

from __future__ import annotations

from collections.abc import Iterable

from rapidfuzz import fuzz

from rfp_analyzer.pipeline.grounding.normalize import normalize
from rfp_analyzer.pipeline.models import CrossMapping, Requirement

MATCH_THRESHOLD = 55.0
"""Similarity floor (0-100) for calling two requirements counterparts.

Lower than the grounding threshold because L and M describe the same duty in
different voices ("the Offeror shall submit a phase-in plan" vs "the Government
will evaluate the feasibility of the phase-in plan"), so near-identity would
report gaps that are not gaps.

⚠ Still coarse. After the actor-typing fix (see module docstring) 55.0 maps 26%
of rows on N4008526R0033 with genuine L<->M pairs among them, but structurally
similar sentences about DIFFERENT evaluation factors still link. Treat mapped/
gapped as advisory until per-factor anchoring lands.
"""

_L_TYPES = {"instruction"}
_M_TYPES = {"evaluation"}
_SOW_TYPES = {"sow_pws", "special_requirements", "clause", "attachment", "other"}


def _bucket(req: Requirement) -> str:
    """Return ``"L"``, ``"M"``, or ``"C"`` for a requirement.

    Uses ``req_type`` (reconciled from the owning section's role in 02-05), not
    the section label, so an instruction living in an attachment still counts as
    an L-side duty.
    """
    if req.req_type in _L_TYPES:
        return "L"
    if req.req_type in _M_TYPES:
        return "M"
    return "C"


def _text(req: Requirement) -> str:
    """The comparison text: the atomic obligation, falling back to the verbatim.

    ``atomic_obligation`` is the single-duty rewrite, so it strips the legal
    scaffolding ("Offerors are advised that...") that otherwise dominates a
    similarity score and links unrelated rows.
    """
    return normalize(req.atomic_obligation or req.verbatim_text)


def _best_matches(
    req: Requirement, pool: list[Requirement], thresh: float
) -> tuple[list[str], float]:
    """Return ids of counterparts in ``pool`` clearing ``thresh``, best score first."""
    target = _text(req)
    scored: list[tuple[float, str]] = []
    for other in pool:
        score = fuzz.token_set_ratio(target, _text(other))
        if score >= thresh:
            scored.append((score, other.requirement_id))
    if not scored:
        return [], 0.0
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [rid for _s, rid in scored], scored[0][0]


def cross_map(
    requirements: Iterable[Requirement], thresh: float = MATCH_THRESHOLD
) -> list[CrossMapping]:
    """Return one :class:`CrossMapping` per requirement — mapped rows AND gaps.

    Every requirement gets a row. A gap is not an absence to be filtered out; it
    is the finding, and a matrix that silently omitted unmapped rows would hide
    exactly what the analysis exists to surface.

    L rows look for M counterparts and vice versa; C/SOW rows look at both sides
    and are flagged only when neither instructs nor evaluates them.
    """
    reqs = list(requirements)
    by_bucket: dict[str, list[Requirement]] = {"L": [], "M": [], "C": []}
    for req in reqs:
        by_bucket[_bucket(req)].append(req)

    out: list[CrossMapping] = []
    for req in reqs:
        bucket = _bucket(req)
        if bucket == "L":
            ids, score = _best_matches(req, by_bucket["M"], thresh)
            kind = "mapped" if ids else "l_without_m"
            why = (
                f"matched {len(ids)} Section M criterion/criteria"
                if ids
                else "no Section M evaluation criterion covers this instruction — "
                "work that will not be scored"
            )
        elif bucket == "M":
            ids, score = _best_matches(req, by_bucket["L"], thresh)
            kind = "mapped" if ids else "m_without_l"
            why = (
                f"matched {len(ids)} Section L instruction(s)"
                if ids
                else "no Section L instruction tells the offeror to submit what this "
                "criterion scores"
            )
        else:
            ids, score = _best_matches(req, by_bucket["L"] + by_bucket["M"], thresh)
            kind = "mapped" if ids else "sow_without_either"
            why = (
                f"matched {len(ids)} L/M requirement(s)"
                if ids
                else "performance obligation with no instruction and no evaluation "
                "criterion — deliverable post-award, invisible pre-award"
            )
        out.append(
            CrossMapping(
                requirement_id=req.requirement_id,
                counterpart_ids=ids,
                gap_kind=kind,
                rationale=why,
                score=score,
            )
        )
    return out


def gap_summary(mappings: Iterable[CrossMapping]) -> dict[str, int]:
    """Count rows per gap kind — the headline the CLI report and export lead with."""
    counts = {"mapped": 0, "l_without_m": 0, "m_without_l": 0, "sow_without_either": 0}
    for mapping in mappings:
        counts[mapping.gap_kind] = counts.get(mapping.gap_kind, 0) + 1
    return counts
