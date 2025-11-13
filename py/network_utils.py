"""Compatibility wrapper for :mod:`py.core.network_utils`."""

from .core.network_utils import *  # noqa: F401,F403
from .core.network_utils import connect_to_device

__all__ = ["connect_to_device"]
