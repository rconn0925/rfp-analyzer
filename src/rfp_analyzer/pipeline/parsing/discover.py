"""File discovery: stable identity, extension allowlist, hostile-input guards.

Walks a package directory and classifies every file for downstream parsing.
Threats addressed (see plan 01-03 threat model):

- T-01-08 path traversal: ``resolve()``-containment check rejects any file
  (e.g. via symlink/junction) whose real path escapes the package dir.
- T-01-06 pre-parse DoS: per-file size cap before a parser ever opens it.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rfp_analyzer.pipeline.models import ParsedFile

MAX_FILE_BYTES = 250 * 1024 * 1024
"""Per-file size cap. Module-level so it is corpus-tunable and test-patchable."""

_STEM_SANITIZER = re.compile(r"[^a-z0-9]+")

_SUFFIX_KINDS: dict[str, Literal["pdf", "docx"]] = {
    ".pdf": "pdf",
    ".docx": "docx",
}


@dataclass(frozen=True)
class DiscoveredFile:
    """One file found in the package, classified for parsing or rejected."""

    path: Path
    filename: str
    sha256: str
    file_id: str
    kind: Literal["pdf", "docx", "rejected"]
    rejection: ParsedFile | None = None


def _is_within(path: Path, root: Path) -> bool:
    """True if path's resolved location is contained in root's resolved location."""
    return path.resolve().is_relative_to(root.resolve())


def _file_identity(path: Path) -> tuple[str, str]:
    """Streaming sha256 (1 MB chunks) + `{sha[:12]}-{sanitized-stem}` file_id."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    stem = _STEM_SANITIZER.sub("-", path.stem.lower()).strip("-")[:40]
    return digest, f"{digest[:12]}-{stem}"


def _rejection(
    filename: str,
    sha256: str,
    file_id: str,
    file_type: Literal["pdf", "docx", "other"],
    error: str,
) -> ParsedFile:
    return ParsedFile(
        file_id=file_id,
        filename=filename,
        sha256=sha256,
        file_type=file_type,
        parse_status="rejected",
        error=error,
    )


def discover_files(package_dir: Path) -> list[DiscoveredFile]:
    """Discover every file under package_dir, classified pdf/docx/rejected.

    Nested directories are traversed (SAM.gov zips often nest attachments);
    each entry's ``filename`` records the posix-style path relative to
    ``package_dir``. Rejections carry a prebuilt ParsedFile with an explicit
    error message — discovery never raises on hostile input.
    """
    discovered: list[DiscoveredFile] = []
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        filename = path.relative_to(package_dir).as_posix()

        # Containment first: never read a file whose real location escapes
        # the package dir (symlinks/junctions/crafted names — T-01-08).
        if not _is_within(path, package_dir):
            file_id = "0" * 12 + "-" + _STEM_SANITIZER.sub("-", path.stem.lower()).strip("-")[:40]
            discovered.append(
                DiscoveredFile(
                    path=path,
                    filename=filename,
                    sha256="",
                    file_id=file_id,
                    kind="rejected",
                    rejection=_rejection(
                        filename,
                        "",
                        file_id,
                        "other",
                        f"outside package directory: {filename} resolves outside the package",
                    ),
                )
            )
            continue

        sha256, file_id = _file_identity(path)
        suffix = path.suffix.lower()
        kind = _SUFFIX_KINDS.get(suffix)

        if suffix == ".doc":
            error = ".doc legacy Word not supported — convert to .docx and re-upload"
            rejection = _rejection(filename, sha256, file_id, "other", error)
        elif kind is None:
            error = f"unsupported file type: {suffix or '(no extension)'}"
            rejection = _rejection(filename, sha256, file_id, "other", error)
        elif path.stat().st_size > MAX_FILE_BYTES:
            error = f"file size {path.stat().st_size} bytes exceeds cap of {MAX_FILE_BYTES} bytes"
            rejection = _rejection(filename, sha256, file_id, kind, error)
        else:
            discovered.append(
                DiscoveredFile(
                    path=path, filename=filename, sha256=sha256, file_id=file_id, kind=kind
                )
            )
            continue

        discovered.append(
            DiscoveredFile(
                path=path,
                filename=filename,
                sha256=sha256,
                file_id=file_id,
                kind="rejected",
                rejection=rejection,
            )
        )
    return discovered
