"""TCP measurement broker exposing Electabuzz datapoints."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

from ..constants import cfg
from ..datapoint_mapping import DATA_POINT_MAPPING
from ..electabuzz_client import (
    EbResult,
    EB_TYPE_BOOL,
    EB_TYPE_DOUBLE,
    EB_TYPE_FLOAT,
    EB_TYPE_INT32,
    EB_TYPE_INT8,
    EB_TYPE_UINT16,
    EB_TYPE_UINT32,
    EB_TYPE_UNKOWN,
)
from .interfaces import ElectabuzzGateway, MeasurementBroker

TYPE_MAP = {
    "EB_TYPE_FLOAT": EB_TYPE_FLOAT,
    "EB_TYPE_DOUBLE": EB_TYPE_DOUBLE,
    "EB_TYPE_UINT16": EB_TYPE_UINT16,
    "EB_TYPE_UINT32": EB_TYPE_UINT32,
    "EB_TYPE_INT32": EB_TYPE_INT32,
    "EB_TYPE_INT8": EB_TYPE_INT8,
    "EB_TYPE_BOOL": EB_TYPE_BOOL,
    "EB_TYPE_UNKOWN": EB_TYPE_UNKOWN,
}


class TcpMeasurementBroker(MeasurementBroker):
    """Serve TCP clients and forward read/write requests to Electabuzz."""

    def __init__(
        self,
        gateway: ElectabuzzGateway,
        listen_host: str = "0.0.0.0",
        listen_port: int = 5050,
    ) -> None:
        self._gateway = gateway
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._server: asyncio.AbstractServer | None = None

    @property
    def listen_port(self) -> int:
        return self._listen_port

    async def start(self) -> None:
        print(f">> Listening on port {self._listen_port} for PC connections...")
        self._server = await asyncio.start_server(
            self._handle_connection,
            self._listen_host,
            self._listen_port,
        )
        async with self._server:
            await self._server.serve_forever()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        print(f">> Connected from {addr}")
        writer.write(b">> Connected to Raspberry Pi Electabuzz bridge\n")
        await writer.drain()

        try:
            while not reader.at_eof():
                data = await reader.readline()
                if not data:
                    break
                cmd = data.decode().strip()
                if cmd.lower() in ("exit", "quit"):
                    break

                print(f">> [{addr}] CMD: {cmd}")
                response = await self._process_command(cmd)
                writer.write(response.encode())
                await writer.drain()
                print(response.strip())
        finally:
            writer.close()
            await writer.wait_closed()
            print(f">> Disconnected {addr}")

    async def _process_command(self, cmd: str) -> str:
        parts = cmd.split()
        if not parts:
            return ""

        op = parts[0].lower()
        try:
            if op == "r" and len(parts) == 2:
                return await self._handle_read(parts[1])
            if op == "w" and len(parts) >= 3:
                return await self._handle_write(parts[1], parts[2:])
        except Exception as exc:  # noqa: BLE001 - surface the exact error
            return f"<<< ERROR: {exc}\n"

        return "<<< Usage:\n r <hex_dp>\n w <hex_dp> <values>\n"

    async def _handle_read(self, datapoint_raw: str) -> str:
        dp = int(datapoint_raw, 16)
        result = await self._gateway.multi_read([dp])
        if result and dp in result:
            payload = result[dp]
            return f"<<< READ 0x{dp:04X} = {payload['value']} ({payload['result_string']})\n"
        return f"<<< Failed to read 0x{dp:04X}\n"

    async def _handle_write(self, datapoint_raw: str, values: Sequence[str]) -> str:
        dp = int(datapoint_raw, 16)
        point_key = f"0x{dp:04x}"
        type_name = DATA_POINT_MAPPING.get(point_key, {}).get("type", "EB_TYPE_DOUBLE")
        eb_type = TYPE_MAP.get(type_name, EB_TYPE_UNKOWN)
        try:
            value = _convert_value_for_type(type_name, values)
        except ValueError as exc:
            return f"<<< Invalid value for {type_name}: {exc}\n"

        result = await self._gateway.single_write(dp, value, eb_type=eb_type)
        if result == EbResult.EB_OK:
            return f"<<< WROTE 0x{dp:04X} = {value} ({result.name})\n"
        if result is None:
            return f"<<< WROTE 0x{dp:04X} = {value} (no response)\n"
        return f"<<< WRITE 0x{dp:04X} ERR {result.name}\n"


def _convert_value_for_type(type_name: str, raw_values: Sequence[str]) -> Any:
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


async def run_default_server(listen_host: str = "0.0.0.0", listen_port: int = 5050) -> None:
    """Start the default TCP broker using the UDP gateway and project config."""

    from .gateway import UdpElectabuzzGateway

    print(f">> Connecting to controller {cfg.host}:{cfg.port} ...")
    gateway = UdpElectabuzzGateway()
    await gateway.connect(cfg.host, cfg.port, recv_timeout_ms=cfg.recv_timeout_ms)
    print(f">> Connected to {cfg.host}:{cfg.port}")

    broker = TcpMeasurementBroker(gateway, listen_host=listen_host, listen_port=listen_port)
    await broker.start()
