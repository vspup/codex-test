#!/usr/bin/env python3
import asyncio
import electabuzz_client as ebc
from constants import cfg
from network_utils import connect_to_device
from datapoint_mapping import DATA_POINT_MAPPING
from electabuzz_client import *

import readline, os, atexit

HISTORY_FILE = os.path.expanduser("~/.id_transmiter_history")
if os.path.exists(HISTORY_FILE):
    readline.read_history_file(HISTORY_FILE)
atexit.register(lambda: readline.write_history_file(HISTORY_FILE))

COMMANDS = ['r', 'w', 'exit']
POINTS = list(DATA_POINT_MAPPING.keys())


def completer(text, state):
    buffer = readline.get_line_buffer().strip().split()
    options = []
    if len(buffer) == 0:
        options = COMMANDS
    elif len(buffer) == 1:
        options = [cmd for cmd in COMMANDS if cmd.startswith(text)]
    elif len(buffer) == 2 and buffer[0] in ('r', 'w'):
        prefix = f'0x{text.lower()}'
        matches = [pt for pt in POINTS if pt.startswith(prefix)]
        options = [f"{pt[2:]} [{DATA_POINT_MAPPING[pt]['name']}]" if 'name' in DATA_POINT_MAPPING[pt] else pt[2:] for pt
                   in matches]
    try:
        return options[state]
    except IndexError:
        return None


readline.set_completer(completer)
readline.parse_and_bind('tab: complete')

TYPE_MAP = {
    'EB_TYPE_FLOAT': EB_TYPE_FLOAT,
    'EB_TYPE_DOUBLE': EB_TYPE_DOUBLE,
    'EB_TYPE_UINT16': EB_TYPE_UINT16,
    'EB_TYPE_UINT32': EB_TYPE_UINT32,
    'EB_TYPE_INT32': EB_TYPE_INT32,
    'EB_TYPE_INT8': EB_TYPE_INT8,
    'EB_TYPE_BOOL': EB_TYPE_BOOL,
    'EB_TYPE_UNKOWN': EB_TYPE_UNKOWN,
}


async def read_point(client, hex_id):
    try:
        dp_id = int(hex_id, 16)
        result = await client.multi_read([dp_id])
        if not result or dp_id not in result:
            print(f"❌ {hex_id} not found or no response.")
        else:
            dp_data = result[dp_id]
            name = DATA_POINT_MAPPING.get(f"0x{dp_id:04x}", {}).get("name", "Unnamed")
            val = dp_data.get('value')

            # Apply formatting: if it's float, format to 5 decimals
            if isinstance(val, float):
                val_str = f"{val:.5f}"
            elif isinstance(val, list) and all(isinstance(v, float) for v in val):
                val_str = "[" + ", ".join(f"{v:.5f}" for v in val) + "]"
            else:
                val_str = str(val)

            print(f"  {hex_id.upper()} [{name}] = {val_str}")
    except Exception as e:
        print(f"❌ Read error: {e}")


async def write_point(client, hex_id, values):
    try:
        dp_id = int(hex_id, 16)
        point = f"0x{dp_id:04x}"
        type_str = DATA_POINT_MAPPING.get(point, {}).get("type", "EB_TYPE_FLOAT")
        eb_type = TYPE_MAP.get(type_str, EB_TYPE_UNKOWN)

        # 🟢 Proper type handling
        if type_str == 'EB_TYPE_BOOL':
            def to_bool(v):
                s = str(v).strip().lower()
                return s in ('1', 'true', 'yes', 'on')

            value = to_bool(values[0]) if len(values) == 1 else [to_bool(v) for v in values]
        elif type_str in ['EB_TYPE_UINT32', 'EB_TYPE_UINT16', 'EB_TYPE_INT32', 'EB_TYPE_INT8']:
            value = int(values[0]) if len(values) == 1 else [int(v) for v in values]
        else:
            value = float(values[0]) if len(values) == 1 else [float(v) for v in values]

        result = await client.single_write(dp_id, value, eb_type)

        if result == ebc.EbResult.EB_OK:
            print(f"  ✅ Wrote to {hex_id.upper()}: {value}")
        else:
            print(f"  ❌ Write failed for {hex_id.upper()} → Code {result}")
    except Exception as e:
        print(f"❌ Write error: {e}")


async def cli_loop(client):
    while True:
        try:
            line = input(">> ").strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                print("Bye.")
                break
            parts = line.split()
            cmd = parts[0].lower()
            if cmd == "r" and len(parts) == 2:
                await read_point(client, parts[1])
            elif cmd == "w" and len(parts) >= 3:
                await write_point(client, parts[1], parts[2:])
            else:
                print("Usage:\n  r <hex>         read\n  w <hex> <val>   write")
        except KeyboardInterrupt:
            print("\nStopped.")
            break


async def main():
    client = ebc.Client()
    if await connect_to_device(client, cfg.port):
        try:
            print(f">> Connected to {cfg.host}:{cfg.port}. Type 'r' or 'w'.")
            await cli_loop(client)
        finally:
            client.close()
    else:
        print("❌ Failed to connect.")


if __name__ == "__main__":
    asyncio.run(main())
