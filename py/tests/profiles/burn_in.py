"""Burn-in scenario configuration for extended runs."""
from __future__ import annotations

from config.core import cfg

PROFILE_NAME = "burn_in"
TARGET_HOST = cfg.host
TARGET_PORT = cfg.port
POLLING_INTERVAL_S = 5.0
MEASUREMENT_DURATION_S = 3600.0
TARGET_TEMPERATURE_C = 55.0

__all__ = [
    "PROFILE_NAME",
    "TARGET_HOST",
    "TARGET_PORT",
    "POLLING_INTERVAL_S",
    "MEASUREMENT_DURATION_S",
    "TARGET_TEMPERATURE_C",
]
