"""Corpus-driven integration fixtures and the no-corpus skip guard.

Expectations come ONLY from ``tests/corpus/manifest.json`` so the suite is
corpus-portable. The corpus binaries are gitignored (D-02): CI has the
manifests but no package files, so the skip condition checks for the actual
package directories listed in the manifest — when any is missing or empty,
every test in this directory is SKIPPED, never failed.
"""

import json
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.models import DocumentMap
from rfp_analyzer.pipeline.run import run_pipeline

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"


def load_packages() -> list[dict]:
    """Package expectation records from tests/corpus/manifest.json."""
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["packages"]


def corpus_available() -> bool:
    """True only when every manifest-listed package dir exists and has files."""
    packages = load_packages()
    if not packages:
        return False
    return all(any((CORPUS_DIR / pkg["dir"]).glob("*")) for pkg in packages)


def pytest_collection_modifyitems(config, items):
    if corpus_available():
        return
    here = Path(__file__).parent
    skip = pytest.mark.skip(
        reason="corpus binaries absent (gitignored, D-02) — see tests/corpus/MANIFEST.md"
    )
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(skip)


_maps: dict[str, DocumentMap] = {}


@pytest.fixture(scope="session")
def pipeline_map():
    """Run run_pipeline at most once per corpus package (session-wide cache).

    Three packages x one parse each — parsing the 408-page hostile package
    takes ~1 minute, so every test shares the same DocumentMap instances.
    """

    def get(pkg: dict) -> DocumentMap:
        if pkg["dir"] not in _maps:
            _maps[pkg["dir"]] = run_pipeline(CORPUS_DIR / pkg["dir"])
        return _maps[pkg["dir"]]

    return get
