"""Per-file parsing layer: discovery, PDF (pdfplumber), and DOCX (python-docx).

Pure library code — no HTTP, queue, or CLI imports. Every failure mode
produces an explicit per-file status on a ParsedFile, never a crashed run.
"""


def sanitize_text(text: str) -> str:
    """Fold extracted text to text that can actually be serialized.

    A malformed or hostile PDF whose ToUnicode CMap maps glyphs to surrogate
    code points yields Python strings containing lone surrogates. Those are
    legal ``str`` values but cannot be encoded as UTF-8, so they blow up
    ``DocumentMap.model_dump_json()`` — crashing the run at the final artifact
    write, after the whole pipeline succeeded. Every parser passes extracted
    text through here so unserializable content never enters the document
    map.

    Lone surrogates become U+FFFD, which is exactly what the quality gates'
    ``replacement_char_count`` measures: a glyph with no valid Unicode
    mapping. Text that is already clean is returned unchanged.

    ``surrogatepass`` encodes the surrogate to its (invalid) UTF-8 byte
    sequence so the decode step can map it to U+FFFD; plain
    ``errors="replace"`` on encode would substitute ``?``, which is a
    legitimate character and would silently corrupt the text instead.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return text.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
    return text
