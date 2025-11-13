"""Backwards compatibility layer for legacy imports.

Prefer importing :mod:`config.core` directly. This module simply re-exports
the shared configuration instance as ``cfg`` so that older scripts keep
working while the codebase migrates to the new package layout.
"""

from config.core import cfg  # noqa: F401

__all__ = ["cfg"]
