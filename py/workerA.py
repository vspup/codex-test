"""Compatibility wrapper for :mod:`py.edge.workerA`."""

from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.append(str(PACKAGE_ROOT))

_workerA = import_module("py.edge.workerA")

if hasattr(_workerA, "__all__"):
    __all__ = list(_workerA.__all__)  # type: ignore[attr-defined]
else:
    __all__ = [name for name in dir(_workerA) if not name.startswith("_")]

globals().update({name: getattr(_workerA, name) for name in __all__})


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(_workerA.main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        exit_code = 130
    sys.exit(exit_code)
