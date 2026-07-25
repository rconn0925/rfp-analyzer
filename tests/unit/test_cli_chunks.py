"""The `chunks` export — step one of the two-step Claude Code extraction flow."""

from __future__ import annotations

import argparse
import json

from rfp_analyzer.cli import _run_chunks, build_parser
from rfp_analyzer.pipeline.extraction.chunker import chunk_key
from rfp_analyzer.pipeline.models import DocumentMap, PageInfo, ParsedFile

PAGE = "SECTION L. The offeror shall submit a technical proposal of 30 pages or fewer."


def _map(text: str = PAGE) -> DocumentMap:
    return DocumentMap(
        package_name="synthetic",
        classification="full_ucf",
        files=[
            ParsedFile(
                file_id="ffffffffffff-solicitation",
                filename="Solicitation.pdf",
                sha256="0" * 64,
                file_type="pdf",
                parse_status="ok",
                doc_role="base_solicitation",
                page_count=1,
                pages=[PageInfo(page_number=1, quality="ok", char_count=len(text), text=text)],
            )
        ],
    )


def _write_map(artifacts, dmap: DocumentMap) -> None:
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "document_map.json").write_text(
        dmap.model_dump_json(indent=2), encoding="utf-8"
    )


def _args(artifacts, out=None) -> argparse.Namespace:
    return argparse.Namespace(artifacts_dir=str(artifacts), out=out and str(out))


def test_writes_one_record_per_chunk(tmp_path, capsys):
    artifacts = tmp_path / "pkg"
    _write_map(artifacts, _map())
    assert _run_chunks(_args(artifacts)) == 0

    lines = (artifacts / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["chunk_key"] == chunk_key(record["text"])
    assert record["file_id"] == "ffffffffffff-solicitation"
    assert record["filename"] == "Solicitation.pdf"
    assert PAGE in record["text"]


def test_page_map_is_not_exported(tmp_path):
    """Page provenance is recomputed at grounding time, never round-tripped
    through the engine — so a page reference cannot be influenced by output."""
    artifacts = tmp_path / "pkg"
    _write_map(artifacts, _map())
    _run_chunks(_args(artifacts))
    record = json.loads((artifacts / "chunks.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "page_map" not in record


def test_export_is_deterministic(tmp_path):
    artifacts = tmp_path / "pkg"
    _write_map(artifacts, _map())
    _run_chunks(_args(artifacts))
    first = (artifacts / "chunks.jsonl").read_text(encoding="utf-8")
    _run_chunks(_args(artifacts))
    assert (artifacts / "chunks.jsonl").read_text(encoding="utf-8") == first


def test_honors_explicit_out_path(tmp_path):
    artifacts = tmp_path / "pkg"
    _write_map(artifacts, _map())
    out = tmp_path / "nested" / "c.jsonl"
    assert _run_chunks(_args(artifacts, out)) == 0
    assert out.exists()


def test_missing_document_map_returns_exit_2(tmp_path):
    artifacts = tmp_path / "pkg"
    artifacts.mkdir()
    assert _run_chunks(_args(artifacts)) == 2


def test_nonexistent_dir_returns_exit_2(tmp_path):
    assert _run_chunks(_args(tmp_path / "nope")) == 2


def test_output_names_the_next_step(tmp_path, capsys):
    """The two-step flow is only usable if step one says what step two is."""
    artifacts = tmp_path / "pkg"
    _write_map(artifacts, _map())
    _run_chunks(_args(artifacts))
    out = capsys.readouterr().out
    assert "drafts.jsonl" in out
    assert "rfp-analyzer extract" in out


def test_parser_registers_chunks_command():
    args = build_parser().parse_args(["chunks", "artifacts/x", "--out", "c.jsonl"])
    assert args.command == "chunks"
    assert args.out == "c.jsonl"
