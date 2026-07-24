"""Command-line interface for rfp-analyzer.

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
import sys
from pathlib import Path

from rfp_analyzer.pipeline.models import DocumentMap, PageInfo, ParsedFile, SectionNode
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
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
