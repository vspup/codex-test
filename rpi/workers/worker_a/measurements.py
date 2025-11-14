"""Measurement loop and logging for Worker A running on Raspberry Pi."""
from __future__ import annotations

import asyncio
import csv
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

import electabuzz_client as ebc

from rpi.workers.worker_a.config import WorkerAConfig
from rpi.service.worker_a_client import (
    DP_CURRENT,
    DP_T1,
    DP_T2,
    DP_VOLTAGE,
    format_currents_line,
    format_temperature_line,
    read_datapoint,
)


class VoltageReader(Protocol):
    """Minimal protocol for the Hioki adapter used in measurements."""

    def read_voltage(self) -> Optional[float]:  # pragma: no cover - protocol definition
        ...


@dataclass(slots=True)
class MeasurementResult:
    """Value object describing the measurement session output."""

    log_path: Path


async def run_measurements(
    client: ebc.Client,
    config: WorkerAConfig,
    *,
    hioki: Optional[VoltageReader] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> MeasurementResult:
    """Run the measurement loop and return the path to the CSV log."""
    stop_event = stop_event or asyncio.Event()

    print(">> Starting measurement loop. Press Ctrl+C to stop.")
    start_time = time.time()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config.log_directory.mkdir(parents=True, exist_ok=True)
    log_path = config.log_directory / f"log_{timestamp}.csv"

    with log_path.open("w", newline="") as csv_file:
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

        print(
            " Time | I1     I2     I3     I4     I5     I6     I7     I8    |  Sum   |   U    |  DM7275"
        )
        print("-" * 93)

        iteration = 0
        try:
            while not stop_event.is_set():
                elapsed = time.time() - start_time

                currents = await read_datapoint(client, DP_CURRENT)
                voltage = await read_datapoint(client, DP_VOLTAGE)
                temps1 = await read_datapoint(client, DP_T1)
                temps2 = await read_datapoint(client, DP_T2)
                dm_voltage = hioki.read_voltage() if hioki else None

                if all(isinstance(x, list) for x in (currents, temps1, temps2)) and isinstance(
                    voltage, (int, float)
                ):
                    total_current = sum(abs(i) for i in currents)
                    time_str = f"{elapsed:5.1f}"
                    if dm_voltage is not None:
                        line1 = (
                            f"{time_str} | {format_currents_line(currents)} | {total_current:6.3f} "
                            f"| {voltage:6.3f} | {dm_voltage:7.5f}"
                        )
                    else:
                        line1 = (
                            f"{time_str} | {format_currents_line(currents)} | {total_current:6.3f} "
                            f"| {voltage:6.3f} |   ---"
                        )
                    print(line1)
                    print(format_temperature_line("T1", temps1))
                    print(format_temperature_line("T2", temps2))

                    writer.writerow(
                        [
                            datetime.now().isoformat(timespec="seconds"),
                            round(elapsed, 2),
                            *currents,
                            total_current,
                            voltage,
                            dm_voltage if dm_voltage is not None else "",
                            *temps1,
                            *temps2,
                        ]
                    )
                else:
                    print("!! Failed to read one or more datapoints (1000, 1002, 6001, 6002)")

                iteration += 1
                next_ts = start_time + (iteration * config.polling_interval)
                await asyncio.sleep(max(0.0, next_ts - time.time()))
        finally:
            print(f">> Log file saved: {log_path}")

    return MeasurementResult(log_path=log_path)
