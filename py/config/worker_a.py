"""Configuration loading and validation for the workerA measurement script."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(slots=True)
class WorkerAConfig:
    """Typed container for Worker A runtime configuration."""

    set_voltage: float = 2.0
    set_current: float = 500.0
    stop_current: float = 0.0
    current_drop_threshold: float = 0.2
    current_drop_timeout: float = 60.0

    polling_interval: float = 2.0
    main_mode_timeout: float = 180.0
    retry_delay: float = 1.0
    max_enable_attempts: int = 3
    mode_poll_interval: float = 5.0
    max_valid_op_mode: int = 5
    safe_bus_voltage_threshold: float = 10.0
    current_check_interval: float = 1.0

    hioki_port: str = "/dev/ttyACM0"
    hioki_range: str = "1"

    log_directory: Path = field(default_factory=lambda: Path("./log"))

    def validate(self) -> None:
        """Validate numeric ranges to avoid infinite loops or crashes."""
        numeric_checks = {
            "set_voltage": self.set_voltage,
            "set_current": self.set_current,
            "current_drop_threshold": self.current_drop_threshold,
            "polling_interval": self.polling_interval,
            "main_mode_timeout": self.main_mode_timeout,
            "retry_delay": self.retry_delay,
            "mode_poll_interval": self.mode_poll_interval,
            "safe_bus_voltage_threshold": self.safe_bus_voltage_threshold,
            "current_check_interval": self.current_check_interval,
        }
        for name, value in numeric_checks.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative, got {value!r}")

        if self.max_enable_attempts <= 0:
            raise ValueError("max_enable_attempts must be positive")
        if self.current_drop_timeout < 0:
            raise ValueError("current_drop_timeout must be non-negative")

        if not isinstance(self.hioki_port, str) or not self.hioki_port:
            raise ValueError("hioki_port must be a non-empty string")
        if not isinstance(self.hioki_range, str) or not self.hioki_range:
            raise ValueError("hioki_range must be a non-empty string")

        self.log_directory = Path(self.log_directory)


def load_worker_a_config(overrides: Optional[Dict[str, Any]] = None) -> WorkerAConfig:
    """Return a validated :class:`WorkerAConfig` with optional overrides."""
    overrides = overrides or {}
    config = WorkerAConfig(**overrides)
    config.validate()
    return config
