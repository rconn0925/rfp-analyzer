"""Behavior tests for DOCX parsing: ordered blocks, no fake pages, zip-bomb guard."""

import zipfile
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.parsing import docx as docx_module
from rfp_analyzer.pipeline.parsing.docx import parse_docx

SHA = "d" * 64
FILE_ID = "dddddddddddd-synthetic-docx"


def test_blocks_in_document_order_with_styles_and_tables(tmp_path: Path, make_docx):
    """Paragraphs and a table interleave with 0-indexed ordinals in doc order."""
    path = make_docx(
        tmp_path / "ordered.docx",
        [
            ("STATEMENT OF WORK", "Heading 1"),
            "The contractor shall provide services.",
            {"table": [["Task", "Due"], ["Kickoff", "TBD"]]},
            "Final closing paragraph.",
        ],
    )

    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)
    assert parsed.parse_status == "ok"
    assert [b.ordinal for b in parsed.blocks] == [0, 1, 2, 3]

    assert parsed.blocks[0].kind == "paragraph"
    assert parsed.blocks[0].text == "STATEMENT OF WORK"
    assert parsed.blocks[0].style == "Heading 1"

    assert parsed.blocks[1].kind == "paragraph"
    assert parsed.blocks[1].style == "Normal"

    assert parsed.blocks[2].kind == "table"
    assert parsed.blocks[2].table == [["Task", "Due"], ["Kickoff", "TBD"]]

    assert parsed.blocks[3].kind == "paragraph"
    assert parsed.blocks[3].text == "Final closing paragraph."


def test_no_synthesized_page_numbers(tmp_path: Path, make_docx):
    """DOCX has no fixed pages: page_count None, pages empty — block ordinals only."""
    path = make_docx(tmp_path / "plain.docx", ["Just one paragraph."])
    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)

    assert parsed.file_type == "docx"
    assert parsed.page_count is None
    assert parsed.pages == []


def test_corrupt_docx_fails_without_exception(tmp_path: Path):
    """Random bytes with a .docx extension yield parse_status 'failed', no crash."""
    path = tmp_path / "corrupt.docx"
    path.write_bytes(bytes(range(256)) * 16)

    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)
    assert parsed.parse_status == "failed"
    assert parsed.error
    assert parsed.blocks == []


def test_zip_bomb_rejected_before_python_docx(tmp_path: Path, monkeypatch):
    """A zip exceeding the uncompressed-size guard fails pre-parse with a size message."""
    monkeypatch.setattr(docx_module, "MAX_DOCX_UNCOMPRESSED", 10_000)
    path = tmp_path / "bomb.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", b"\0" * 50_000)

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("python-docx must not be invoked on a bomb-suspect file")

    monkeypatch.setattr(docx_module, "Document", _explode)

    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)
    assert parsed.parse_status == "failed"
    assert "size" in parsed.error.lower() or "decompress" in parsed.error.lower()


def test_high_compression_ratio_rejected(tmp_path: Path, monkeypatch):
    """A member with an extreme compression ratio trips the bomb guard."""
    path = tmp_path / "ratio-bomb.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 20 MB of zeros deflates to a few KB — ratio far beyond 200x.
        zf.writestr("word/document.xml", b"\0" * (20 * 1024 * 1024))

    monkeypatch.setattr(
        docx_module,
        "Document",
        lambda *a, **k: pytest.fail("python-docx must not open a bomb-suspect file"),
    )

    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)
    assert parsed.parse_status == "failed"
    assert parsed.error


def test_identity_passed_through(tmp_path: Path, make_docx):
    """parse_docx stamps the caller-provided sha256 and file_id onto the record."""
    path = make_docx(tmp_path / "identity.docx", ["Paragraph."])
    parsed = parse_docx(path, sha256=SHA, file_id=FILE_ID)
    assert parsed.sha256 == SHA
    assert parsed.file_id == FILE_ID
    assert parsed.filename == "identity.docx"
