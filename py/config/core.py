"""Core configuration for Electabuzz tools.

This module centralises network addresses, connection timeouts and
shared constants that are used by utility scripts and test profiles.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final


def _get_env(name: str, default: str) -> str:
    """Return environment value for ``name`` or ``default`` when empty."""
    return os.environ.get(name, default)


def _get_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class ElectabuzzConfig:
    """Runtime configuration shared by Electabuzz scripts."""

    host: str = _get_env("EB_HOST", "mps.local")
    port: int = _get_env_int("EB_PORT", 5554)
    recv_timeout_ms: int = _get_env_int("EB_RECV_TIMEOUT_MS", 500)

    max_connect_attempts: int = _get_env_int("EB_MAX_CONNECT_ATTEMPTS", 3)
    connect_retry_delay_s: float = _get_env_float("EB_CONNECT_RETRY_DELAY", 0.5)
    connect_timeout_s: float = _get_env_float("EB_CONNECT_TIMEOUT", 3.0)

    profile_dir: str = "py/tests/profiles"


cfg: Final[ElectabuzzConfig] = ElectabuzzConfig()
EB_HOST_LABEL: Final[str] = f"{cfg.host}:{cfg.port}"
DEFAULT_PROFILE: Final[str] = "baseline"
"""Default profile name used by CLI helpers."""

__all__ = ["cfg", "EB_HOST_LABEL", "DEFAULT_PROFILE", "ElectabuzzConfig"]
