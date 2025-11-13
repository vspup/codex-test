"""Compatibility wrapper for :mod:`py.edge.worker_server`."""

from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path

if __package__ in {None, ""}:
    PACKAGE_ROOT = Path(__file__).resolve().parent.parent
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.append(str(PACKAGE_ROOT))

_worker_server = import_module("py.edge.worker_server")

if hasattr(_worker_server, "__all__"):
    __all__ = list(_worker_server.__all__)  # type: ignore[attr-defined]
else:
    __all__ = [name for name in dir(_worker_server) if not name.startswith("_")]

globals().update({name: getattr(_worker_server, name) for name in __all__})


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(_worker_server.main())
    except KeyboardInterrupt:
        print(">> Stopped.")
        exit_code = 130
    sys.exit(exit_code)
