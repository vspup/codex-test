#!/usr/bin/env python3
"""CLI entry point for the Electabuzz TCP measurement broker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ is None or __package__ == "":  # pragma: no cover - runtime execution path
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from py.constants import cfg
from py.services import TcpMeasurementBroker, UdpElectabuzzGateway


async def main() -> None:
    print(f">> Connecting to controller {cfg.host}:{cfg.port} ...")
    gateway = UdpElectabuzzGateway()
    await gateway.connect(cfg.host, cfg.port, recv_timeout_ms=cfg.recv_timeout_ms)
    print(f">> Connected to {cfg.host}:{cfg.port}")

    broker = TcpMeasurementBroker(gateway)
    try:
        await broker.start()
    finally:
        gateway.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(">> Stopped.")
