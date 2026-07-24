"""Behavior tests for PDF parsing: per-page text, raw metrics, failure isolation."""

import time
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.parsing.pdf import parse_pdf

SHA = "c" * 64
FILE_ID = "cccccccccccc-synthetic-pdf"

PAGE_TEXTS = ["First page alpha text", "Second page bravo text", "Third page charlie text"]


@pytest.fixture
def three_page_pdf(tmp_path: Path, make_minimal_pdf) -> Path:
    return make_minimal_pdf(tmp_path / "three.pdf", PAGE_TEXTS)


def test_three_page_pdf_parses_ok_with_1_indexed_pages(three_page_pdf: Path):
    """A 3-page PDF parses ok with 1-indexed page numbers and per-page text."""
    start = time.monotonic()
    parsed = parse_pdf(three_page_pdf, sha256=SHA, file_id=FILE_ID)
    elapsed = time.monotonic() - start

    assert parsed.parse_status == "ok"
    assert parsed.file_type == "pdf"
    assert parsed.page_count == 3
    assert len(parsed.pages) == 3
    for i, page in enumerate(parsed.pages):
        assert page.page_number == i + 1
        assert PAGE_TEXTS[i] in page.text
    # Wall-clock sanity guard against accidental quadratic behavior.
    assert elapsed < 10.0


def test_garbage_pdf_fails_without_exception(tmp_path: Path):
    """Garbage bytes after a %PDF header yield parse_status 'failed', never a crash."""
    garbage = tmp_path / "garbage.pdf"
    garbage.write_bytes(b"%PDF-1.4\n" + bytes(range(256)) * 64)

    parsed = parse_pdf(garbage, sha256=SHA, file_id=FILE_ID)
    assert parsed.parse_status == "failed"
    assert parsed.error
    assert parsed.pages == []


def test_page_metrics_capture_raw_quality_signals(three_page_pdf: Path):
    """Each page records cid_count, replacement_char_count, has_images, char_count."""
    parsed = parse_pdf(three_page_pdf, sha256=SHA, file_id=FILE_ID)
    for page in parsed.pages:
        assert "cid_count" in page.metrics
        assert "replacement_char_count" in page.metrics
        assert page.metrics["has_images"] in (0.0, 1.0)
        assert page.char_count > 0
        # Synthetic fixture pages are clean born-digital text.
        assert page.metrics["cid_count"] == 0.0
        assert page.metrics["replacement_char_count"] == 0.0
        assert page.metrics["has_images"] == 0.0


def test_all_pages_quality_pending(three_page_pdf: Path):
    """Quality stage owns final status — parser marks every page 'pending'."""
    parsed = parse_pdf(three_page_pdf, sha256=SHA, file_id=FILE_ID)
    assert parsed.pages
    assert all(page.quality == "pending" for page in parsed.pages)


def test_first_page_layout_text_populated(three_page_pdf: Path):
    """first_page_layout_text is captured (layout=True, page 1 only)."""
    parsed = parse_pdf(three_page_pdf, sha256=SHA, file_id=FILE_ID)
    assert parsed.first_page_layout_text is not None
    assert PAGE_TEXTS[0].split()[0] in parsed.first_page_layout_text


def test_identity_passed_through(three_page_pdf: Path):
    """parse_pdf stamps the caller-provided sha256 and file_id onto the record."""
    parsed = parse_pdf(three_page_pdf, sha256=SHA, file_id=FILE_ID)
    assert parsed.sha256 == SHA
    assert parsed.file_id == FILE_ID
    assert parsed.filename == "three.pdf"  # defaults to the basename


def test_discovered_relative_filename_is_preserved(three_page_pdf: Path):
    """WR-03: the discovery-assigned relative path wins over the basename."""
    parsed = parse_pdf(
        three_page_pdf, sha256=SHA, file_id=FILE_ID, filename="attachments/three.pdf"
    )
    assert parsed.filename == "attachments/three.pdf"
