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

LIMITATION (measured on N4008526R0033, 2026-07-24) — READ BEFORE SHIPPING GAPS
------------------------------------------------------------------------------
Text similarity alone does not recover L<->M correspondence in this package, and
probably not in FAR solicitations generally. Two findings:

1. **This RFP delegates L's content to M.** Section L says only "The non-price
   proposal shall include responses to each non-price factor as specified in
   Section M"; the actual submittal instructions for Factors 1-4 live *inside*
   Section M under "(i) Solicitation Submittal Requirements". Measured topic
   coverage over the extracted rows: phase-in L=0/M=3, workforce L=0/M=3,
   safety L=0/M=15, corporate experience L=0/M=5. So nearly every substantive M
   row is correctly *un*matched in L — and reporting those as "m_without_l" gaps
   would be flatly wrong. They are not gaps; they are the RFP's structure.

2. **Consequently ``req_type`` mislabels them.** The 02-05 rule "the owning
   section's role wins" types everything in Section M as ``evaluation``, but
   M's Solicitation Submittal Requirements subsections are *instructions*
   ("The Offeror shall submit a narrative response..."). Bucketing by req_type
   therefore puts real instructions on the M side.

Recommended fix (needs a design decision, not a threshold tweak): anchor
cross-mapping on the **evaluation factor** — the axis a FAR proposal is actually
organized by — rather than on paraphrase similarity. That requires sub-section
structure (L.5, M.2, "Factor 2, Corporate Experience") to reach the Requirement,
which today's coarse ``section_label`` (L / M / C only) does not carry, and a
``req_type`` rule that distinguishes M's submittal subsections from its
evaluation criteria. Explicit "Factor N" text is not a usable anchor on its own:
only 2 of 277 rows mention one.

Until then this module is wired but its gap output is NOT export-ready.
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

⚠ **UNVALIDATED — do not present this module's gaps to a proposal team yet.**
Measured on N4008526R0033 (277 requirements), the threshold has no stable
operating point: 45.0 maps 95% of rows, 55.0 maps 22%, 65.0 maps 4%. Scores
cluster so tightly that "mapped" at 55.0 includes clear false links (e.g.
"Certify in writing on page 1 of the proposal" scored 60 against "Tab each
listed topic in the non-price proposal"). See the module docstring's LIMITATION
note for the underlying reason and the recommended fix.
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
