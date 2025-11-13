"""Concrete Electabuzz gateway implementations."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..electabuzz_client import Client
from .interfaces import ElectabuzzGateway


class UdpElectabuzzGateway(ElectabuzzGateway):
    """Gateway that proxies calls to the UDP Electabuzz client."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or Client()

    @property
    def client(self) -> Client:
        return self._client

    async def connect(self, host: str, port: int, *, recv_timeout_ms: int = 500) -> None:
        await self._client.connect(host, port, recv_timeout_ms=recv_timeout_ms)

    async def multi_read(self, datapoints: Sequence[int]) -> Mapping[int, Mapping[str, Any]] | None:
        return await self._client.multi_read(list(datapoints))

    async def single_write(
        self,
        datapoint: int,
        value: Any,
        *,
        eb_type: int | None = None,
    ) -> Any:
        return await self._client.single_write(datapoint, value, eb_type=eb_type)

    def close(self) -> None:
        self._client.close()

    async def __aenter__(self) -> "UdpElectabuzzGateway":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.close()
