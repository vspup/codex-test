from __future__ import annotations

import time
import logging

import electabuzz_client as ebc

from config.core import cfg, EB_HOST_LABEL


async def connect_to_device(client: ebc.Client, port: int | None = None) -> bool:
    """Attempt to connect the client using shared configuration settings."""

    target_port = port or cfg.port
    for attempt in range(cfg.max_connect_attempts):
        try:
            ret = await client.connect(
                hostname=cfg.host,
                port=target_port,
                timeout=cfg.connect_timeout_s,
            )
            if ret != 0:
                print(
                    f"Attempt {attempt + 1}: Failed to connect to {EB_HOST_LABEL}"
                )
                logging.error(
                    f"Attempt {attempt + 1}: Failed to connect to {EB_HOST_LABEL}"
                )
                time.sleep(cfg.connect_retry_delay_s)
                # send a request to the EB server to check the communication
                result_code, _ = await client.get_connected_clients()
                if result_code == ebc.EbResult.EB_OK:
                    return True
            print(
                f"Attempt {attempt + 1}: Failed to communicate with {EB_HOST_LABEL}: {result_code}"
            )
            logging.error(
                f"Attempt {attempt + 1}: Failed to communicate with {EB_HOST_LABEL}: {result_code}"
            )
        except Exception as e:
            print(f"Error connecting to {cfg.host}: {e}")
            logging.error(f'Error connecting to {cfg.host}: {e}')

    print(
        f"Failed to connect to {EB_HOST_LABEL} after {cfg.max_connect_attempts} attempts"
    )
    return False

