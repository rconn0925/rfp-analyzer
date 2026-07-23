"""Run-level metrics scaffolding (D-09).

Phase 1 makes zero LLM calls, but the cost-instrumentation fields exist now
so Phase 2 can populate them without a schema change. LLM fields default to
zero and stay zero in this phase.
"""

from pydantic import BaseModel, Field


class RunMetrics(BaseModel):
    """Counters and timings for one pipeline run.

    ``stage_timings`` maps stage names (e.g. ``"parsing"``, ``"quality"``,
    ``"sectioning"``, ``"classify"``) to elapsed wall-clock seconds.
    """

    stage_timings: dict[str, float] = Field(default_factory=dict)
    files_parsed: int = 0
    pages_parsed: int = 0
    pages_flagged: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
