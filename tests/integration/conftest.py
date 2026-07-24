"""Corpus-driven integration fixtures and the no-corpus skip guard.

Expectations come ONLY from ``tests/corpus/manifest.json`` so the suite is
corpus-portable. The corpus binaries are gitignored (D-02): CI has the
manifests but no package files, so the skip condition checks for the actual
package directories listed in the manifest — when any is missing or empty,
every test in this directory is SKIPPED, never failed.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from rfp_analyzer.pipeline.models import DocumentMap
from rfp_analyzer.pipeline.run import run_pipeline

CORPUS_DIR = Path("tests/corpus")
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

OLLAMA_HOST = os.environ.get("RFP_OLLAMA_HOST", "http://localhost:11434")
"""Where the local model runtime is expected. Overridable so the skip path can be
exercised (point it at an unreachable host)."""


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


def ollama_available(host: str = OLLAMA_HOST, timeout: float = 2.0) -> bool:
    """True when the local Ollama runtime answers GET /api/version quickly.

    A cheap liveness probe (stdlib urllib — no import cost in conftest) so
    model-calling integration tests SKIP rather than fail on a machine with no
    GPU/Ollama (CI). Any error — connection refused, timeout, non-200 — is a
    clean False.
    """
    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_ollama: integration test makes real local-model calls; skipped "
        "when Ollama is unreachable (CI has no GPU/runtime).",
    )


def pytest_collection_modifyitems(config, items):
    here = Path(__file__).parent
    corpus_ok = corpus_available()
    ollama_ok = ollama_available()
    corpus_skip = pytest.mark.skip(
        reason="corpus binaries absent (gitignored, D-02) — see tests/corpus/MANIFEST.md"
    )
    ollama_skip = pytest.mark.skip(
        reason=f"Ollama unreachable at {OLLAMA_HOST} — model-calling tests skipped (CI has none)"
    )
    for item in items:
        if here not in Path(item.fspath).parents:
            continue
        if not corpus_ok:
            item.add_marker(corpus_skip)
        if item.get_closest_marker("requires_ollama") is not None and not ollama_ok:
            item.add_marker(ollama_skip)


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
