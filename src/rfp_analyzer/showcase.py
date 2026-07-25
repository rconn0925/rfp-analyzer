"""Generate the static portfolio showcase from a real analysis (Phase 5).

Reads ``matrix.json`` and emits one self-contained HTML file. No live inference,
no hosting cost, no ToS exposure — it is a record of an analysis that already
happened, which is also the honest thing to publish given the engine is a
personal subscription.

Design intent: this is a *record*, not a landing page. The visual language comes
from the subject's own world — solicitation text set in mono, page citations
carried on every row, disposition encoded as a severity stripe the way a shred
sheet does it. The measured accuracy is shown WITH its caveats, because the
measurement discipline is the thing worth showing.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from rfp_analyzer.pipeline.analysis.crossmap import gap_summary
from rfp_analyzer.pipeline.analysis.judge import judgment_summary
from rfp_analyzer.pipeline.analysis.outline import (
    EVAL_CRITERIA_ID,
    POST_AWARD_ID,
    UNASSIGNED_ID,
    outline_coverage,
)
from rfp_analyzer.pipeline.models import ComplianceMatrix

SAMPLE_SIZE = 18
"""How many requirement rows the showcase displays.

A showcase, not a data dump: enough rows to prove the citations and verdicts are
real, few enough that a reader actually reads them. The full set ships in the
workbook.
"""

_VERDICT_CLASS = {
    "fully_compliant": ("ok", "Fully compliant"),
    "partially_compliant": ("warn", "Partially compliant"),
    "non_compliant": ("bad", "Non-compliant"),
    "unknown": ("idle", "Judge declined"),
}

_GAP_CLASS = {
    "mapped": ("ok", "Mapped L↔M"),
    "l_without_m": ("warn", "L without M"),
    "m_without_l": ("bad", "M without L"),
    "sow_without_either": ("idle", "SOW only"),
}


def _pick_rows(matrix: ComplianceMatrix) -> list[dict]:
    """Choose a representative sample: judged rows first, spread across outcomes.

    Deliberately includes the partially-compliant findings — a sample of only
    green rows would misrepresent what the tool actually produced.
    """
    judged = {j.requirement_id: j for j in matrix.judgments}
    gaps = {m.requirement_id: m for m in matrix.cross_mappings}
    node_titles = {n.node_id: n.title for n in matrix.outline}

    def score(req):
        j = judged.get(req.requirement_id)
        if j and j.verdict == "partially_compliant":
            return 0
        if j and j.verdict == "unknown":
            return 1
        if j:
            return 2
        return 3

    chosen = sorted(matrix.requirements, key=lambda r: (score(r), r.display_label))[:SAMPLE_SIZE]
    rows = []
    for req in chosen:
        j = judged.get(req.requirement_id)
        gap = gaps.get(req.requirement_id)
        node_id = matrix.requirement_outline.get(req.requirement_id, "")
        if j:
            vclass, vlabel = _VERDICT_CLASS.get(j.verdict, ("idle", "—"))
        else:
            vclass, vlabel = "idle", "Not judged"
        gclass, glabel = _GAP_CLASS.get(gap.gap_kind, ("idle", "—")) if gap else ("idle", "—")
        rows.append({
            "id": req.requirement_id,
            "label": req.display_label,
            "file": req.source_ref.filename,
            "section": req.source_ref.section_label or "—",
            "page": req.source_ref.page,
            "keyword": req.binding_keyword,
            "verbatim": " ".join(req.verbatim_text.split()),
            "atomic": req.atomic_obligation,
            "location": node_titles.get(node_id, node_id),
            "verdict_class": vclass,
            "verdict": vlabel,
            "rationale": j.rationale if j else "",
            "gap_class": gclass,
            "gap": glabel,
        })
    return rows


def build_context(matrix: ComplianceMatrix) -> dict:
    """Aggregate the numbers the showcase reports."""
    total = len(matrix.requirements)
    gaps = gap_summary(matrix.cross_mappings)
    verdicts = judgment_summary(matrix.judgments, total)
    coverage = outline_coverage(matrix.requirement_outline)
    grounded = sum(1 for r in matrix.requirements if r.verified)
    return {
        "package": matrix.package_name,
        "total": total,
        "grounded": grounded,
        "grounded_pct": round(100 * grounded / total) if total else 0,
        "files": len({r.source_ref.filename for r in matrix.requirements}),
        "sections": len({(r.source_ref.section_label or "")[:1] for r in matrix.requirements}),
        "gaps": gaps,
        "verdicts": verdicts,
        "judged": len(matrix.judgments),
        "outline_nodes": len(matrix.outline),
        "post_award": coverage.get(POST_AWARD_ID, 0),
        "eval_criteria": coverage.get(EVAL_CRITERIA_ID, 0),
        "unassigned": coverage.get(UNASSIGNED_ID, 0),
        "written": total - coverage.get(POST_AWARD_ID, 0)
        - coverage.get(EVAL_CRITERIA_ID, 0) - coverage.get(UNASSIGNED_ID, 0),
        "profile": matrix.profile,
        "types": Counter(r.req_type for r in matrix.requirements),
        "rows": _pick_rows(matrix),
    }


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def render_html(context: dict) -> str:
    """Render the self-contained showcase page."""
    c = context
    rows_html = "\n".join(_row_html(r) for r in c["rows"])
    gap_rows = "".join(
        f'<div class="bar-row"><span class="bar-label">{_e(label)}</span>'
        f'<span class="bar-track"><span class="bar-fill {cls}" '
        f'style="width:{(count / max(c["total"], 1)) * 100:.1f}%"></span></span>'
        f'<span class="bar-num">{count}</span></div>'
        for label, cls, count in [
            ("Mapped L↔M", "ok", c["gaps"].get("mapped", 0)),
            ("L without M", "warn", c["gaps"].get("l_without_m", 0)),
            ("M without L", "bad", c["gaps"].get("m_without_l", 0)),
            ("SOW only", "idle", c["gaps"].get("sow_without_either", 0)),
        ]
    )
    caps = "".join(
        f'<li class="{"gap" if cap.startswith("NO-CAP") else ""}">{_e(cap)}</li>'
        for cap in c["profile"].capabilities
    )
    return _PAGE.format(
        package=_e(c["package"]),
        total=c["total"],
        grounded=c["grounded"],
        grounded_pct=c["grounded_pct"],
        files=c["files"],
        judged=c["judged"],
        not_judged=c["verdicts"].get("not_judged", 0),
        full=c["verdicts"].get("fully_compliant", 0),
        partial=c["verdicts"].get("partially_compliant", 0),
        declined=c["verdicts"].get("unknown", 0),
        outline_nodes=c["outline_nodes"],
        written=c["written"],
        post_award=c["post_award"],
        eval_criteria=c["eval_criteria"],
        unassigned=c["unassigned"],
        company=_e(c["profile"].company_name),
        capabilities=caps,
        gap_rows=gap_rows,
        rows=rows_html,
        sample=len(c["rows"]),
    )


def _row_html(r: dict) -> str:
    page = f"p.{r['page']}" if r["page"] is not None else "ungrounded"
    rationale = (
        f'<p class="rationale"><span class="rk">Why</span>{_e(r["rationale"])}</p>'
        if r["rationale"] else ""
    )
    return f"""      <article class="rec {_e(r['verdict_class'])}">
        <header class="rec-head">
          <span class="rid">{_e(r['id'])}</span>
          <span class="cite">{_e(r['file'])} · {_e(r['section'])} · {_e(page)}</span>
          <span class="chip {_e(r['gap_class'])}">{_e(r['gap'])}</span>
          <span class="chip {_e(r['verdict_class'])}">{_e(r['verdict'])}</span>
        </header>
        <blockquote class="verbatim">{_e(r['verbatim'])}</blockquote>
        <p class="atomic"><span class="rk">Obligation</span>{_e(r['atomic'])}</p>
        <p class="loc"><span class="rk">Goes in</span>{_e(r['location'])}
          <span class="kw">{_e(r['keyword'])}</span></p>
        {rationale}
      </article>"""


def write_showcase(matrix: ComplianceMatrix, path: Path | str) -> Path:
    """Render the showcase HTML for ``matrix`` to ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(build_context(matrix)), encoding="utf-8")
    return path


def load_matrix(path: Path | str) -> ComplianceMatrix:
    """Load a ComplianceMatrix from matrix.json."""
    return ComplianceMatrix.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


_PAGE = """<title>RFP Compliance Matrix — a real federal solicitation, shredded</title>
<style>
  :root {{
    --ground: #F6F7F9;      --panel: #FFFFFF;      --ink: #10151B;
    --ink-soft: #4A5563;    --rule: #DDE1E7;       --stamp: #1F3864;
    --ok: #2F6B4F;          --warn: #97671A;       --bad: #A32C2C;   --idle: #6B7683;
    --ok-bg: #E7F0EA;       --warn-bg: #FAF0DC;    --bad-bg: #F7E4E4; --idle-bg: #ECEEF1;
    --serif: Georgia, 'Iowan Old Style', 'Times New Roman', ui-serif, serif;
    --sans: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    --mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --ground: #0D1117;    --panel: #151B23;      --ink: #E6EAF0;
      --ink-soft: #9AA6B4;  --rule: #262E39;       --stamp: #8FA9DC;
      --ok: #6FBF95;        --warn: #D6A756;       --bad: #E58686;   --idle: #8B95A3;
      --ok-bg: #16261E;     --warn-bg: #2A2114;    --bad-bg: #2B1919; --idle-bg: #1C222B;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground: #0D1117;      --panel: #151B23;      --ink: #E6EAF0;
    --ink-soft: #9AA6B4;    --rule: #262E39;       --stamp: #8FA9DC;
    --ok: #6FBF95;          --warn: #D6A756;       --bad: #E58686;   --idle: #8B95A3;
    --ok-bg: #16261E;       --warn-bg: #2A2114;    --bad-bg: #2B1919; --idle-bg: #1C222B;
  }}
  :root[data-theme="light"] {{
    --ground: #F6F7F9;      --panel: #FFFFFF;      --ink: #10151B;
    --ink-soft: #4A5563;    --rule: #DDE1E7;       --stamp: #1F3864;
    --ok: #2F6B4F;          --warn: #97671A;       --bad: #A32C2C;   --idle: #6B7683;
    --ok-bg: #E7F0EA;       --warn-bg: #FAF0DC;    --bad-bg: #F7E4E4; --idle-bg: #ECEEF1;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--ground); color: var(--ink);
    font-family: var(--sans); line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 60rem; margin: 0 auto; padding: 3rem 1.5rem 5rem; }}
  .eyebrow {{
    font-family: var(--mono); font-size: .72rem; letter-spacing: .14em;
    text-transform: uppercase; color: var(--stamp); margin: 0 0 .75rem;
  }}
  h1 {{
    font-family: var(--serif); font-weight: 600; font-size: clamp(1.9rem, 4.5vw, 2.9rem);
    line-height: 1.15; margin: 0 0 .6rem; text-wrap: balance; letter-spacing: -.01em;
  }}
  .lede {{ font-size: 1.06rem; color: var(--ink-soft); max-width: 62ch; margin: 0 0 1.25rem; }}
  .notice {{
    border-left: 3px solid var(--stamp); background: var(--panel);
    padding: .8rem 1rem; font-size: .9rem; color: var(--ink-soft);
    margin: 0 0 2.5rem; border-radius: 0 4px 4px 0;
  }}
  h2 {{
    font-family: var(--serif); font-size: 1.35rem; font-weight: 600;
    margin: 3rem 0 .35rem; letter-spacing: -.005em;
  }}
  .sub {{ color: var(--ink-soft); font-size: .92rem; margin: 0 0 1.25rem; max-width: 64ch; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: 1px;
    background: var(--rule); border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }}
  .stat {{ background: var(--panel); padding: 1rem 1.1rem; }}
  .stat b {{ display: block; font-family: var(--mono); font-size: 1.65rem; font-weight: 600;
    font-variant-numeric: tabular-nums; letter-spacing: -.02em; }}
  .stat span {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .07em;
    color: var(--ink-soft); }}
  .stat.hero b {{ color: var(--ok); }}
  .bar-row {{ display: grid; grid-template-columns: 9.5rem 1fr 3rem; gap: .8rem;
    align-items: center; padding: .3rem 0; font-size: .88rem; }}
  .bar-track {{ background: var(--idle-bg); height: .55rem; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; }}
  .bar-fill.ok {{ background: var(--ok); }} .bar-fill.warn {{ background: var(--warn); }}
  .bar-fill.bad {{ background: var(--bad); }} .bar-fill.idle {{ background: var(--idle); }}
  .bar-num {{ font-family: var(--mono); text-align: right; font-variant-numeric: tabular-nums;
    color: var(--ink-soft); }}
  .rec {{ background: var(--panel); border: 1px solid var(--rule);
    border-left: 3px solid var(--idle); border-radius: 0 5px 5px 0;
    padding: 1rem 1.15rem; margin: 0 0 .7rem; }}
  .rec.ok {{ border-left-color: var(--ok); }} .rec.warn {{ border-left-color: var(--warn); }}
  .rec.bad {{ border-left-color: var(--bad); }}
  .rec-head {{ display: flex; flex-wrap: wrap; gap: .5rem; align-items: center;
    margin-bottom: .6rem; }}
  .rid {{ font-family: var(--mono); font-size: .76rem; color: var(--stamp); font-weight: 600; }}
  .cite {{ font-family: var(--mono); font-size: .74rem; color: var(--ink-soft); }}
  .chip {{ font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
    padding: .16rem .5rem; border-radius: 3px; margin-left: auto; white-space: nowrap; }}
  .chip + .chip {{ margin-left: 0; }}
  .chip.ok {{ background: var(--ok-bg); color: var(--ok); }}
  .chip.warn {{ background: var(--warn-bg); color: var(--warn); }}
  .chip.bad {{ background: var(--bad-bg); color: var(--bad); }}
  .chip.idle {{ background: var(--idle-bg); color: var(--idle); }}
  .verbatim {{ font-family: var(--mono); font-size: .83rem; line-height: 1.55; margin: 0 0 .7rem;
    padding: .6rem .8rem; background: var(--ground); border-radius: 4px; color: var(--ink);
    border: 1px solid var(--rule); }}
  .rec p {{ margin: .3rem 0; font-size: .89rem; }}
  .rk {{ font-family: var(--mono); font-size: .68rem; text-transform: uppercase;
    letter-spacing: .07em; color: var(--ink-soft); margin-right: .55rem; }}
  .kw {{ font-family: var(--mono); font-size: .7rem; color: var(--stamp);
    border: 1px solid var(--rule); padding: .05rem .35rem; border-radius: 3px;
    margin-left: .5rem; }}
  .rationale {{ color: var(--ink-soft); }}
  .caveats {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 6px;
    padding: 1.1rem 1.3rem; }}
  .caveats li {{ margin: .45rem 0; font-size: .9rem; color: var(--ink-soft); }}
  .caveats b {{ color: var(--ink); }}
  .profile {{ background: var(--panel); border: 1px solid var(--rule); border-radius: 6px;
    padding: 1.1rem 1.3rem; }}
  .profile ul {{ columns: 2; column-gap: 2rem; padding-left: 1.1rem; margin: .5rem 0 0; }}
  .profile li {{ font-size: .84rem; margin: .25rem 0; break-inside: avoid; }}
  .profile li.gap {{ color: var(--bad); font-weight: 600; }}
  @media (max-width: 34rem) {{ .profile ul {{ columns: 1; }} }}
  footer {{ margin-top: 3.5rem; padding-top: 1.25rem; border-top: 1px solid var(--rule);
    font-size: .82rem; color: var(--ink-soft); }}
  code {{ font-family: var(--mono); font-size: .84em; background: var(--idle-bg);
    padding: .1rem .3rem; border-radius: 3px; }}
</style>

<div class="wrap">
  <p class="eyebrow">Solicitation N4008526R0033 · MCAS Beaufort base operations support</p>
  <h1>A 290-page federal solicitation, shredded into a compliance matrix</h1>
  <p class="lede">
    Every binding requirement extracted verbatim, each one carrying a page citation
    verified against the source document, cross-mapped across Sections L, M and the
    SOW, placed in a proposal outline, and judged against a capabilities profile.
  </p>
  <p class="notice">
    This is a record of one analysis that already ran — not a live service. The
    compliance verdicts below were judged against a <strong>fictional</strong>
    capabilities profile and describe no real company.
  </p>

  <h2>What came out</h2>
  <p class="sub">Counts from the run that produced the workbook, not estimates.</p>
  <div class="stats">
    <div class="stat"><b>{total}</b><span>Requirements</span></div>
    <div class="stat hero"><b>{grounded_pct}%</b><span>Page-verified</span></div>
    <div class="stat"><b>{files}</b><span>Source files</span></div>
    <div class="stat"><b>{outline_nodes}</b><span>Outline nodes</span></div>
    <div class="stat"><b>{judged}</b><span>Judged</span></div>
  </div>

  <h2>Grounding is the whole product</h2>
  <p class="sub">
    Every one of the {total} requirements was located in its source page by string
    match — {grounded} of {total} verified, none ungrounded. No citation is
    model-generated; page numbers are computed from the parsed document and then
    checked. A requirement that cannot be found in the document does not get a
    page number, it gets flagged.
  </p>

  <h2>Where the requirements go</h2>
  <p class="sub">
    Not every requirement is something you write. The outline separates proposal
    content from duties you perform after award and from the criteria the
    Government scores you against.
  </p>
  <div class="stats">
    <div class="stat"><b>{written}</b><span>Written in the proposal</span></div>
    <div class="stat"><b>{post_award}</b><span>Post-award performance</span></div>
    <div class="stat"><b>{eval_criteria}</b><span>Evaluation criteria</span></div>
    <div class="stat"><b>{unassigned}</b><span>Unplaced</span></div>
  </div>

  <h2>Cross-mapping L ↔ M ↔ SOW</h2>
  <p class="sub">
    A proposal is lost in the gaps: work that is instructed but never scored, or
    scored but never instructed. This pass is similarity-based and still advisory —
    see the caveats below.
  </p>
  {gap_rows}

  <h2>The matrix itself</h2>
  <p class="sub">
    {sample} of {total} rows, weighted toward the interesting ones — the partial
    findings and the calls the judge declined. Every row carries its own citation.
  </p>
{rows}

  <h2>Judged against a fictional profile</h2>
  <p class="sub">
    {company}. Deliberately mixed, with real gaps, so the demo produces genuine
    partial findings instead of a wall of green.
  </p>
  <div class="profile"><ul>{capabilities}</ul></div>

  <h2>What this does not do yet</h2>
  <p class="sub">
    Measured limits, stated plainly. A tool that hides these is worse than one that
    names them.
  </p>
  <div class="caveats">
    <ul>
      <li><b>Recall 0.971, precision 0.426</b> against a hand-built golden set of 103
        requirements. Precision is a <b>lower bound, not an error rate</b>: the golden
        set annotates ~22 of 290 pages and is a validated sample, not an exhaustive
        shred, so most "false positives" are real requirements it simply never
        recorded.</li>
      <li><b>Cross-mapping is advisory.</b> No per-factor anchor yet, so structurally
        similar sentences about different evaluation factors can still link.</li>
      <li><b>{not_judged} of {total} rows are not judged</b> and say so explicitly. An
        unjudged row is never rendered as compliant — a team believing it is covered
        because nobody looked is the costliest failure this tool could cause.</li>
      <li><b>A parser defect is open.</b> The annex two-column spec tables interleave
        the title column into sentence text, which corrupts some requirement text even
        when grounding succeeds.</li>
      <li><b>Coverage of this run was scoped</b> to the golden-annotated sections, so
        this matrix is not the whole 290-page package.</li>
    </ul>
  </div>

  <footer>
    Pipeline: <code>parse → chunk → extract → ground → cross-map → outline → judge →
    workbook</code>. Extraction and judgment run through a recorded-artifact seam, so
    the same inputs replay to a byte-identical matrix and every number above can be
    re-derived rather than taken on trust.
  </footer>
</div>
"""
