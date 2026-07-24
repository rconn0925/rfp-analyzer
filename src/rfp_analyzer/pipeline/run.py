"""Full-pipeline orchestration: discover -> parse -> quality -> sectioning -> classify.

:func:`run_pipeline` is the single library entry point the CLI (and later the
web/worker services) wrap. It is pure orchestration — no printing, no
network, no queue, no CLI imports (the locked import boundary: presentation
code imports the pipeline, never the reverse).

Stage timings are captured with ``time.perf_counter`` into
``RunMetrics.stage_timings`` under the keys ``discover`` / ``parse`` /
``quality`` / ``sectioning`` / ``classify``. LLM counters stay zero in
Phase 1 (D-09 scaffolding — Phase 2 fills them without a schema change).
"""

import time
from pathlib import Path

from rfp_analyzer.pipeline.classify.forms import assign_doc_role
from rfp_analyzer.pipeline.classify.package import classify_package
from rfp_analyzer.pipeline.metrics import RunMetrics
from rfp_analyzer.pipeline.models import DocumentMap, ParsedFile
from rfp_analyzer.pipeline.parsing import sanitize_text
from rfp_analyzer.pipeline.parsing.discover import discover_files
from rfp_analyzer.pipeline.parsing.docx import parse_docx
from rfp_analyzer.pipeline.parsing.pdf import parse_pdf
from rfp_analyzer.pipeline.quality.headers import apply_quality
from rfp_analyzer.pipeline.sectioning.tree import build_section_tree


def run_pipeline(package_dir: Path) -> DocumentMap:
    """Run the full Phase 1 pipeline over one package directory.

    Returns a :class:`~rfp_analyzer.pipeline.models.DocumentMap` — the
    versioned Phase 2 input contract. Never raises on hostile package
    content: per-file failures land as ``parse_status="failed"`` /
    ``"rejected"`` entries (isolation is enforced by the parsing stage).
    """
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    discovered = discover_files(package_dir)
    timings["discover"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    files: list[ParsedFile] = []
    for entry in discovered:
        if entry.kind == "rejected" and entry.rejection is not None:
            files.append(entry.rejection)
        elif entry.kind == "pdf":
            files.append(
                parse_pdf(
                    entry.path,
                    filename=entry.filename,
                    sha256=entry.sha256,
                    file_id=entry.file_id,
                )
            )
        elif entry.kind == "docx":
            files.append(
                parse_docx(
                    entry.path,
                    filename=entry.filename,
                    sha256=entry.sha256,
                    file_id=entry.file_id,
                )
            )
    timings["parse"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    files = [apply_quality(file) for file in files]
    timings["quality"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    for file in files:
        if file.parse_status == "ok":
            file.sections = build_section_tree(file)
    timings["sectioning"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    files = [assign_doc_role(file) for file in files]
    classification, evidence, warnings = classify_package(files)
    timings["classify"] = time.perf_counter() - t0

    metrics = RunMetrics(
        stage_timings=timings,
        files_parsed=sum(1 for f in files if f.parse_status == "ok"),
        pages_parsed=sum(len(f.pages) for f in files),
        pages_flagged=sum(1 for f in files for p in f.pages if p.quality != "ok"),
    )

    return DocumentMap(
        package_name=sanitize_text(package_dir.name),
        classification=classification,
        classification_evidence=evidence,
        warnings=warnings,
        files=files,
        metrics=metrics,
    )
