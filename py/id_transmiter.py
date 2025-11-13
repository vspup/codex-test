"""Compatibility wrapper for :mod:`py.desktop.id_transmiter`."""

from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.append(str(PACKAGE_ROOT))

_id_transmiter = import_module("py.desktop.id_transmiter")

if hasattr(_id_transmiter, "__all__"):
    __all__ = list(_id_transmiter.__all__)  # type: ignore[attr-defined]
else:
    __all__ = [name for name in dir(_id_transmiter) if not name.startswith("_")]

globals().update({name: getattr(_id_transmiter, name) for name in __all__})


if __name__ == "__main__":
    asyncio.run(_id_transmiter.main())
