"""Shared service interfaces used by local and remote clients."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class ElectabuzzGateway(Protocol):
    """Minimal async API for reading and writing Electabuzz datapoints."""

    async def connect(self, host: str, port: int, *, recv_timeout_ms: int = 500) -> None:
        """Open the connection to the remote Electabuzz controller."""

    async def multi_read(self, datapoints: Sequence[int]) -> Mapping[int, Mapping[str, Any]] | None:
        """Read multiple datapoints and return the raw Electabuzz payload."""

    async def single_write(
        self,
        datapoint: int,
        value: Any,
        *,
        eb_type: int | None = None,
    ) -> Any:
        """Write a datapoint value and return the Electabuzz result."""

    def close(self) -> None:
        """Close the underlying transport."""


class MeasurementBroker(Protocol):
    """Broker capable of exposing Electabuzz to remote TCP clients."""

    async def start(self) -> None:
        """Start serving clients (the call should block until shutdown)."""
