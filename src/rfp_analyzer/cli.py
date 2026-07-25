"""Command-line interface for rfp-analyzer.

The whole pipeline in one command:

    rfp-analyzer run <package-dir>                        # parse + emit chunks
    (Claude Code reads chunks.jsonl -> drafts.jsonl)
    rfp-analyzer run <package-dir> --drafts drafts.jsonl  # ...through to the workbook

The Claude Code handoff cannot be automated away — the engine is a personal
subscription, not an API — so a first run stops after writing chunks.jsonl and
prints exactly what to do next. Once the recordings exist the same command runs
end to end. The individual stages (`parse`, `chunks`, `extract`, `judgments`,
`analyze`) remain available for working on one step at a time.

``rfp-analyzer parse <package-dir> --out <artifacts-dir>`` (D-06) runs the
full Phase 1 pipeline and emits both D-05 artifacts every run:

1. Canonical ``document_map.json`` (the versioned Phase 2 contract) written
   to ``<out>/<package-name>/document_map.json``.
2. A human-readable section-tree report to stdout — classification with
   evidence, per-file roles, section hierarchy with locator ranges, quality
   flags as contiguous-range notes (D-03), warnings, and a metrics footer
   proving the D-09 zero-LLM-cost plumbing.

Report rendering lives here on purpose: presentation is not library code.
The only import direction allowed is CLI -> pipeline, never the reverse.

Exit codes: 0 success; 1 honest failure (classification ``unknown`` AND
zero sections detected anywhere — machine-checkable "we got nothing");
2 usage errors.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from rfp_analyzer.analysis_report import render_matrix_report
from rfp_analyzer.eval.scoring import format_score_line, score
from rfp_analyzer.pipeline.analysis.export import write_csv, write_workbook
from rfp_analyzer.pipeline.analysis.judge import (
    DEMO_PROFILE,
    CorruptVerdictsError,
    judgment_tasks,
    load_verdicts,
)
from rfp_analyzer.pipeline.analysis.run_analysis import run_analysis
from rfp_analyzer.pipeline.extraction.chunker import chunk_key, iter_chunks
from rfp_analyzer.pipeline.extraction.replay import (
    CorruptDraftsError,
    load_drafts,
    replay_extract_fn,
)
from rfp_analyzer.pipeline.extraction.run_extraction import DEFAULT_MODEL, run_extraction
from rfp_analyzer.pipeline.models import (
    CapabilityProfile,
    DocumentMap,
    PageInfo,
    ParsedFile,
    RequirementSet,
    SectionNode,
)
from rfp_analyzer.pipeline.run import run_pipeline

QUALITY_NOTES: dict[str, str] = {
    "scanned": "scanned image, no text layer",
    "empty": "empty page, no extractable text",
    "low_text": "very little text (partial scan or stamped page)",
    "gibberish": "gibberish text layer (broken font encoding)",
}
"""D-03 surfaced-note phrasing per non-ok page quality status."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rfp-analyzer",
        description="Parse a federal RFP package into a structured document map.",
    )
    subparsers = parser.add_subparsers(dest="command")

    parse_cmd = subparsers.add_parser(
        "parse",
        help="Parse a package directory of RFP files (PDF/DOCX) into artifacts.",
    )
    parse_cmd.add_argument(
        "package_dir",
        help="Directory containing the RFP package files (PDF/DOCX).",
    )
    parse_cmd.add_argument(
        "--out",
        default="artifacts",
        help="Output directory for artifacts (default: artifacts).",
    )

    chunks_cmd = subparsers.add_parser(
        "chunks",
        help="Export extraction chunks as JSONL for Claude Code to extract from.",
    )
    chunks_cmd.add_argument(
        "artifacts_dir",
        help="Directory containing a document_map.json produced by `parse`.",
    )
    chunks_cmd.add_argument(
        "--out",
        default=None,
        help="Path for chunks.jsonl (default: alongside document_map.json).",
    )

    extract_cmd = subparsers.add_parser(
        "extract",
        help="Ground recorded requirement drafts into a requirements.json matrix.",
    )
    extract_cmd.add_argument(
        "artifacts_dir",
        help="Directory containing a document_map.json produced by `parse`.",
    )
    extract_cmd.add_argument(
        "--drafts",
        required=True,
        help=(
            "Path to drafts.jsonl recorded by Claude Code from `chunks` output. "
            "Required — there is no in-process extraction engine."
        ),
    )
    extract_cmd.add_argument(
        "--golden",
        default=None,
        help="Golden-set JSON to score this run against (precision/recall/F1).",
    )
    extract_cmd.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Provenance label recorded on the run (default: {DEFAULT_MODEL}).",
    )
    extract_cmd.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Run provenance seed recorded with the run (default: 7).",
    )
    extract_cmd.add_argument(
        "--out",
        default=None,
        help="Directory for requirements.json (default: alongside document_map.json).",
    )

    judgments_cmd = subparsers.add_parser(
        "judgments",
        help="Export the compliance-judging worklist for Claude Code.",
    )
    judgments_cmd.add_argument(
        "artifacts_dir",
        help="Directory containing requirements.json produced by `extract`.",
    )
    judgments_cmd.add_argument(
        "--out",
        default=None,
        help="Path for judgments.jsonl (default: alongside requirements.json).",
    )

    analyze_cmd = subparsers.add_parser(
        "analyze",
        help="Turn requirements.json into a compliance matrix workbook (xlsx + csv).",
    )
    analyze_cmd.add_argument(
        "artifacts_dir",
        help="Directory containing document_map.json and requirements.json.",
    )
    analyze_cmd.add_argument(
        "--verdicts",
        default=None,
        help=(
            "Path to verdicts.jsonl recorded by Claude Code. Optional — without it "
            "the matrix reports every row as NOT JUDGED rather than implying compliance."
        ),
    )
    analyze_cmd.add_argument(
        "--out",
        default=None,
        help="Directory for matrix.json / matrix.xlsx / matrix.csv (default: artifacts_dir).",
    )
    analyze_cmd.add_argument(
        "--profile",
        default=None,
        help="Capabilities profile JSON to judge against (default: the fictional demo profile).",
    )

    run_cmd = subparsers.add_parser(
        "run",
        help="One command: package directory -> compliance workbook.",
    )
    run_cmd.add_argument("package_dir", help="Directory containing the RFP package files.")
    run_cmd.add_argument(
        "--drafts",
        default=None,
        help=(
            "drafts.jsonl recorded by Claude Code. Omit on a first run: the pipeline "
            "parses, writes chunks.jsonl, and stops with the handoff instructions."
        ),
    )
    run_cmd.add_argument(
        "--verdicts", default=None, help="verdicts.jsonl recorded by Claude Code (optional)."
    )
    run_cmd.add_argument(
        "--profile", default=None, help="Capabilities profile JSON (default: demo profile)."
    )
    run_cmd.add_argument(
        "--out", default="artifacts", help="Artifacts root (default: artifacts)."
    )
    return parser


def _span_text(node: SectionNode) -> str:
    locator = node.locator
    if locator.kind == "pages":
        return f"pages {locator.page_start}-{locator.page_end}"
    return f"blocks {locator.block_start}-{locator.block_end}"


def _node_display(node: SectionNode) -> str:
    label = node.label
    if len(label) == 1 and "A" <= label <= "M" and node.detection == "heading":
        label = f"SECTION {label}"
    title = node.title.strip()
    return f"{label} — {title}" if title else label


def _render_section(node: SectionNode, depth: int, lines: list[str]) -> None:
    indent = "  " * (depth + 2)
    lines.append(f"{indent}{_node_display(node)}  {_span_text(node)}")
    for child in node.children:
        _render_section(child, depth + 1, lines)


def _quality_ranges(pages: list[PageInfo]) -> list[tuple[int, int, str]]:
    """Contiguous (start, end, status) ranges of non-ok pages, in page order."""
    ranges: list[tuple[int, int, str]] = []
    for page in sorted(pages, key=lambda p: p.page_number):
        if page.quality == "ok":
            continue
        if ranges and ranges[-1][2] == page.quality and ranges[-1][1] == page.page_number - 1:
            ranges[-1] = (ranges[-1][0], page.page_number, page.quality)
        else:
            ranges.append((page.page_number, page.page_number, page.quality))
    return ranges


def _role_text(file: ParsedFile) -> str:
    if file.doc_role != "amendment":
        return file.doc_role
    parts = ["amendment"]
    if file.amendment_number:
        parts.append(file.amendment_number)
    if file.amendment_evidence == "filename":
        parts.append("(unverified — scanned, matched by filename)")
    return " ".join(parts)


def render_report(document_map: DocumentMap) -> str:
    """The D-05 human-readable section-tree report for one pipeline run."""
    lines: list[str] = []
    lines.append(f"Package: {document_map.package_name}")
    lines.append(f"Classification: {document_map.classification}")
    for reason in document_map.classification_evidence:
        lines.append(f"  evidence: {reason}")
    lines.append("")

    lines.append(f"Files ({len(document_map.files)}):")
    for file in document_map.files:
        lines.append(f"  {file.filename}  [{_role_text(file)}]  parse: {file.parse_status}")
        if file.error:
            lines.append(f"    error: {file.error}")
        for node in file.sections:
            _render_section(node, 0, lines)
        for start, end, status in _quality_ranges(file.pages):
            span = f"page {start}" if start == end else f"pages {start}-{end}"
            lines.append(f"    {span}: {QUALITY_NOTES.get(status, status)}")

    if document_map.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in document_map.warnings:
            lines.append(f"  - {warning}")

    metrics = document_map.metrics
    lines.append("")
    lines.append("Metrics:")
    timing = "  ".join(f"{name}: {secs:.2f}s" for name, secs in metrics.stage_timings.items())
    if timing:
        lines.append(f"  stages: {timing}")
    lines.append(
        f"  files parsed: {metrics.files_parsed}/{len(document_map.files)}"
        f"  pages parsed: {metrics.pages_parsed}"
        f"  pages flagged: {metrics.pages_flagged}"
    )
    lines.append(f"  LLM cost: ${metrics.estimated_cost_usd:.2f} ({metrics.llm_calls} calls)")
    return "\n".join(lines)


def render_requirements_report(
    requirement_set: RequirementSet, golden_path: str | None = None
) -> str:
    """Human-readable extraction report — the `extract` half of the dual output.

    Surfaces the honesty signals the matrix depends on: counts by req_type and
    by section, verified vs unverified totals (T-02-15: hallucinated rows are
    counted, never hidden), extraction coverage (T-02-20), the golden-set
    precision/recall/F1 line when one applies (success criterion 5), the
    deterministic-sweep missed-candidate list (EXTR-05), amendment change rows
    and possibly-modified base rows (INTK-03), and a metrics footer.
    """
    reqs = requirement_set.requirements
    lines: list[str] = []
    lines.append(f"Package: {requirement_set.package_name}")
    lines.append(f"Model: {requirement_set.model_name}")
    lines.append(f"Requirements: {len(reqs)}")

    verified = sum(1 for r in reqs if r.verified)
    unverified = len(reqs) - verified
    lines.append(f"  verified (grounded): {verified}  unverified (ungroundable): {unverified}")

    # T-02-20: an un-extracted chunk is a coverage hole, not "nothing here".
    metrics = requirement_set.metrics
    if metrics.chunks_total:
        extracted = metrics.chunks_total - metrics.chunks_unextracted
        lines.append(f"  chunks extracted: {extracted}/{metrics.chunks_total}")
        if metrics.chunks_unextracted:
            lines.append(
                f"  WARNING: {metrics.chunks_unextracted} chunk(s) had no recorded "
                "drafts — coverage is incomplete and recall is understated"
            )

    lines.append("")
    lines.append(_golden_line(requirement_set, golden_path))

    by_type = Counter(r.req_type for r in reqs)
    lines.append("")
    lines.append("By type:")
    for req_type, count in sorted(by_type.items()):
        lines.append(f"  {req_type}: {count}")

    by_section = Counter((r.source_ref.section_label or "(none)") for r in reqs)
    lines.append("")
    lines.append("By section:")
    for section, count in sorted(by_section.items()):
        lines.append(f"  {section}: {count}")

    # INTK-03: amendment change rows and the base rows they may modify (never merged).
    changes = [r for r in reqs if r.is_amendment_change]
    modified = [r for r in reqs if r.possibly_modified]
    lines.append("")
    lines.append(
        f"Amendment change rows: {len(changes)}  "
        f"possibly-modified base rows: {len(modified)}"
    )
    for change in changes:
        page = change.source_ref.page
        where = f"p{page}" if page is not None else "ungrounded"
        preview = _truncate(change.verbatim_text)
        lines.append(f"  change [{change.display_label} {where}]: {preview}")

    # EXTR-05: deterministic sweep hits no extraction covered.
    missed = requirement_set.missed_candidates
    lines.append("")
    lines.append(f"Missed candidates (sweep hits not extracted): {len(missed)}")
    for candidate in missed[:_MISSED_PREVIEW]:
        lines.append(
            f"  [{candidate.file_id} p{candidate.page} {candidate.binding_keyword}] "
            f"{_truncate(candidate.verbatim_sentence)}"
        )
    if len(missed) > _MISSED_PREVIEW:
        lines.append(f"  ... and {len(missed) - _MISSED_PREVIEW} more")

    metrics = requirement_set.metrics
    lines.append("")
    lines.append("Metrics:")
    timing = "  ".join(f"{name}: {secs:.2f}s" for name, secs in metrics.stage_timings.items())
    if timing:
        lines.append(f"  stages: {timing}")
    lines.append(
        f"  LLM calls: {metrics.llm_calls}"
        f"  input tokens: {metrics.input_tokens}"
        f"  output tokens: {metrics.output_tokens}"
    )
    lines.append(
        f"  LLM cost: ${metrics.estimated_cost_usd:.2f} "
        "(engine ran in a Claude Code session; not metered here)"
    )
    return "\n".join(lines)


NO_GOLDEN_LINE = "vs golden set: no golden set for this package (recall/precision not scored)"
"""Printed when nothing scores this run.

Success criterion 5 says recall and precision appear on EVERY run. When there is
no ground truth the honest report is an explicit "not scored" — silently omitting
the line would let an unmeasured run look the same as a measured one.
"""


def _golden_line(requirement_set: RequirementSet, golden_path: str | None) -> str:
    """The precision/recall/F1 line, or an explicit statement that nothing scored it."""
    if not golden_path:
        return NO_GOLDEN_LINE

    path = Path(golden_path)
    if not path.exists():
        return f"vs golden set: ERROR — golden file not found: {path}"

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        golds = doc["requirements"] if isinstance(doc, dict) else doc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return f"vs golden set: ERROR — unreadable golden file {path}: {exc}"

    result = score(requirement_set.requirements, golds)
    line = format_score_line(result)

    # Guard against scoring a run against a DIFFERENT package's ground truth,
    # which would print a confidently meaningless number. Compare file_ids, not
    # names: the golden set's "package" is a solicitation number while
    # package_name is the corpus directory, so a name comparison always
    # mismatches. A file_id is content-derived and shared by both sides.
    gold_files = {g.get("file_id") for g in golds if isinstance(g, dict)}
    run_files = {r.source_ref.file_id for r in requirement_set.requirements}
    if gold_files and run_files and not (gold_files & run_files):
        package = doc.get("package") if isinstance(doc, dict) else "unknown"
        line += f"  [WARNING: golden set ({package}) shares no source file with this run]"
    return line


def _truncate(text: str, limit: int = 120) -> str:
    """One-line preview of a verbatim span for the report."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


_MISSED_PREVIEW = 25
"""How many missed candidates to list before summarizing the remainder."""


def _resolve_document_map(artifacts_dir: Path) -> DocumentMap | None:
    """Load and validate ``<artifacts_dir>/document_map.json``, or report why not."""
    if not artifacts_dir.exists():
        print(f"error: artifacts directory does not exist: {artifacts_dir}", file=sys.stderr)
        return None
    if not artifacts_dir.is_dir():
        print(f"error: not a directory: {artifacts_dir}", file=sys.stderr)
        return None

    map_path = artifacts_dir / "document_map.json"
    if not map_path.exists():
        print(
            f"error: no document_map.json in {artifacts_dir} — run `parse` first",
            file=sys.stderr,
        )
        return None

    # T-02-14: validate the artifact before it drives extraction. A schema-version
    # mismatch is an honest, machine-readable failure, not a silent mis-parse.
    return _load_document_map(map_path.read_text(encoding="utf-8"))


def _run_chunks(args: argparse.Namespace) -> int:
    """Export every extraction chunk as JSONL — the input Claude Code extracts from.

    One line per chunk, in deterministic ``iter_chunks`` order, carrying the
    ``chunk_key`` that joins it back to the drafts recorded for it. ``page_map``
    is deliberately NOT exported: page provenance is recomputed at grounding time
    from the document map, never round-tripped through the engine, so a page
    reference can't be influenced by what the engine returns.
    """
    artifacts_dir = Path(args.artifacts_dir)
    document_map = _resolve_document_map(artifacts_dir)
    if document_map is None:
        return 2

    out_path = Path(args.out) if args.out is not None else artifacts_dir / "chunks.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in iter_chunks(document_map):
            record = {
                "chunk_key": chunk_key(chunk.text),
                "file_id": chunk.file_id,
                "filename": chunk.filename,
                "section_label": chunk.section_label,
                "role": chunk.role,
                "doc_role": chunk.doc_role,
                "text": chunk.text,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    print(f"Package: {document_map.package_name}")
    print(f"Chunks written: {count} -> {out_path}")
    print(
        "\nNext: have Claude Code extract each chunk into drafts.jsonl "
        '({"chunk_key": ..., "requirements": [...]}), then run:\n'
        f"  rfp-analyzer extract {artifacts_dir} --drafts drafts.jsonl"
    )
    return 0


def _run_extract(args: argparse.Namespace) -> int:
    artifacts_dir = Path(args.artifacts_dir)
    document_map = _resolve_document_map(artifacts_dir)
    if document_map is None:
        return 2

    try:
        drafts = load_drafts(args.drafts)
    except CorruptDraftsError as exc:
        # A bad recording fails the run rather than silently under-reporting.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    engine = replay_extract_fn(drafts)
    requirement_set = run_extraction(
        document_map, model=args.model, seed=args.seed, extract_fn=engine
    )

    out_dir = Path(args.out) if args.out is not None else artifacts_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    requirements_path = out_dir / "requirements.json"
    requirements_path.write_text(requirement_set.model_dump_json(indent=2), encoding="utf-8")

    print(render_requirements_report(requirement_set, golden_path=args.golden))
    if engine.unused_count:
        print(
            f"\nnote: {engine.unused_count} recorded chunk(s) went unused — "
            "the drafts file may be stale relative to the current document map"
        )
    print(f"\nRequirements written to {requirements_path}")
    return 0


def _load_requirement_set(artifacts_dir: Path) -> RequirementSet | None:
    """Load requirements.json from an artifacts directory, or report why not."""
    path = artifacts_dir / "requirements.json"
    if not path.exists():
        print(
            f"error: no requirements.json in {artifacts_dir} — run `extract` first",
            file=sys.stderr,
        )
        return None
    try:
        return RequirementSet.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"error: requirements.json failed schema validation: {exc}", file=sys.stderr)
        return None


def _run_judgments(args: argparse.Namespace) -> int:
    """Export the judging worklist — step one of the compliance-judgment handoff."""
    artifacts_dir = Path(args.artifacts_dir)
    requirement_set = _load_requirement_set(artifacts_dir)
    if requirement_set is None:
        return 2

    tasks = judgment_tasks(requirement_set.requirements, DEMO_PROFILE)
    out_path = Path(args.out) if args.out is not None else artifacts_dir / "judgments.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        profile_line = json.dumps({"profile": DEMO_PROFILE.model_dump()}, ensure_ascii=False)
        handle.write(profile_line + "\n")
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    print(f"Package: {requirement_set.package_name}")
    print(f"Judging tasks written: {len(tasks)} -> {out_path}")
    print(f"Profile: {DEMO_PROFILE.company_name}")
    print(
        "\nNext: have Claude Code judge each requirement into verdicts.jsonl "
        '({"requirement_id", "verdict", "rationale", "confidence"} per line), then:\n'
        f"  rfp-analyzer analyze {artifacts_dir} --verdicts verdicts.jsonl"
    )
    return 0


def _load_profile(path: str | None) -> CapabilityProfile | None:
    """Load a capabilities profile, or return the demo profile when none is given.

    Returns ``None`` only on an unreadable file, so a typo in ``--profile`` fails
    the run rather than silently judging against the fictional demo profile and
    exporting verdicts that look real.
    """
    if not path:
        return DEMO_PROFILE
    try:
        return CapabilityProfile.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        print(f"error: could not read capabilities profile {path}: {exc}", file=sys.stderr)
        return None


def _run_analyze(args: argparse.Namespace) -> int:
    """Build the compliance matrix and write the workbook + CSV."""
    artifacts_dir = Path(args.artifacts_dir)
    document_map = _resolve_document_map(artifacts_dir)
    if document_map is None:
        return 2
    requirement_set = _load_requirement_set(artifacts_dir)
    if requirement_set is None:
        return 2

    profile = _load_profile(getattr(args, "profile", None))
    if profile is None:
        return 2

    verdicts = None
    if args.verdicts:
        try:
            verdicts = load_verdicts(args.verdicts)
        except CorruptVerdictsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    matrix = run_analysis(document_map, requirement_set, profile=profile, verdicts=verdicts)

    out_dir = Path(args.out) if args.out is not None else artifacts_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "matrix.json").write_text(matrix.model_dump_json(indent=2), encoding="utf-8")
    xlsx_path = write_workbook(matrix, out_dir / "matrix.xlsx")
    csv_path = write_csv(matrix, out_dir / "matrix.csv")

    print(render_matrix_report(matrix))
    print(f"\nWorkbook written to {xlsx_path}")
    print(f"CSV written to {csv_path}")
    return 0


def _run_all(args: argparse.Namespace) -> int:
    """Package directory -> compliance workbook in one command.

    Chains parse -> chunks -> extract -> analyze. The Claude Code handoffs cannot
    be automated away (the engine is a subscription, not an API), so a first run
    stops after writing chunks.jsonl and prints exactly what to do next. Once the
    recordings exist, the same command runs the whole thing.
    """
    package_dir = Path(args.package_dir)
    if not package_dir.is_dir():
        print(f"error: not a directory: {package_dir}", file=sys.stderr)
        return 2

    package_name = package_dir.resolve().name or "package"
    artifacts_dir = Path(args.out) / package_name

    print(f"[1/4] parsing {package_dir} ...")
    parse_args = argparse.Namespace(package_dir=str(package_dir), out=args.out)
    if _run_parse_quiet(parse_args) != 0:
        return 1

    print(f"[2/4] exporting chunks -> {artifacts_dir / 'chunks.jsonl'}")
    chunks_args = argparse.Namespace(artifacts_dir=str(artifacts_dir), out=None)
    if _run_chunks_quiet(chunks_args) != 0:
        return 2

    if not args.drafts:
        print(
            "\nStopping here: extraction needs Claude Code.\n"
            f"  1. Have Claude Code read {artifacts_dir / 'chunks.jsonl'} and write drafts.jsonl\n"
            f"  2. Re-run: rfp-analyzer run {package_dir} --drafts drafts.jsonl"
        )
        return 0

    print(f"[3/4] extracting with recorded drafts ({args.drafts}) ...")
    extract_args = argparse.Namespace(
        artifacts_dir=str(artifacts_dir), drafts=args.drafts, golden=None,
        model=DEFAULT_MODEL, seed=7, out=None,
    )
    if _run_extract(extract_args) != 0:
        return 2

    print("\n[4/4] analyzing -> compliance workbook ...")
    analyze_args = argparse.Namespace(
        artifacts_dir=str(artifacts_dir), verdicts=args.verdicts,
        profile=args.profile, out=None,
    )
    return _run_analyze(analyze_args)


def _run_parse_quiet(args: argparse.Namespace) -> int:
    """`parse` without the full section-tree report — `run` prints its own progress."""
    package_dir = Path(args.package_dir)
    document_map = run_pipeline(package_dir)
    package_name = package_dir.resolve().name or "package"
    out_dir = Path(args.out) / package_name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "document_map.json").write_text(
        document_map.model_dump_json(indent=2), encoding="utf-8"
    )
    files_ok = sum(1 for f in document_map.files if f.parse_status == "ok")
    print(
        f"      {files_ok}/{len(document_map.files)} files parsed, "
        f"classification={document_map.classification}"
    )
    total_sections = sum(len(f.sections) for f in document_map.files)
    if document_map.classification == "unknown" and total_sections == 0:
        print("error: nothing structural detected in this package", file=sys.stderr)
        return 1
    return 0


def _run_chunks_quiet(args: argparse.Namespace) -> int:
    """`chunks` without the next-step banner — `run` sequences the steps itself."""
    artifacts_dir = Path(args.artifacts_dir)
    document_map = _resolve_document_map(artifacts_dir)
    if document_map is None:
        return 2
    out_path = artifacts_dir / "chunks.jsonl"
    count = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in iter_chunks(document_map):
            handle.write(json.dumps({
                "chunk_key": chunk_key(chunk.text),
                "file_id": chunk.file_id,
                "filename": chunk.filename,
                "section_label": chunk.section_label,
                "role": chunk.role,
                "doc_role": chunk.doc_role,
                "text": chunk.text,
            }, ensure_ascii=False) + "\n")
            count += 1
    print(f"      {count} chunks")
    return 0


def _load_document_map(raw: str) -> DocumentMap | None:
    """Validate raw document_map.json text; return None (after an error) if unusable.

    Rejects an incompatible major ``schema_version`` before Pydantic validation
    so an evolved contract fails with a clear message instead of a field error.
    """
    expected_major = DocumentMap().schema_version.split(".", 1)[0]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: document_map.json is not valid JSON: {exc}", file=sys.stderr)
        return None
    found_version = str(payload.get("schema_version", ""))
    found_major = found_version.split(".", 1)[0]
    if found_major != expected_major:
        print(
            f"error: incompatible document_map schema_version {found_version!r} "
            f"(this build reads {expected_major}.x) — re-run `parse`",
            file=sys.stderr,
        )
        return None
    try:
        return DocumentMap.model_validate_json(raw)
    except ValueError as exc:
        print(f"error: document_map.json failed schema validation: {exc}", file=sys.stderr)
        return None


def _run_parse(args: argparse.Namespace) -> int:
    package_dir = Path(args.package_dir)
    if not package_dir.exists():
        print(f"error: package directory does not exist: {package_dir}", file=sys.stderr)
        return 2
    if not package_dir.is_dir():
        print(f"error: not a directory: {package_dir}", file=sys.stderr)
        return 2

    document_map = run_pipeline(package_dir)

    # T-01-16: the output path derives ONLY from the package dir's own name —
    # never from file-derived names inside the package.
    package_name = package_dir.resolve().name or "package"
    out_dir = Path(args.out) / package_name
    out_dir.mkdir(parents=True, exist_ok=True)
    map_path = out_dir / "document_map.json"
    map_path.write_text(document_map.model_dump_json(indent=2), encoding="utf-8")

    print(render_report(document_map))
    print(f"\nDocument map written to {map_path}")

    total_sections = sum(len(file.sections) for file in document_map.files)
    if document_map.classification == "unknown" and total_sections == 0:
        return 1
    return 0


def main() -> None:
    # Windows consoles may use a legacy codepage; never crash the report on
    # an unencodable character (em-dashes, odd filename glyphs).
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")

    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(2)
    if args.command == "parse":
        sys.exit(_run_parse(args))
    if args.command == "chunks":
        sys.exit(_run_chunks(args))
    if args.command == "extract":
        sys.exit(_run_extract(args))
    if args.command == "judgments":
        sys.exit(_run_judgments(args))
    if args.command == "analyze":
        sys.exit(_run_analyze(args))
    if args.command == "run":
        sys.exit(_run_all(args))
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
