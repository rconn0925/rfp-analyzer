"""Per-file parsing layer: discovery, PDF (pdfplumber), and DOCX (python-docx).

Pure library code — no HTTP, queue, or CLI imports. Every failure mode
produces an explicit per-file status on a ParsedFile, never a crashed run.
"""
