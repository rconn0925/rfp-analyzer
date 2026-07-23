"""Command-line interface for rfp-analyzer.

Phase 1 stub: the ``parse`` subcommand is wired but not yet implemented.
Plan 01-06 replaces the body with the real pipeline invocation.
"""

import argparse
import sys


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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(2)
    print("not yet implemented")
    sys.exit(2)
