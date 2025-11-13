"""Utilities for connecting to the Electabuzz controller."""

from __future__ import annotations

import logging
import time

from . import electabuzz_client as ebc
from .constants import cfg


async def connect_to_device(client: ebc.Client, port: int = 5554) -> bool:
    """Attempt to connect a client to the configured Electabuzz host.

    Retries a few times and validates the connection by performing a
    ``get_connected_clients`` call.
    """

    max_connect_attempts = 3
    host = cfg.host

    for attempt in range(max_connect_attempts):
        try:
            ret = await client.connect(hostname=host, port=port)
            if ret != 0:
                print(f"Attempt {attempt + 1}: Failed to connect to {host}")
                logging.error("Attempt %s: Failed to connect to %s", attempt + 1, host)
                time.sleep(0.5)
                continue

            # Send a request to the EB server to check the communication
            result_code, _ = await client.get_connected_clients()
            if result_code == ebc.EbResult.EB_OK:
                return True

            print(
                f"Attempt {attempt + 1}: Failed to communicate with {host}: {result_code}"
            )
            logging.error(
                "Attempt %s: Failed to communicate with %s: %s",
                attempt + 1,
                host,
                result_code,
            )
        except Exception as exc:  # pylint: disable=broad-except
            # Keep behaviour consistent with previous version by logging and retrying.
            print(f"Error connecting to {host}: {exc}")
            logging.error("Error connecting to %s: %s", host, exc)

    print(f"Failed to connect to {host} after {max_connect_attempts} attempts")
    return False
