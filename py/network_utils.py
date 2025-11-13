import time
import logging
import electabuzz_client as ebc
from constants import cfg


async def connect_to_device(client : ebc.Client, port : int = 5554) -> bool:
    max_connect_attempts = 3
    for attempt in range(max_connect_attempts):
        try:
            ret = await client.connect(hostname=cfg.host, port=port)
            if ret != 0:
                print(f'Attempt {attempt + 1}: Failed to connect to {EB_HOST_NAME}')
                logging.error(f'Attempt {attempt + 1}: Failed to connect to {EB_HOST_NAME}')
                time.sleep(0.5)
            # send a request to the EB server to check the communication
            result_code, _ = await client.get_connected_clients()
            if result_code == ebc.EbResult.EB_OK:
                return True
            print(f'Attempt {attempt + 1}: Failed to communicate with {EB_HOST_NAME}: {result_code}')
            logging.error(f'Attempt {attempt + 1}: Failed to communicate with {EB_HOST_NAME}: {result_code}')
        except Exception as e:
            print(f"Error connecting to {cfg.host}: {e}")
            logging.error(f'Error connecting to {cfg.host}: {e}')
    
    print(f'Failed to connect to {EB_HOST_NAME} after {max_connect_attempts} attempts')
    return False

