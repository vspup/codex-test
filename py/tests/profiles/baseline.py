"""Baseline measurement scenario configuration."""
from __future__ import annotations

from config.core import cfg, DEFAULT_PROFILE

PROFILE_NAME = DEFAULT_PROFILE
TARGET_HOST = cfg.host
TARGET_PORT = cfg.port
POLLING_INTERVAL_S = 2.0
MEASUREMENT_DURATION_S = 120.0

__all__ = [
    "PROFILE_NAME",
    "TARGET_HOST",
    "TARGET_PORT",
    "POLLING_INTERVAL_S",
    "MEASUREMENT_DURATION_S",
]
