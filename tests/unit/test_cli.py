"""Unit tests for the CLI harness (W2 — the phase's headline deliverable had
zero automated coverage).

Everything here is synthetic: report rendering asserts against a hand-built
DocumentMap, and the exit-code / artifact paths drive ``_run_parse`` over tiny
PDFs written by the ``make_minimal_pdf`` fixture (tests/unit/conftest.py). No
corpus binaries are touched, so these pass in CI where the corpus is absent.
"""

import argparse
import json

from rfp_analyzer.cli import (
    _run_parse,
    build_parser,
    main,
    render_report,
)
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import (
    DocumentMap,
    PageInfo,
    PageSpan,
    ParsedFile,
    SectionNode,
)

# --- synthetic DocumentMap for render_report ---------------------------------


def _synthetic_map() -> DocumentMap:
    """A DocumentMap exercising a page-range locator, a flagged-page range, an
    amendment role, warnings, and the zeroed metrics footer."""
    solicitation = ParsedFile(
        file_id="aaaaaaaaaaaa-solicitation",
        filename="Solicitation.pdf",
        sha256="0" * 64,
        file_type="pdf",
        parse_status="ok",
        doc_role="base_solicitation",
        page_count=70,
        pages=[
            PageInfo(page_number=1, quality="ok", char_count=100, text="cover"),
            PageInfo(page_number=2, quality="scanned", char_count=0, text=""),
            PageInfo(page_number=3, quality="scanned", char_count=0, text=""),
            PageInfo(page_number=4, quality="ok", char_count=100, text="body"),
        ],
        sections=[
            SectionNode(
                label="L",
                title="INSTRUCTIONS, CONDITIONS, AND NOTICES TO OFFERORS",
                role="instructions",
                locator=PageSpan(page_start=49, page_end=57),
                detection="heading",
            ),
            SectionNode(
                label="M",
                title="EVALUATION FACTORS FOR AWARD",
                role="evaluation",
                locator=PageSpan(page_start=58, page_end=70),
                detection="heading",
            ),
        ],
    )
    amendment = ParsedFile(
        file_id="bbbbbbbbbbbb-amendment",
        filename="Amendment SF30.pdf",
        sha256="1" * 64,
        file_type="pdf",
        parse_status="ok",
        doc_role="amendment",
        amendment_number="0001",
        amendment_evidence="filename",
        page_count=5,
        pages=[PageInfo(page_number=1, quality="ok", char_count=50, text="amd")],
    )
    return DocumentMap(
        package_name="primary-ucf",
        classification="partial_ucf",
        classification_evidence=["SF1449 title matched on Solicitation.pdf page 1"],
        warnings=["Commercial-form signal found alongside detected UCF sections."],
        files=[solicitation, amendment],
        metrics=RunMetrics(
            stage_timings={"parse": 15.35, "quality": 0.06},
            files_parsed=2,
            pages_parsed=5,
            pages_flagged=2,
        ),
    )


class TestBuildParser:
    def test_parse_subcommand_defaults_out_to_artifacts(self):
        parser = build_parser()
        args = parser.parse_args(["parse", "some/dir"])
        assert args.command == "parse"
        assert args.package_dir == "some/dir"
        assert args.out == "artifacts"

    def test_parse_subcommand_accepts_out_flag(self):
        parser = build_parser()
        args = parser.parse_args(["parse", "some/dir", "--out", "build/x"])
        assert args.out == "build/x"

    def test_no_command_leaves_command_none(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None


class TestRenderReport:
    def test_report_carries_all_load_bearing_lines(self):
        report = render_report(_synthetic_map())

        # Classification line + evidence.
        assert "Classification: partial_ucf" in report
        assert "evidence: SF1449 title matched on Solicitation.pdf page 1" in report

        # A page-range locator for a detected section.
        assert "SECTION L" in report
        assert "pages 49-57" in report
        assert "pages 58-70" in report

        # Contiguous quality range note (pages 2-3 scanned collapse into one).
        assert "pages 2-3: scanned image, no text layer" in report

        # Amendment role rendered with the unverified-filename qualifier.
        assert "amendment" in report
        assert "unverified" in report

        # Warning surfaced.
        assert "Warnings:" in report
        assert "Commercial-form signal" in report

        # Zeroed metrics footer (D-09 plumbing).
        assert "LLM cost: $0.00 (0 calls)" in report
        assert "files parsed: 2/2" in report

    def test_single_flagged_page_renders_as_page_not_range(self):
        dmap = _synthetic_map()
        dmap.files[0].pages = [
            PageInfo(page_number=1, quality="ok", char_count=10, text="x"),
            PageInfo(page_number=2, quality="gibberish", char_count=0, text=""),
            PageInfo(page_number=3, quality="ok", char_count=10, text="y"),
        ]
        report = render_report(dmap)
        assert "page 2: gibberish text layer (broken font encoding)" in report


def _unknown_empty_map() -> DocumentMap:
    """classification == unknown AND zero sections anywhere — the exit-1 case."""
    return DocumentMap(
        package_name="empty",
        classification="unknown",
        classification_evidence=["No UCF section headings and no recognized form pages found"],
        warnings=["Package structure unrecognized."],
        files=[
            ParsedFile(
                file_id="cccccccccccc-body",
                filename="body.pdf",
                sha256="2" * 64,
                file_type="pdf",
                parse_status="ok",
                doc_role="attachment",
                page_count=1,
                pages=[PageInfo(page_number=1, quality="ok", char_count=40, text="body")],
            )
        ],
    )


class TestRunParseExitCodes:
    """The exit-code POLICY lives in _run_parse. run_pipeline is stubbed so the
    policy is tested in isolation from parsing/quality internals (the exit-2
    dir guards run before run_pipeline is ever called)."""

    def test_exit_0_when_not_unknown_or_sections_present(self, tmp_path, monkeypatch):
        pkg = tmp_path / "good-pkg"
        pkg.mkdir()
        monkeypatch.setattr("rfp_analyzer.cli.run_pipeline", lambda _dir: _synthetic_map())
        args = argparse.Namespace(package_dir=str(pkg), out=str(tmp_path / "artifacts"))
        assert _run_parse(args) == 0

    def test_exit_1_on_unknown_classification_with_zero_sections(self, tmp_path, monkeypatch):
        pkg = tmp_path / "empty-structure-pkg"
        pkg.mkdir()
        monkeypatch.setattr("rfp_analyzer.cli.run_pipeline", lambda _dir: _unknown_empty_map())
        args = argparse.Namespace(package_dir=str(pkg), out=str(tmp_path / "artifacts"))
        assert _run_parse(args) == 1

    def test_exit_0_when_unknown_but_some_section_detected(self, tmp_path, monkeypatch):
        # Only unknown AND zero sections is an honest failure; unknown WITH a
        # detected section is still exit 0.
        dmap = _unknown_empty_map()
        dmap.files[0].sections = [
            SectionNode(
                label="SOW",
                title="STATEMENT OF WORK",
                role="sow_pws",
                locator=PageSpan(page_start=1, page_end=1),
                detection="role_title",
            )
        ]
        pkg = tmp_path / "unknown-with-section"
        pkg.mkdir()
        monkeypatch.setattr("rfp_analyzer.cli.run_pipeline", lambda _dir: dmap)
        args = argparse.Namespace(package_dir=str(pkg), out=str(tmp_path / "artifacts"))
        assert _run_parse(args) == 0

    def test_exit_2_on_nonexistent_directory(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        args = argparse.Namespace(package_dir=str(missing), out=str(tmp_path / "out"))
        assert _run_parse(args) == 2

    def test_exit_2_when_path_is_a_file_not_a_dir(self, tmp_path, make_minimal_pdf):
        f = make_minimal_pdf(tmp_path / "lonely.pdf", ["body"])
        args = argparse.Namespace(package_dir=str(f), out=str(tmp_path / "out"))
        assert _run_parse(args) == 2


class TestArtifactOutput:
    def test_document_map_json_written_under_package_name(self, tmp_path, monkeypatch):
        pkg = tmp_path / "my-package"
        pkg.mkdir()
        monkeypatch.setattr("rfp_analyzer.cli.run_pipeline", lambda _dir: _synthetic_map())
        out = tmp_path / "artifacts"
        args = argparse.Namespace(package_dir=str(pkg), out=str(out))

        assert _run_parse(args) == 0

        # T-01-16: the artifact path derives from the package dir's own name,
        # not from any file-derived name inside the package.
        map_path = out / "my-package" / "document_map.json"
        assert map_path.exists(), "document_map.json not written under <out>/<package_name>/"

        # The artifact is valid JSON and re-validates against the schema.
        payload = json.loads(map_path.read_text(encoding="utf-8"))
        assert payload["package_name"] == "primary-ucf"
        DocumentMap.model_validate_json(map_path.read_text(encoding="utf-8"))


class TestMainUsage:
    def test_main_with_no_command_prints_help_and_exits_2(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["rfp-analyzer"])
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("main() did not exit on missing command")
        out = capsys.readouterr().out
        assert "usage" in out.lower()

    def test_main_parse_of_missing_dir_exits_2(self, monkeypatch, tmp_path):
        missing = tmp_path / "nope"
        monkeypatch.setattr("sys.argv", ["rfp-analyzer", "parse", str(missing)])
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("main() did not exit on missing directory")
