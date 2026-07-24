"""Behavior tests for run_pipeline wiring (stage order, identity threading).

Synthetic packages only — no corpus needed, CI-safe.
"""

from pathlib import Path

import pdfplumber
import pytest

from rfp_analyzer.pipeline.models import DocumentMap
from rfp_analyzer.pipeline.parsing import sanitize_text
from rfp_analyzer.pipeline.run import run_pipeline

LONE_SURROGATE = chr(0xD800)


class TestSanitizeText:
    def test_clean_text_is_untouched(self):
        text = "The contractor shall provide services — per Section L."
        assert sanitize_text(text) is text

    def test_lone_surrogate_becomes_replacement_char(self):
        cleaned = sanitize_text(f"Requirement {LONE_SURROGATE} text")
        assert LONE_SURROGATE not in cleaned
        assert "�" in cleaned  # the gibberish gate's signal, never a bare "?"
        assert cleaned.startswith("Requirement ")
        assert cleaned.endswith(" text")
        cleaned.encode("utf-8")

    @pytest.mark.parametrize("raw", ["", "plain", "(cid:0)(cid:2)", "� already"])
    def test_serializable_text_round_trips(self, raw: str):
        assert sanitize_text(raw) == raw


def test_hostile_surrogate_text_still_serializes(tmp_path: Path, monkeypatch, make_minimal_pdf):
    """WR-05 regression: a PDF whose ToUnicode CMap yields lone surrogates.

    Lone surrogates are legal `str` values that cannot be UTF-8 encoded, so
    they used to blow up DocumentMap.model_dump_json() — crashing the run at
    the final artifact write, after the whole pipeline had succeeded.
    """
    pkg = tmp_path / "package"
    make_minimal_pdf(pkg / "hostile.pdf", ["Placeholder text"])

    real_extract = pdfplumber.page.Page.extract_text

    def hostile_extract(self, *args, **kwargs):
        return f"SECTION L {LONE_SURROGATE} INSTRUCTIONS" + real_extract(self, *args, **kwargs)

    monkeypatch.setattr(pdfplumber.page.Page, "extract_text", hostile_extract)

    dmap = run_pipeline(pkg)

    payload = dmap.model_dump_json(indent=2)  # used to raise PydanticSerializationError
    assert LONE_SURROGATE not in payload
    payload.encode("utf-8")  # and the artifact write itself must not raise
    DocumentMap.model_validate_json(payload)


def test_parsed_and_rejected_files_share_one_naming_convention(
    tmp_path: Path, make_minimal_pdf, make_docx
):
    """WR-03: every ParsedFile.filename is the posix path relative to the package.

    Parsed records used to carry the basename while rejections carried the
    relative path — two conventions in one document map, and nested files
    with the same basename were indistinguishable to Phase 2.
    """
    pkg = tmp_path / "package"
    make_minimal_pdf(pkg / "base.pdf", ["Base solicitation"])
    make_minimal_pdf(pkg / "amd1" / "SF30.pdf", ["Amendment one"])
    make_minimal_pdf(pkg / "amd2" / "SF30.pdf", ["Amendment two"])
    make_docx(pkg / "attachments" / "sow.docx", ["The contractor shall provide services."])
    (pkg / "attachments" / "notes.txt").write_text("unsupported", encoding="utf-8")

    dmap = run_pipeline(pkg)
    filenames = sorted(f.filename for f in dmap.files)
    assert filenames == [
        "amd1/SF30.pdf",
        "amd2/SF30.pdf",
        "attachments/notes.txt",
        "attachments/sow.docx",
        "base.pdf",
    ]

    # Nested same-basename files stay distinguishable in the Phase 2 contract.
    assert len({f.filename for f in dmap.files}) == len(dmap.files)
    assert len({f.file_id for f in dmap.files}) == len(dmap.files)


def test_pipeline_leaves_no_pending_pages(tmp_path: Path, make_minimal_pdf):
    """The quality stage runs for every parsed PDF the pipeline produces."""
    pkg = tmp_path / "package"
    make_minimal_pdf(pkg / "doc.pdf", ["Alpha page", "Bravo page"])

    dmap = run_pipeline(pkg)
    assert dmap.files
    for file in dmap.files:
        for page in file.pages:
            assert page.quality != "pending"
