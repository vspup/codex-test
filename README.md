# Electabuzz Utilities

This repository contains helper scripts and services used to communicate with
an Electabuzz controller.  The codebase now exposes a dedicated service layer so
that local scripts and remote TCP clients can share the same API surface.

## Project layout

```
py/
  services/        # Shared service layer (gateways, brokers)
  workerA.py       # Example measurement workflow
scripts/
  server.py        # Entry point that exposes the TCP bridge
```

## Running the TCP bridge server

The server proxies TCP commands to the UDP Electabuzz gateway.  The connection
parameters are configured in `py/constants.py`.

```bash
python -m scripts.server
```

Once started the server listens on port `5050` and accepts simple commands:

```
r <hex_datapoint>
w <hex_datapoint> <value> [<value>...]
```

## Service API

The new `py.services` package introduces two interfaces:

- `ElectabuzzGateway` — minimal async API for reading and writing datapoints.
- `MeasurementBroker` — abstraction for components that expose Electabuzz to
  remote clients.

Concrete implementations such as `UdpElectabuzzGateway` and
`TcpMeasurementBroker` live alongside the interfaces.  Both local automation
scripts and remote tools can now depend on the same abstractions.
