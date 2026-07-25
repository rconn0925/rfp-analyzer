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

STATUS (re-measured on N4008526R0033, 2026-07-25) — FACTOR-ANCHORED
------------------------------------------------------------------------------
Two structural defects made the first cut report mostly FALSE gaps. Both are now
fixed, so gap output is no longer advisory-only.

1. **Section typing.** This RFP delegates Section L's content to Section M
   ("responses to each non-price factor as specified in Section M"), so M carries
   the real submittal instructions. Typing rows by their section filed those
   offeror duties on the evaluation side and reported them as "scored but never
   instructed". FIXED by typing on ACTOR (``pipeline.actor``): whoever owes the
   duty decides, so an offeror duty in Section M is an ``instruction`` wherever
   it is filed.

2. **No factor anchor.** Similarity alone linked structurally identical sentences
   about different factors — "Limit the Factor 1 narrative to 25 single-sided
   pages" scored 88 against "Limit the Technical Approach to Safety narrative to
   seven single-sided pages". FIXED by ``pipeline.analysis.factors``: a
   requirement inherits the factor whose line-anchored heading precedes its
   grounded position, and matching factors is a hard gate. 14 cross-factor links
   removed on the real package.

Award mechanics also got their own disposition. An evaluation statement under no
evaluation factor ("Price is evaluated on total price") describes how the
competition is run, not a criterion any submittal answers, so it reports as
``evaluation_process`` rather than a gap a team would go chasing.

Remaining known limit: an L-side row and an M-side row can still link on
similarity when neither carries a factor (Section L's own subsections have no
factor structure in this RFP). That is a smaller surface than before, but it is
why counterpart links are still worth a human glance.
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

With actor typing and factor anchoring in place, 55.0 maps 65 of 277 rows on
N4008526R0033 and the cross-factor false links are gone. The threshold now only
has to separate genuine paraphrase pairs WITHIN a factor, which is the job it is
actually suited to.
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
    req: Requirement,
    pool: list[Requirement],
    thresh: float,
    factors: dict[str, str] | None = None,
) -> tuple[list[str], float]:
    """Return ids of counterparts in ``pool`` clearing ``thresh``, best score first.

    When BOTH rows carry an evaluation factor, matching factors is a hard gate:
    a proposal is organised by factor, so two requirements under different
    factors are not counterparts however similarly they are worded. When either
    side has no factor (Section L rows, award-mechanics preamble), similarity
    decides alone — a gate cannot be applied to information that isn't there.
    """
    target = _text(req)
    factors = factors or {}
    own_factor = factors.get(req.requirement_id)
    scored: list[tuple[float, str]] = []
    for other in pool:
        other_factor = factors.get(other.requirement_id)
        if own_factor and other_factor and own_factor != other_factor:
            continue
        score = fuzz.token_set_ratio(target, _text(other))
        if score >= thresh:
            scored.append((score, other.requirement_id))
    if not scored:
        return [], 0.0
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [rid for _s, rid in scored], scored[0][0]


def cross_map(
    requirements: Iterable[Requirement],
    thresh: float = MATCH_THRESHOLD,
    factors: dict[str, str] | None = None,
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
            ids, score = _best_matches(req, by_bucket["M"], thresh, factors)
            kind = "mapped" if ids else "l_without_m"
            why = (
                f"matched {len(ids)} Section M criterion/criteria"
                if ids
                else "no Section M evaluation criterion covers this instruction — "
                "work that will not be scored"
            )
        elif bucket == "M":
            ids, score = _best_matches(req, by_bucket["L"], thresh, factors)
            if ids:
                kind, why = "mapped", f"matched {len(ids)} Section L instruction(s)"
            elif not (factors or {}).get(req.requirement_id):
                # An evaluation statement under no evaluation factor is award
                # MECHANICS ("Award goes to the responsible Offeror...", "Price is
                # evaluated on total price") — it describes how the competition is
                # run, not a criterion any submittal answers. Calling that a gap
                # sends a proposal team looking for an instruction that should not
                # exist, so it gets its own disposition rather than a false alarm.
                kind, why = (
                    "evaluation_process",
                    "award/evaluation mechanics under no evaluation factor — describes "
                    "how the competition is run, not a criterion a submittal answers",
                )
            else:
                kind, why = (
                    "m_without_l",
                    "no Section L instruction tells the offeror to submit what this "
                    "criterion scores",
                )
        else:
            ids, score = _best_matches(req, by_bucket["L"] + by_bucket["M"], thresh, factors)
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
    counts = {
        "mapped": 0, "l_without_m": 0, "m_without_l": 0,
        "sow_without_either": 0, "evaluation_process": 0,
    }
    for mapping in mappings:
        counts[mapping.gap_kind] = counts.get(mapping.gap_kind, 0) + 1
    return counts
