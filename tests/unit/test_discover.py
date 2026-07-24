"""Behavior tests for file discovery: identity, allowlist, hostile-input guards."""

import os
import re
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.parsing import discover
from rfp_analyzer.pipeline.parsing.discover import discover_files


@pytest.fixture
def mixed_package(tmp_path: Path, make_minimal_pdf, make_docx) -> Path:
    """Package dir with one file of each interesting kind."""
    pkg = tmp_path / "package"
    pkg.mkdir()
    make_minimal_pdf(pkg / "a.pdf", ["Alpha page one"])
    make_docx(pkg / "b.docx", ["Bravo paragraph"])
    (pkg / "c.doc").write_bytes(b"\xd0\xcf\x11\xe0legacy word bytes")
    (pkg / "d.txt").write_text("plain text file")
    return pkg


def _by_name(entries, name):
    return next(e for e in entries if Path(e.path).name == name)


def test_mixed_directory_classifies_and_rejects(mixed_package: Path):
    """pdf/docx classified for parsing; .doc and unknown extensions rejected explicitly."""
    entries = discover_files(mixed_package)
    assert len(entries) == 4

    assert _by_name(entries, "a.pdf").kind == "pdf"
    assert _by_name(entries, "b.docx").kind == "docx"

    doc_entry = _by_name(entries, "c.doc")
    assert doc_entry.kind == "rejected"
    assert doc_entry.rejection is not None
    assert doc_entry.rejection.parse_status == "rejected"
    assert "doc" in doc_entry.rejection.error
    assert "not supported" in doc_entry.rejection.error

    txt_entry = _by_name(entries, "d.txt")
    assert txt_entry.kind == "rejected"
    assert txt_entry.rejection is not None
    assert txt_entry.rejection.parse_status == "rejected"
    assert "unsupported file type" in txt_entry.rejection.error


def test_every_entry_has_stable_identity(mixed_package: Path):
    """Every entry carries sha256 (64 hex) and file_id `{sha[:12]}-{sanitized-stem}`."""
    entries = discover_files(mixed_package)
    for entry in entries:
        assert re.fullmatch(r"[0-9a-f]{64}", entry.sha256), entry.path
        assert entry.file_id.startswith(entry.sha256[:12] + "-")
        stem_part = entry.file_id[13:]
        assert re.fullmatch(r"[a-z0-9-]{1,40}", stem_part), entry.file_id

    # Determinism: hashing the same files again yields identical identities.
    again = discover_files(mixed_package)
    assert sorted(e.file_id for e in entries) == sorted(e.file_id for e in again)


def test_file_id_sanitizes_and_truncates_stem(tmp_path: Path):
    """Non-alphanumeric runs collapse to '-' and the stem caps at 40 chars."""
    pkg = tmp_path / "package"
    pkg.mkdir()
    long_name = "Solicitation  (FINAL) & Amended!! " + "x" * 60 + ".pdf"
    (pkg / long_name).write_bytes(b"%PDF-1.4 stub")
    entries = discover_files(pkg)
    assert len(entries) == 1
    stem_part = entries[0].file_id.split("-", 1)[1]
    assert len(stem_part) <= 40
    assert re.fullmatch(r"[a-z0-9-]+", stem_part)


def test_oversize_file_rejected(tmp_path: Path, monkeypatch, make_minimal_pdf):
    """A file exceeding MAX_FILE_BYTES is rejected with a size-related error."""
    monkeypatch.setattr(discover, "MAX_FILE_BYTES", 64)
    pkg = tmp_path / "package"
    pkg.mkdir()
    make_minimal_pdf(pkg / "big.pdf", ["This PDF body is comfortably larger than 64 bytes"])

    entries = discover_files(pkg)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "rejected"
    assert entry.rejection.parse_status == "rejected"
    assert "size" in entry.rejection.error.lower()


def test_containment_check_rejects_outside_paths(tmp_path: Path, monkeypatch):
    """A path whose resolve() is not under package_dir.resolve() is rejected."""
    pkg = tmp_path / "package"
    pkg.mkdir()
    (pkg / "inside.pdf").write_bytes(b"%PDF-1.4 stub")

    monkeypatch.setattr(discover, "_is_within", lambda path, root: False)
    entries = discover_files(pkg)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "rejected"
    assert "outside package directory" in entry.rejection.error


def test_symlink_escaping_package_dir_rejected(tmp_path: Path):
    """A symlink pointing outside package_dir is rejected, not followed."""
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 outside stub")
    pkg = tmp_path / "package"
    pkg.mkdir()
    link = pkg / "sneaky.pdf"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privileges on this platform")

    entries = discover_files(pkg)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.kind == "rejected"
    assert "outside package directory" in entry.rejection.error


@pytest.mark.parametrize(
    "exc",
    [
        PermissionError(13, "The process cannot access the file"),
        FileNotFoundError(2, "No such file or directory"),
        OSError(1224, "The requested operation cannot be performed"),
    ],
    ids=["locked", "vanished", "generic-oserror"],
)
def test_unreadable_file_rejected_not_raised(
    tmp_path: Path, monkeypatch, make_minimal_pdf, exc: OSError
):
    """A locked/vanished/unreadable file becomes a rejected record, not a crash.

    CR-01 regression: discovery runs BEFORE the parsers' per-file isolation,
    so an OSError from the stat/open of one entry used to take down the whole
    package run.
    """
    pkg = tmp_path / "package"
    pkg.mkdir()
    make_minimal_pdf(pkg / "locked.pdf", ["Locked by another process"])
    make_minimal_pdf(pkg / "fine.pdf", ["Readable"])

    real_identity = discover._file_identity

    def flaky_identity(path: Path):
        if path.name == "locked.pdf":
            raise exc
        return real_identity(path)

    monkeypatch.setattr(discover, "_file_identity", flaky_identity)

    entries = discover_files(pkg)
    assert len(entries) == 2

    locked = _by_name(entries, "locked.pdf")
    assert locked.kind == "rejected"
    assert locked.rejection.parse_status == "rejected"
    assert "unreadable file" in locked.rejection.error

    # The rest of the package is unaffected — isolation is per file.
    assert _by_name(entries, "fine.pdf").kind == "pdf"


def test_is_within_fails_closed_on_unresolvable_path(tmp_path: Path):
    """resolve() raising (symlink/junction loop) means 'not contained', not a crash."""

    class Unresolvable:
        def resolve(self):
            raise OSError(1921, "The name of the file cannot be resolved by the system")

    assert discover._is_within(Unresolvable(), tmp_path) is False


def test_nested_files_discovered_with_relative_path(tmp_path: Path, make_minimal_pdf):
    """Files in nested dirs ARE discovered; filename records the relative path."""
    pkg = tmp_path / "package"
    (pkg / "attachments").mkdir(parents=True)
    make_minimal_pdf(pkg / "base.pdf", ["Base solicitation"])
    make_minimal_pdf(pkg / "attachments" / "sow.pdf", ["Statement of work"])

    entries = discover_files(pkg)
    filenames = sorted(e.filename for e in entries)
    assert filenames == ["attachments/sow.pdf", "base.pdf"]
