"""Behavior tests for run_pipeline wiring (stage order, identity threading).

Synthetic packages only — no corpus needed, CI-safe.
"""

from pathlib import Path

from rfp_analyzer.pipeline.run import run_pipeline


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
