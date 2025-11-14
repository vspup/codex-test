#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for Worker A measurements."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import Optional

import electabuzz_client as ebc
from electabuzz_client import EB_TYPE_DOUBLE

from config.worker_a import WorkerAConfig, load_worker_a_config
from services import worker_a_client
from services.hioki_dm7275 import HiokiDM7275, connect as connect_hioki
from services.worker_a_client import (
    DP_BUS_VOLTAGE,
    DP_CURRENT,
    DP_OP_MODE,
    DP_PM_FUSE,
    DP_SET_CURRENT,
    DP_SET_VOLTAGE,
    enable_all_pm_modules,
    format_pm_fuse,
    read_datapoint,
    switch_main_mode,
)
from services.worker_a_measurements import run_measurements


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker A measurement utility")
    parser.add_argument(
        "--hioki-port",
        help="Override Hioki DM7275 serial port",
    )
    parser.add_argument(
        "--hioki-range",
        help="Override Hioki DM7275 range (AUTO or numeric value)",
    )
    return parser.parse_args(argv)


async def _initialise_hioki(config: WorkerAConfig) -> Optional[HiokiDM7275]:
    try:
        print(">> Connecting to Hioki DM7275...")
        hioki = connect_hioki(config.hioki_port, config.hioki_range)
        voltage = hioki.read_voltage()
        if voltage is not None:
            print(f">> Hioki DM7275: {voltage:.6f} V")
        else:
            print("!! Failed to read voltage from Hioki DM7275.")
        return hioki
    except Exception as exc:
        print(f"!! Could not initialize Hioki DM7275: {exc}")
        return None


async def _wait_for_current_drop(client: ebc.Client, config: WorkerAConfig) -> None:
    for _ in range(int(config.current_drop_timeout)):
        currents = await read_datapoint(client, DP_CURRENT)
        if isinstance(currents, list):
            total = sum(abs(i) for i in currents)
            print(f"  Total current: {total:.3f} A")
            if total <= config.current_drop_threshold:
                print(f">> Current dropped below {config.current_drop_threshold} A.")
                break
        await asyncio.sleep(config.current_check_interval)
    else:
        print(
            f"!! Timeout: Current did not drop below {config.current_drop_threshold} A"
        )


async def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = _parse_args(argv)

    overrides = {}
    if args.hioki_port:
        overrides["hioki_port"] = args.hioki_port
    if args.hioki_range:
        overrides["hioki_range"] = args.hioki_range

    try:
        config = load_worker_a_config(overrides)
    except ValueError as exc:
        print(f"Invalid configuration: {exc}")
        return 1

    stop_event = asyncio.Event()

    def handle_stop(signum, frame) -> None:  # pragma: no cover - signal handler
        stop_event.set()
        print("\n>> Measurement interrupted. Proceeding with safe shutdown...")

    signal.signal(signal.SIGINT, handle_stop)

    client = await worker_a_client.connect()
    if not client:
        return 1

    hioki: Optional[HiokiDM7275] = await _initialise_hioki(config)

    bus_voltage = await read_datapoint(client, DP_BUS_VOLTAGE)
    if bus_voltage is None:
        print("!! Failed to read Filtered Bus Voltage (0x1001).")
        client.close()
        return 2
    if isinstance(bus_voltage, float):
        print(f">> Filtered Bus Voltage (0x1001): {bus_voltage:.5f}")
    else:
        print(f"Filtered Bus Voltage: {bus_voltage!r}")

    op_mode = await read_datapoint(client, DP_OP_MODE)
    if op_mode is None:
        print("!! Failed to read Current Operating Mode (0x2000).")
        client.close()
        return 2
    print(f">> Current Operating Mode (0x2000): {op_mode}")

    if (
        isinstance(bus_voltage, (int, float))
        and bus_voltage > config.safe_bus_voltage_threshold
    ):
        print(
            ">>> Skipped reading 0x3107: "
            f"Filtered Bus Voltage = {bus_voltage:.5f} V > {config.safe_bus_voltage_threshold:.0f} V."
        )
        client.close()
        if hioki:
            hioki.close()
        return 0

    if op_mode != 0:
        print(f">>> Skipped reading 0x3107: Current Operating Mode = {op_mode} (must be 0).")
        client.close()
        if hioki:
            hioki.close()
        return 0

    pm_value = await read_datapoint(client, DP_PM_FUSE)
    if pm_value is None:
        print("!! Failed to read PM Fuse state (datapoint 0x3107).")
        client.close()
        if hioki:
            hioki.close()
        return 3

    print(format_pm_fuse(pm_value))

    if not (isinstance(pm_value, list) and all(pm_value)):
        print(">> Some PM modules are OFF. Attempting to enable...")
        for attempt in range(1, config.max_enable_attempts + 1):
            print(f">> Enable attempt {attempt}...")
            await enable_all_pm_modules(client)
            await asyncio.sleep(config.retry_delay)
            pm_value = await read_datapoint(client, DP_PM_FUSE)
            if pm_value is None:
                print("!! Failed to read PM Fuse state after write.")
                client.close()
                if hioki:
                    hioki.close()
                return 3
            print(format_pm_fuse(pm_value))
            if isinstance(pm_value, list) and all(pm_value):
                print(f">> All PM modules successfully enabled on attempt {attempt}.")
                break
        else:
            print(
                f"!! Failed to enable all PM modules after {config.max_enable_attempts} attempts."
            )
            client.close()
            if hioki:
                hioki.close()
            return 4

    if isinstance(pm_value, list) and all(pm_value):
        power_on = await switch_main_mode(
            client,
            target_mode=1,
            timeout=config.main_mode_timeout,
            poll_interval=config.mode_poll_interval,
            max_valid_op_mode=config.max_valid_op_mode,
        )
        if not power_on:
            print("Failed to enable power.")
            client.close()
            if hioki:
                hioki.close()
            return 5

    await client.single_write(DP_SET_VOLTAGE, config.set_voltage, EB_TYPE_DOUBLE)
    await client.single_write(DP_SET_CURRENT, config.set_current, EB_TYPE_DOUBLE)
    print(
        f">> Set voltage = {config.set_voltage} V (0x1101), current = {config.set_current} A (0x1100)"
    )

    await run_measurements(client, config, hioki=hioki, stop_event=stop_event)

    print(f">> Setting current to {config.stop_current} A (0x{DP_SET_CURRENT:04X})...")
    await client.single_write(DP_SET_CURRENT, config.stop_current, EB_TYPE_DOUBLE)

    print(
        f">> Waiting for total current to drop below {config.current_drop_threshold} A..."
    )
    await _wait_for_current_drop(client, config)

    print(">> Switching off main mode...")
    await switch_main_mode(
        client,
        target_mode=0,
        timeout=config.main_mode_timeout,
        poll_interval=config.mode_poll_interval,
        max_valid_op_mode=config.max_valid_op_mode,
    )

    if hioki:
        hioki.close()
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
