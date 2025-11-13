#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workerA.py — minimal script that connects to EB client just like id_transmiter.py,
reads 0x3107 (PM Fuse On/Off), and prints result in English.
"""

# === CONFIGURATION ===
SET_VOLTAGE = 2.0  # Напряжение (0x1101), в вольтах
SET_CURRENT = 500.0  # Ток (0x1100), в амперах
STOP_CURRENT = 0.0  # Ток для отключения режима
CURRENT_DROP_THRESHOLD = 0.2  # Порог тока для безопасного отключения, А
CURRENT_DROP_TIMEOUT = 60  # Время ожидания снижения тока, сек

POLLING_INTERVAL = 2.0  # Интервал опроса, сек
MAIN_MODE_TIMEOUT = 180.0  # Таймаут включения/выключения Main Mode, сек
RETRY_DELAY = 1.0  # Задержка между повторными попытками, сек
MAX_ENABLE_ATTEMPTS = 3  # Максимальное количество попыток включить PM Fuse
MODE_POLL_INTERVAL = 5.0  # Интервал проверки режима Main Mode, сек
MAX_VALID_OP_MODE = 5  # Максимально допустимый код режима
SAFE_BUS_VOLTAGE_THRESHOLD = 10.0  # Порог безопасного напряжения шины, В
CURRENT_CHECK_INTERVAL = 1.0  # Интервал проверки тока при выключении, сек

HIOKI_PORT = "/dev/ttyACM0" # Последовательный порт Hioki DM7275
HIOKI_RANGE = "1" # Диапазон измерения Hioki DM7275 (например, AUTO или 0.1)

# === END CONFIG ===

import sys
import asyncio
import electabuzz_client as ebc
from constants import cfg
from network_utils import connect_to_device
from datapoint_mapping import DATA_POINT_MAPPING
from typing import Optional
import signal
import serial
import csv
from datetime import datetime
from pathlib import Path
import time

from dm7275 import connect_dm7275, read_voltage


from electabuzz_client import EB_TYPE_BOOL
from electabuzz_client import EB_TYPE_UINT32
from electabuzz_client import EB_TYPE_DOUBLE


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

# graceful cancel flag
stop_requested = False

def request_stop(signum, frame):
    global stop_requested
    stop_requested = True
    print("\n>> Measurement interrupted. Proceeding with safe shutdown...")


def format_row(currents, voltage, dm7275_v=None, elapsed_s=0.0):
    i_parts = [f"{i:+.3f}" for i in currents]
    total = sum(abs(i) for i in currents)
    u_str = f"{voltage:6.3f}"
    dm_str = f"{dm7275_v:6.3f}" if isinstance(dm7275_v, (int, float)) else "  ---"
    time_str = f"{elapsed_s:5.1f}"
    return f"{time_str} | {' '.join(i_parts)} | {total:6.3f} | {u_str} | {dm_str}"


async def polling_loop(client: ebc.Client, hioki: serial.Serial | None, interval: float = POLLING_INTERVAL):
    print(">> Starting measurement loop. Press Ctrl+C to stop.")
    global stop_requested
    stop_requested = False
    iteration = 0

    # Time anchor
    start_time = time.time()

    # --- Prepare CSV logger ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(f"./log/log_{timestamp}.csv")
    csv_file = log_path.open("w", newline="")
    writer = csv.writer(csv_file)
    header = [
        "timestamp",
        "elapsed_s",
        *[f"I{i+1}" for i in range(8)],
        "I_sum",
        "U_term",
        "U_dm",
        *[f"T1_{i+1}" for i in range(8)],
        *[f"T2_{i+1}" for i in range(8)],
    ]
    writer.writerow(header)
    print(f">> Logging to {log_path}\n")

    # --- Print table header ---
    print(" Time | I1     I2     I3     I4     I5     I6     I7     I8    |  Sum   |   U    |  DM7275")
    print("-" * 93)

    try:
        while not stop_requested:
            # Elapsed time since start
            elapsed = time.time() - start_time
            t_display = f"{elapsed:5.1f}"

            # Read data points
            currents = await read_datapoint(client, DP_CURRENT)
            voltage = await read_datapoint(client, DP_VOLTAGE)
            temps1 = await read_datapoint(client, DP_T1)
            temps2 = await read_datapoint(client, DP_T2)
            dm_v = read_voltage(hioki) if hioki else None

            if all(isinstance(x, list) for x in (currents, temps1, temps2)) and isinstance(voltage, (int, float)):
                # 1️⃣ Line 1 — currents + voltages
                sum_current = sum(abs(i) for i in currents)
                line1 = t_display + " | " + " ".join(f"{i:+.3f}" for i in currents)
                line1 += f" | {sum_current:6.3f} | {voltage:6.3f} | {dm_v:7.5f}" if dm_v is not None else f" | {sum_current:6.3f} | {voltage:6.3f} |   ---"
                print(line1)

                # 2️⃣ Line 2 — T1
                line2 = " " * 6 + " " + " ".join(f"{t:5.1f}" for t in temps1) + " |  T1"
                print(line2)

                # 3️⃣ Line 3 — T2
                line3 = " " * 6 + " " + " ".join(f"{t:5.1f}" for t in temps2) + " |  T2"
                print(line3)

                # 🔄 CSV log
                writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    round(elapsed, 2),
                    *currents,
                    sum_current,
                    voltage,
                    dm_v if dm_v is not None else "",
                    *temps1,
                    *temps2
                ])
            else:
                print("!! Failed to read one or more datapoints (1000, 1002, 6001, 6002)")

            next_ts = start_time + (iteration + 1) * interval
            sleep_time = max(0.0, next_ts - time.time())
            await asyncio.sleep(sleep_time)
            iteration += 1

    except KeyboardInterrupt:
        print("\n>> Measurement interrupted. Proceeding with safe shutdown...")
    finally:
        csv_file.close()
        print(f">> Log file saved: {log_path}")


async def connect() -> Optional[ebc.Client]:
    """Creates and connects the EB client. Returns client or None if failed."""
    client = ebc.Client()
    print(f">> Connecting to {cfg.host}:{cfg.port} using connect_to_device()...")
    if not await connect_to_device(client, cfg.port):
        print("!! Failed to connect.")
        return None
    print(">> Connected.")
    return client


def format_pm_fuse(val) -> str:
    """Formats the value of the PM Fuse datapoint into human-readable output."""
    name = DATA_POINT_MAPPING.get("0x3107", {}).get("name", "PM Fuse On/Off")
    if isinstance(val, list):
        channel_bits = " ".join("1" if x else "0" for x in val)
        status = "ON" if all(val) else "OFF"
        return f">> Power modules: [{channel_bits}]\n>> Status: {status}"
    elif isinstance(val, bool):
        return f"{name}: {'ON' if val else 'OFF'}"
    else:
        return f"{name}: {val!r}"


async def read_datapoint(client: ebc.Client, dp_id: int) -> Optional[any]:
    """Reads a single datapoint and returns its 'value', or None."""
    try:
        result = await client.multi_read([dp_id])
        if dp_id in result:
            return result[dp_id].get("value")
    except Exception as e:
        print(f"!! Failed to read 0x{dp_id:04X}: {e}")
    return None


async def enable_all_pm_modules(client: ebc.Client) -> bool:
    """Sends [True]*8 to 0x3107 to enable all PM modules."""
    try:
        result = await client.single_write(DP_PM_FUSE, [True] * 8, EB_TYPE_BOOL)
        if result == ebc.EbResult.EB_OK:
            print(">> Sent enable command to all PM modules via 0x3107.")
            return True
        else:
            print(f"!! Write to 0x3107 failed with result code: {result}")
            return False
    except Exception as e:
        print(f"!! Exception during write to 0x3107: {e}")
        return False


async def switch_main_mode(client: ebc.Client, target_mode: int, timeout: float = MAIN_MODE_TIMEOUT) -> bool:
    """
    Sets main power mode via 0x2000 = target_mode,
    then waits for 0x2001 to reflect the change.

    target_mode: 1 = ON, 0 = OFF
    """
    assert target_mode in (0, 1), "target_mode must be 0 or 1"

    try:
        print(f">> Sending command: w 0x{DP_REQ_MODE:04X} {target_mode}")
        result = await client.single_write(DP_REQ_MODE, target_mode, EB_TYPE_UINT32)
        if result != ebc.EbResult.EB_OK:
            print(f"!! Failed to write to {DP_REQ_MODE}. Code: {result}")
            return False
    except Exception as e:
        print(f"!! Exception while writing to {DP_REQ_MODE}: {e}")
        return False

    print(f">> Waiting for mode confirmation in 0x{DP_OP_MODE:04X} == {target_mode}...")
    poll_interval = MODE_POLL_INTERVAL
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
        elif isinstance(actual_mode, int) and actual_mode > MAX_VALID_OP_MODE:
            print(
                f"!! Error: 0x{DP_OP_MODE:04X} = {actual_mode} (> {MAX_VALID_OP_MODE}). Aborting."
            )
            return False

    print(f"!! Timeout: 0x{DP_OP_MODE:04X} did not become {target_mode} within {int(timeout)} seconds.")
    return False


def format_three_lines(currents, voltage, dm7275, temps1, temps2):
    sum_current = sum(abs(i) for i in currents)
    line1 = " ".join(f"{i:.3f}".rjust(6) for i in currents) + f" | {sum_current:6.3f} | {voltage:5.3f} | {dm7275:6.3f}" if dm7275 is not None else "  --"
    line2 = " ".join(f"{t:.1f}".rjust(6) for t in temps1) + " |  T1"
    line3 = " ".join(f"{t:.1f}".rjust(6) for t in temps2) + " |  T2"
    return line1, line2, line3



async def main():
    signal.signal(signal.SIGINT, request_stop)

    client = await connect()
    if not client:
        return 1

    # Try to connect to DM7275
    try:
        print(">> Connecting to Hioki DM7275...")
        hioki = connect_dm7275(HIOKI_PORT, rng=HIOKI_RANGE)
        v = read_voltage(hioki)
        if v is not None:
            print(f">> Hioki DM7275: {v:.6f} V")
        else:
            print("!! Failed to read voltage from Hioki DM7275.")
    except Exception as e:
        hioki = None
        print(f"!! Could not initialize Hioki DM7275: {e}")



    bus_voltage = await read_datapoint(client, DP_BUS_VOLTAGE)
    if bus_voltage is None:
        print("!! Failed to read Filtered Bus Voltage (0x1001).")
        return 2
    print(f">> Filtered Bus Voltage (0x1001): {bus_voltage:.5f}" if isinstance(bus_voltage, float) else f"Filtered Bus Voltage: {bus_voltage!r}")

    op_mode = await read_datapoint(client, DP_OP_MODE)
    if op_mode is None:
        print("!! Failed to read Current Operating Mode (0x2000).")
        return 2
    print(f">> Current Operating Mode (0x2000): {op_mode}")

    # Check conditions
    if (
        isinstance(bus_voltage, (int, float))
        and bus_voltage > SAFE_BUS_VOLTAGE_THRESHOLD
    ):
        print(
            ">>> Skipped reading 0x3107: "
            f"Filtered Bus Voltage = {bus_voltage:.5f} V > {SAFE_BUS_VOLTAGE_THRESHOLD:.0f} V."
        )
        client.close()
        return 0

    if op_mode != 0:
        print(f">>> Skipped reading 0x3107: Current Operating Mode = {op_mode} (must be 0).")
        client.close()
        return 0

    # PM Fuse enable
    val = await read_datapoint(client, DP_PM_FUSE)
    if val is None:
        print("!! Failed to read PM Fuse state (datapoint 0x3107).")
        return 3

    print(format_pm_fuse(val))

    if not (isinstance(val, list) and all(val)):
        print(">> Some PM modules are OFF. Attempting to enable...")

        for attempt in range(1, MAX_ENABLE_ATTEMPTS + 1):  # Attempts 1 to MAX
            print(f">> Enable attempt {attempt}...")
            success = await enable_all_pm_modules(client)

            await asyncio.sleep(RETRY_DELAY)
            val = await read_datapoint(client, DP_PM_FUSE)
            if val is None:
                print("!! Failed to read PM Fuse state after write.")
                return 3

            print(format_pm_fuse(val))

            if isinstance(val, list) and all(val):
                print(
                    f">> All PM modules successfully enabled on attempt {attempt}."
                )
                break
        else:
            print(
                f"!! Failed to enable all PM modules after {MAX_ENABLE_ATTEMPTS} attempts."
            )
            return 4



    # Если все силовые модули включены → включаем питание
    if isinstance(val, list) and all(val):
        power_result = await switch_main_mode(client, target_mode=1)
        if not power_result:
            print("Failed to enable power.")
            return 5

    await client.single_write(DP_SET_VOLTAGE, SET_VOLTAGE, EB_TYPE_DOUBLE)
    await client.single_write(DP_SET_CURRENT, SET_CURRENT, EB_TYPE_DOUBLE)
    print(f">> Set voltage = {SET_VOLTAGE} V (0x1101), current = {SET_CURRENT} A (0x1100)")



    await polling_loop(client, hioki, interval=POLLING_INTERVAL)

    print(f">> Setting current to {STOP_CURRENT} A (0x{DP_SET_CURRENT:04X})...")
    await client.single_write(DP_SET_CURRENT, STOP_CURRENT, EB_TYPE_DOUBLE)

    print(f">> Waiting for total current to drop below {CURRENT_DROP_THRESHOLD} A...")
    for i in range(int(CURRENT_DROP_TIMEOUT)):
        currents = await read_datapoint(client, DP_CURRENT)
        if isinstance(currents, list):
            total = sum(abs(i) for i in currents)
            print(f"  Total current: {total:.3f} A")
            if total <= CURRENT_DROP_THRESHOLD:
                print(f">> Current dropped below {CURRENT_DROP_THRESHOLD} A.")
                break
        await asyncio.sleep(CURRENT_CHECK_INTERVAL)
    else:
        print(
            f"!! Timeout: Current did not drop below {CURRENT_DROP_THRESHOLD} A"
        )

    print(">> Switching off main mode...")
    await switch_main_mode(client, 0)

    if hioki:
        hioki.close()

    client.close()
    return 0



if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        exit_code = 130
    sys.exit(exit_code)
