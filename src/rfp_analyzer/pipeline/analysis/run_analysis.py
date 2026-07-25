"""Single pipeline entry: RequirementSet + DocumentMap -> ComplianceMatrix.

Mirrors ``run_extraction``'s shape — pure library, no printing, no CLI imports,
stage timings into ``RunMetrics.stage_timings``.

Order matters: the two deterministic stages (cross-map, outline) run first and
always, so a matrix has real analytical value even when no judgment has been
recorded. Judgment is layered on top and is optional by design, because it is the
only stage that needs the engine.
"""

from __future__ import annotations

import time

from rfp_analyzer.pipeline.analysis.crossmap import cross_map
from rfp_analyzer.pipeline.analysis.factors import assign_factors, factor_anchors
from rfp_analyzer.pipeline.analysis.judge import DEMO_PROFILE, apply_verdicts
from rfp_analyzer.pipeline.analysis.outline import derive_outline, map_requirements
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    ComplianceJudgment,
    ComplianceMatrix,
    DocumentMap,
    RequirementSet,
)


def run_analysis(
    document_map: DocumentMap,
    requirement_set: RequirementSet,
    profile: CapabilityProfile | None = None,
    verdicts: dict[str, ComplianceJudgment] | None = None,
) -> ComplianceMatrix:
    """Compose cross-map -> outline -> judgment into a :class:`ComplianceMatrix`.

    ``verdicts`` is optional: without it the matrix carries no judgments and the
    export says "not judged" per row rather than implying compliance. ``profile``
    defaults to the fictional demo profile, which is labelled as such all the way
    into the workbook.
    """
    profile = profile or DEMO_PROFILE
    metrics = RunMetrics()
    timings: dict[str, float] = {}
    reqs = requirement_set.requirements

    t0 = time.perf_counter()
    factors = assign_factors(reqs, factor_anchors(document_map), document_map)
    mappings = cross_map(reqs, factors=factors)
    timings["crossmap"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    outline = derive_outline(document_map)
    requirement_outline = map_requirements(reqs, outline)
    timings["outline"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    judgments = apply_verdicts(reqs, verdicts) if verdicts else []
    timings["judgment"] = time.perf_counter() - t0

    metrics.stage_timings = timings
    metrics.chunks_total = requirement_set.metrics.chunks_total
    metrics.chunks_unextracted = requirement_set.metrics.chunks_unextracted

    return ComplianceMatrix(
        package_name=requirement_set.package_name,
        profile=profile,
        requirements=reqs,
        cross_mappings=mappings,
        outline=outline,
        requirement_outline=requirement_outline,
        judgments=judgments,
        missed_candidates=requirement_set.missed_candidates,
        metrics=metrics,
    )
