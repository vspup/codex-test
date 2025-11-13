import asyncio
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    if str(PACKAGE_ROOT) not in sys.path:
        sys.path.append(str(PACKAGE_ROOT))
    from core import electabuzz_client as ebc  # type: ignore  # noqa: E402
    from core.constants import cfg  # type: ignore  # noqa: E402
    from core.datapoint_mapping import DATA_POINT_MAPPING  # type: ignore  # noqa: E402
else:
    from ..core import electabuzz_client as ebc
    from ..core.constants import cfg
    from ..core.datapoint_mapping import DATA_POINT_MAPPING

TYPE_MAP = {
    "EB_TYPE_FLOAT": ebc.EB_TYPE_FLOAT,
    "EB_TYPE_DOUBLE": ebc.EB_TYPE_DOUBLE,
    "EB_TYPE_UINT16": ebc.EB_TYPE_UINT16,
    "EB_TYPE_UINT32": ebc.EB_TYPE_UINT32,
    "EB_TYPE_INT32": ebc.EB_TYPE_INT32,
    "EB_TYPE_INT8": ebc.EB_TYPE_INT8,
    "EB_TYPE_BOOL": ebc.EB_TYPE_BOOL,
    "EB_TYPE_UNKOWN": ebc.EB_TYPE_UNKOWN,
}


def _convert_value_for_type(type_name: str, raw_values: list[str]):
    """Convert raw string values into Electabuzz payload respecting the DP type."""

    if type_name == "EB_TYPE_BOOL":
        def to_bool(v: str) -> bool:
            s = v.strip().lower()
            return s in ("1", "true", "yes", "on")

        return to_bool(raw_values[0]) if len(raw_values) == 1 else [to_bool(v) for v in raw_values]

    if type_name in {"EB_TYPE_UINT32", "EB_TYPE_UINT16", "EB_TYPE_INT32", "EB_TYPE_INT8"}:
        caster = int
    else:
        caster = float

    return caster(raw_values[0]) if len(raw_values) == 1 else [caster(v) for v in raw_values]


async def handle_connection(reader, writer, client):
    addr = writer.get_extra_info("peername")
    print(f">> Connected from {addr}")
    writer.write(b">> Connected to Raspberry Pi Electabuzz bridge\n")
    await writer.drain()

    while True:
        data = await reader.readline()
        if not data:
            break
        cmd = data.decode().strip()
        if cmd.lower() in ("exit", "quit"):
            break

        print(f">> [{addr}] CMD: {cmd}")
        parts = cmd.split()
        if not parts:
            continue
        op = parts[0].lower()
        response = ""

        try:
            if op == "r" and len(parts) == 2:
                dp = int(parts[1], 16)
                result = await client.multi_read([dp])
                if result and dp in result:
                    r = result[dp]
                    response = f"<<< READ 0x{dp:04X} = {r['value']} ({r['result_string']})\n"
                else:
                    response = f"<<< Failed to read 0x{dp:04X}\n"


            elif op == "w" and len(parts) >= 3:
                dp = int(parts[1], 16)
                point_key = f"0x{dp:04x}"
                type_name = DATA_POINT_MAPPING.get(point_key, {}).get("type", "EB_TYPE_DOUBLE")
                eb_type = TYPE_MAP.get(type_name, ebc.EB_TYPE_UNKOWN)
                try:
                    value = _convert_value_for_type(type_name, parts[2:])
                except ValueError as exc:
                    response = f"<<< Invalid value for {type_name}: {exc}\n"
                else:
                    res = await client.single_write(dp, value, eb_type=eb_type)
                    if res == ebc.EbResult.EB_OK:
                        response = f"<<< WROTE 0x{dp:04X} = {value} ({res.name})\n"
                    elif res is None:
                        response = f"<<< WROTE 0x{dp:04X} = {value} (no response)\n"
                    else:
                        response = f"<<< WRITE 0x{dp:04X} ERR {res.name}\n"


            else:
                response = "<<< Usage:\n r <hex_dp>\n w <hex_dp> <values>\n"

        except Exception as e:
            response = f"<<< ERROR: {e}\n"

        writer.write(response.encode())
        await writer.drain()
        print(response.strip())

    writer.close()
    await writer.wait_closed()
    print(f">> Disconnected {addr}")

async def main():
    print(f">> Connecting to controller {cfg.host}:{cfg.port} ...")
    client = ebc.Client()
    await client.connect(cfg.host, cfg.port, recv_timeout_ms=cfg.recv_timeout_ms)
    print(f">> Connected to {cfg.host}:{cfg.port}")

    server = await asyncio.start_server(
        lambda r, w: handle_connection(r, w, client),
        "0.0.0.0", 5050
    )
    print(">> Listening on port 5050 for PC connections...")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(">> Stopped.")
