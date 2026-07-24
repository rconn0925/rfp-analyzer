"""Verbatim grounding: compute + string-match-verify requirement source refs.

Pure library code — no HTTP, queue, or CLI imports. A requirement's
``verbatim_text`` must locate inside its cited page text after normalization; a
quote that cannot be located is flagged ``verified=False``, never silently
dropped. This is the EXTR-02 honesty backbone: no model-emitted citation ever
reaches output.
"""
