"""Compatibility wrapper for :mod:`py.edge.dm7275`."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.append(str(PACKAGE_ROOT))

dm7275 = import_module("py.edge.dm7275")

if hasattr(dm7275, "__all__"):
    __all__ = list(dm7275.__all__)  # type: ignore[attr-defined]
else:
    __all__ = [name for name in dir(dm7275) if not name.startswith("_")]

globals().update({name: getattr(dm7275, name) for name in __all__})


if __name__ == "__main__":
    dm7275.main()
