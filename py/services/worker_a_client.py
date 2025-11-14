"""Client helpers for the Worker A measurement script."""
from __future__ import annotations

import asyncio
from typing import Iterable, Optional

import electabuzz_client as ebc
from constants import cfg
from datapoint_mapping import DATA_POINT_MAPPING
from electabuzz_client import EB_TYPE_BOOL, EB_TYPE_UINT32

from network_utils import connect_to_device

# Datapoint identifiers used by the worker script
DP_PM_FUSE = 0x3107
DP_BUS_VOLTAGE = 0x1001
DP_OP_MODE = 0x2000
DP_REQ_MODE = 0x2001
DP_SET_CURRENT = 0x1100
DP_SET_VOLTAGE = 0x1101
DP_CURRENT = 0x1000
DP_VOLTAGE = 0x1002
DP_T1 = 0x6001
DP_T2 = 0x6002


async def connect() -> Optional[ebc.Client]:
    """Connect to the Electabuzz device and return the client on success."""
    client = ebc.Client()
    print(f">> Connecting to {cfg.host}:{cfg.port} using connect_to_device()...")
    if not await connect_to_device(client, cfg.port):
        print("!! Failed to connect.")
        return None
    print(">> Connected.")
    return client


async def read_datapoint(client: ebc.Client, dp_id: int) -> Optional[object]:
    """Return the value of a single datapoint or ``None`` on failure."""
    try:
        result = await client.multi_read([dp_id])
        if dp_id in result:
            return result[dp_id].get("value")
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"!! Failed to read 0x{dp_id:04X}: {exc}")
    return None


async def enable_all_pm_modules(client: ebc.Client) -> bool:
    """Set the PM fuse datapoint to ``[True] * 8``."""
    try:
        result = await client.single_write(DP_PM_FUSE, [True] * 8, EB_TYPE_BOOL)
        if result == ebc.EbResult.EB_OK:
            print(">> Sent enable command to all PM modules via 0x3107.")
            return True
        print(f"!! Write to 0x3107 failed with result code: {result}")
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"!! Exception during write to 0x3107: {exc}")
    return False


async def switch_main_mode(
    client: ebc.Client,
    target_mode: int,
    *,
    timeout: float,
    poll_interval: float,
    max_valid_op_mode: int,
) -> bool:
    """Request the main mode change and wait until it is reflected by the device."""
    assert target_mode in (0, 1), "target_mode must be 0 or 1"

    try:
        print(f">> Sending command: w 0x{DP_REQ_MODE:04X} {target_mode}")
        result = await client.single_write(DP_REQ_MODE, target_mode, EB_TYPE_UINT32)
        if result != ebc.EbResult.EB_OK:
            print(f"!! Failed to write to {DP_REQ_MODE}. Code: {result}")
            return False
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"!! Exception while writing to {DP_REQ_MODE}: {exc}")
        return False

    print(f">> Waiting for mode confirmation in 0x{DP_OP_MODE:04X} == {target_mode}...")
    elapsed = 0.0

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        actual_mode = await read_datapoint(client, DP_OP_MODE)
        if actual_mode is None:
            print(f">>\t0x{DP_OP_MODE:04X} = {actual_mode} at {elapsed:.0f}s")
            continue

        print(f"\t 0x{DP_OP_MODE:04X} = {actual_mode} at {elapsed:.0f}s")

        if actual_mode == target_mode:
            print(f">> Main mode successfully set to {target_mode}.")
            return True
        if isinstance(actual_mode, int) and actual_mode > max_valid_op_mode:
            print(
                f"!! Error: 0x{DP_OP_MODE:04X} = {actual_mode} (> {max_valid_op_mode}). Aborting."
            )
            return False

    print(
        f"!! Timeout: 0x{DP_OP_MODE:04X} did not become {target_mode} within {int(timeout)} seconds."
    )
    return False


def format_pm_fuse(value: object) -> str:
    """Return a human readable description of the PM fuse state."""
    name = DATA_POINT_MAPPING.get("0x3107", {}).get("name", "PM Fuse On/Off")
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        bits = " ".join("1" if bool(x) else "0" for x in value)
        status = "ON" if all(bool(x) for x in value) else "OFF"
        return f">> Power modules: [{bits}]\n>> Status: {status}"
    if isinstance(value, bool):
        return f"{name}: {'ON' if value else 'OFF'}"
    return f"{name}: {value!r}"


def format_currents_line(currents: Iterable[float]) -> str:
    """Format a sequence of currents for console output."""
    return " ".join(f"{current:+.3f}" for current in currents)


def format_temperature_line(label: str, values: Iterable[float]) -> str:
    """Format a temperature row for console output."""
    return " " * 6 + " " + " ".join(f"{temp:5.1f}" for temp in values) + f" |  {label}"
