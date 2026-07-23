"""Pure pipeline library: every stage is ``f(artifact) -> artifact``.

This subpackage must never import HTTP clients, queue libraries, or CLI
modules — it is the boundary that lets the pipeline run under a CLI now
and a web/worker wrapper in later phases.
"""
