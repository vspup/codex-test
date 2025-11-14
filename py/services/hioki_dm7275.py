"""Wrapper around :mod:`dm7275` for Worker A."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import serial

from dm7275 import connect_dm7275 as _connect_dm7275
from dm7275 import read_voltage as _read_voltage


@dataclass(slots=True)
class HiokiDM7275:
    """Small adapter providing a stable interface to the DM7275 driver."""

    serial: Optional[serial.Serial]

    def read_voltage(self) -> Optional[float]:
        if not self.serial:
            return None
        return _read_voltage(self.serial)

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()


def connect(port: str, rng: str) -> HiokiDM7275:
    """Return a :class:`HiokiDM7275` connected to the requested port."""
    serial_port = _connect_dm7275(port, rng=rng)
    return HiokiDM7275(serial=serial_port)
