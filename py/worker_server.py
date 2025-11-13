import asyncio
from electabuzz_client import Client, EbResult
from constants import cfg

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

                vals = [float(v) for v in parts[2:]]

                try:

                    c = Client()

                    # создаём сокет с новым локальным портом

                    await c.connect(cfg.host, cfg.port, recv_timeout_ms=cfg.recv_timeout_ms)

                    # принудительно переинициализируем сокет (у asyncudp всегда новый порт)

                    res = await c.single_write(dp, vals, eb_type=0x0b)

                    c.close()

                    if res == EbResult.EB_OK:

                        response = f"<<< WROTE 0x{dp:04X} = {vals} (EB_OK)\n"

                    elif res is None:

                        response = f"<<< WROTE 0x{dp:04X} = {vals} (no response)\n"

                    else:

                        response = f"<<< WRITE 0x{dp:04X} ERR {res.name}\n"

                except Exception as e:

                    response = f"<<< ERROR: {e}\n"


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
    client = Client()
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
