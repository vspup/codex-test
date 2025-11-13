import ctypes as ct
import asyncio
from threading import Lock
import logging
import asyncudp
import msgpack
import socket
import sys
import struct
from enum import Enum

EB_TYPE_NIL = 0x00
EB_TYPE_BOOL = 0x01
EB_TYPE_UINT8 = 0x02
EB_TYPE_INT8 = 0x03
EB_TYPE_UINT16 = 0x04
EB_TYPE_INT16 = 0x05
EB_TYPE_UINT32 = 0x06
EB_TYPE_INT32 = 0x07
EB_TYPE_UINT64 = 0x08
EB_TYPE_INT64 = 0x09
EB_TYPE_FLOAT = 0x0a
EB_TYPE_DOUBLE = 0x0b
EB_TYPE_STR = 0x0c
EB_TYPE_BIN = 0x0d
EB_TYPE_UNKOWN = 0xFF


class EbPacketType(Enum):
    EB_MT_PROCESSING_ERR = 0x0000
    EB_MT_NOT_SUPPORTED = 0x0001
    EB_MT_TIMEOUT = 0x0002
    # 0x1xxx: requests
    EB_MT_PING_REQ = 0x1000
    EB_MT_READ_DATA_REQ = 0x1001
    EB_MT_WRITE_DATA_REQ = 0x1002
    EB_MT_READ_DESC_REQ = 0x1003
    EB_MT_CLIENTS_REQ = 0x1004
    # 0x2xxx: responses
    EB_MT_PING_RSP = 0x2000
    EB_MT_READ_DATA_RSP = 0x2001
    EB_MT_WRITE_DATA_RSP = 0x2002
    EB_MT_READ_DESC_RSP = 0x2003
    EB_MT_CLIENTS_RSP = 0x2004


class EbResult(Enum):
    EB_OK = 0x0000
    EB_ERR_NOT_FOUND = 0x0001
    EB_ERR_OTHER = 0x0004
    EB_ERR_NOT_UNIQUE = 0x0005
    EB_ERR_NOT_IMPLEMENTED = 0x0006
    EB_ERR_WRONG_PARAMETER = 0x0007
    EB_ERR_NO_MEMORY = 0x0008
    EB_ERR_INTERNAL_ERR = 0x0009
    EB_ERR_MSG_FORMAT = 0x000A
    EB_ERR_OVERFLOW = 0x000B
    EB_ERR_TYPE = 0x000C
    EB_ERR_CALLBACK = 0x000D
    EB_ERR_READ_ONLY = 0x000E
    EB_ERR_LENGTH_MISMATCH = 0x000F
    EB_ERR_TIMEOUT = 0x0010
    EB_ERR_CONNECTION = 0xF000


eb_result_dict = {
    0x0000: "EB_OK",
    0x0001: "EB_ERR_NOT_FOUND",
    0x0004: "EB_ERR_OTHER",
    0x0005: "EB_ERR_NOT_UNIQUE",
    0x0006: "EB_ERR_NOT_IMPLEMENTED",
    0x0007: "EB_ERR_WRONG_PARAMETER",
    0x0008: "EB_ERR_NO_MEMORY",
    0x0009: "EB_ERR_INTERNAL_ERR",
    0x000A: "EB_ERR_MSG_FORMAT",
    0x000B: "EB_ERR_OVERFLOW",
    0x000C: "EB_ERR_TYPE",
    0x000D: "EB_ERR_CALLBACK",
    0x000E: "EB_ERR_READ_ONLY",
    0x000F: "EB_ERR_LENGTH_MISMATCH", }


class Client:
    def __init__(self):
        self.verbose = False
        self.transaction_id = 0
        self.url = ""
        self.tx_rx_lock = asyncio.Lock()

    def set_verbose(self, v: bool):
        self.verbose = v

    async def connect(self, hostname: str, port: int = 5554, recv_timeout_ms=500):
        loop = asyncio.get_running_loop()
        addr_info = await loop.getaddrinfo(hostname, port, type=socket.SOCK_DGRAM)
        remote_addr = addr_info[0][4]
        if self.verbose:
            print(f"connecting to {remote_addr}")
        self.sock = await asyncudp.create_socket(remote_addr=remote_addr)  # local_addr=('127.0.0.1', 9999),
        self.ip = addr_info[0]
        self.port = port
        self.recv_timeout = recv_timeout_ms / 1000
        return 0

    def close(self):
        if self.verbose:
            print("closing UDP socket")
        return self.sock.close()

    def _next_transaction_id(self):
        self.transaction_id += 1
        if self.transaction_id > 0xFFFF:
            self.transaction_id = 0
        return self.transaction_id

    def _create_packet(self, type: EbPacketType, payload: bytes) -> bytes:
        version = 0  # only support version 0
        payload_len = len(payload)
        self._next_transaction_id()
        return struct.pack(">HHHH", version, self.transaction_id, type.value, payload_len) + payload

    def _parse_packet(raw_packet: bytes) -> dict:
        if len(raw_packet) < 8:
            print(f"packet length ({len(packet)}) is shorter than header")
            return None
        header = struct.unpack(">HHHH", raw_packet[0:8])
        packet = {}
        packet['version'] = header[0]
        packet['transaction_id'] = header[1]
        packet['type'] = EbPacketType(header[2])
        # TODO: check payload length
        packet['payload'] = raw_packet[8:]
        return packet

    async def _tx_rx(self, tx_packet: bytes, response_type: EbPacketType, n_tries: int = 4) -> dict | EbResult:
        result = None
        skip_tx = False
        verbose = self.verbose
        for i in range(0, n_tries):
            if verbose and i > 0:
                print(f">>>>>>>>> retransmission, try {i}/{n_tries}")
            if not skip_tx:
                if self.verbose:
                    print(f"send message with id {self.transaction_id} to server: {tx_packet.hex(' ')}")
                self.sock.sendto(tx_packet)
            skip_tx = False
            try:
                if verbose:
                    print(f'try to receive UDP datagram')
                async with asyncio.timeout(self.recv_timeout):
                    response_bytes, addr = await self.sock.recvfrom()
            except asyncio.TimeoutError:
                if verbose:
                    print(f'UDP receive timeout ({self.recv_timeout})')
                result = EbResult.EB_ERR_TIMEOUT
                continue
            except ConnectionRefusedError:
                if verbose:
                    print(f'UPD connection failed')
                result = EbResult.EB_ERR_CONNECTION
                continue

            if self.verbose:
                print(f"received bytes {response_bytes.hex(' ')} from {addr}")
            eb_resp_packet = Client._parse_packet(response_bytes)
            if self.verbose:
                print(f"received packet {eb_resp_packet}")

            if eb_resp_packet['version'] != 0:
                print(f"response has wrong version: {eb_resp_packet['version']}")
                result = EbResult.EB_ERR_MSG_FORMAT
                continue

            if eb_resp_packet['transaction_id'] != self.transaction_id:
                if verbose:
                    print(
                        f"wrong transaction id, got {eb_resp_packet['transaction_id']} expected {self.transaction_id}")
                result = EbResult.EB_ERR_MSG_FORMAT
                skip_tx = True  # maybe this was just a leftover or duplicate, ignore it
                continue

            if eb_resp_packet['type'] == EbPacketType.EB_MT_TIMEOUT:
                if verbose:
                    print(f"Server reports a timeout")
                result = EbResult.EB_ERR_TIMEOUT
                continue

            if eb_resp_packet['type'] != response_type:
                if verbose:
                    print(f"received message has wrong type")
                result = EbResult.EB_ERR_MSG_FORMAT
                continue

            return eb_resp_packet
        return result

    async def multi_read(self, id_codes: list[int] | tuple[int]) -> dict[int, dict[str, object]] | None:
        async with self.tx_rx_lock:  # make sure only one request is transmitted at a time since the multiplexer can handle only
            # prepare the requests payload
            packer = msgpack.Packer()
            payload = bytes()
            for id in id_codes:
                if id < 0 or id > 0xFFFF:
                    print(f"ID code {id} is not valid (out of range)")
                    return None
                payload = payload + packer.pack(id)
            if self.verbose:
                print(f"send read request with payload {payload.hex(' ')}")

            # prepare the read request
            eb_req_packet = self._create_packet(EbPacketType.EB_MT_READ_DATA_REQ, payload)

            eb_resp_packet = await self._tx_rx(eb_req_packet, EbPacketType.EB_MT_READ_DATA_RSP, 3)
            if type(eb_resp_packet) == EbResult:
                print(f"could not get response: {eb_req_packet.hex(' ')}")
                return None

            results = dict.fromkeys(id_codes)
            unpacker = msgpack.Unpacker()
            unpacker.feed(eb_resp_packet['payload'])
            payload_len = len(eb_resp_packet['payload'])
            while unpacker.tell() < payload_len:
                dp_id = unpacker.unpack()
                if type(dp_id) != int:
                    print(f"response format error: received ID code is not an int")
                    return None
                if dp_id < 0 or dp_id > 0xFFFF:
                    print(f"response format error: id code {dp_id} is out of range")
                    return None

                result_code = EbResult(unpacker.unpack())

                result = {'data_point_id': dp_id,
                          'result_code': result_code.value,
                          'result_string': eb_result_dict[result_code.value],
                          'data_type': None}
                if result_code == EbResult.EB_OK:
                    value = unpacker.unpack()
                    if type(value) is list:
                        result['num_elements'] = len(value)
                    else:
                        result['num_elements'] = 1
                        # value = [value] # turn a single element into a list for backwards compatibilty
                    result['value'] = value

                results[dp_id] = result
            # TODO: check that there are no bytes left over
        return results

    async def single_write(self, id_code: int, value, eb_type=None) -> EbResult | None:
        async with self.tx_rx_lock:  # make sure only one request is transmitted at a time since the multiplexer can handle only
            if (id_code < 0) or (id_code > 0xFFFF):
                print(f"id_code {id_code} is not an uint16")
                return EbResult.EB_ERR_WRONG_PARAMETER
            use_single_float = False
            if eb_type == EB_TYPE_FLOAT:
                use_single_float = True
            packer = msgpack.Packer(use_single_float=use_single_float)
            # make sure we send doubles if this is requested, the EB server does strict type checking
            if (eb_type == EB_TYPE_DOUBLE) or (eb_type == EB_TYPE_FLOAT):
                if type(value) is list:
                    value = [float(v) for v in value]
                else:
                    value = float(value)

            payload = packer.pack(id_code) + packer.pack(value)
            if self.verbose:
                print(f"send write request for data point {id_code} to server: {payload.hex(' ')}")
            # prepare the read request
            eb_req_packet = self._create_packet(EbPacketType.EB_MT_WRITE_DATA_REQ, payload)

            eb_resp_packet = await self._tx_rx(eb_req_packet, EbPacketType.EB_MT_WRITE_DATA_RSP, 3)
            if type(eb_resp_packet) == EbResult:
                print(f"could not get response: {eb_req_packet}")
                return None
            if self.verbose:
                print(f"process write response payload for 0x{id_code:04x}: {eb_resp_packet['payload'].hex(' ')}")
            unpacker = msgpack.Unpacker()
            unpacker.feed(eb_resp_packet['payload'])
            payload_len = len(eb_resp_packet['payload'])
            result_code = EbResult.EB_ERR_NOT_FOUND
            while unpacker.tell() < payload_len:
                dp_id = unpacker.unpack()
                if type(dp_id) != int:
                    print(f"response format error: received ID code is not an int")
                    return EbResult.EB_ERR_MSG_FORMAT
                if dp_id < 0 or dp_id > 0xFFFF:
                    print(f"response format error: id code {dp_id} is out of range")
                    return EbResult.EB_ERR_MSG_FORMAT
                if dp_id != id_code:
                    print(f"received write response for id {dp_id} but wrote {id_code}")
                    return EbResult.EB_ERR_MSG_FORMAT
                # get the result code
                result_code = EbResult(unpacker.unpack())
            # TODO: check for leftover bytes
        return result_code

    async def get_connected_clients(self) -> tuple[EbResult, dict]:
        eb_req_packet = self._create_packet(EbPacketType.EB_MT_CLIENTS_REQ, b'')
        eb_resp_packet = await self._tx_rx(eb_req_packet, EbPacketType.EB_MT_CLIENTS_RSP, 3)
        if type(eb_resp_packet) == EbResult:
            print(f"could not get response: {eb_req_packet}")
            return None
        unpacker = msgpack.Unpacker(use_list=False, strict_map_key=False)
        unpacker.feed(eb_resp_packet['payload'])
        # payload_len = len(eb_resp_packet['payload'])
        result_code = EbResult.EB_OK
        clients = unpacker.unpack()
        # TODO: check for leftover bytes
        return result_code, clients


async def a_main(read_only: bool = False):
    import time
    import random
    import pprint
    pp = pprint.PrettyPrinter(depth=4)
    c = Client()
    c.set_verbose(False)
    ip = '127.0.0.1'
    port = 5554
    ret = await c.connect(ip, port, recv_timeout_ms=500)
    print(f'connect: {ret}')
    if ret != 0:
        print(f"Make sure an electabuzz multiplexer & test server are running at {ip} : {port}")
        print(f'check server_and_mux.c in electabuzz-multiplexer repo')
        exit()

    # data point ids of the test server's data points
    DPID_UINT32 = 0
    DPID_DOUBLE = 1
    DPID_INT16_ARRAY = 2
    DPID_UINT32_RO = 4

    count = 0
    uint32_value = 0
    int16_values = [*range(-8, 8, 1)]
    double_value = 0.123

    async def write_uint32():
        ret = await c.single_write(DPID_UINT32, uint32_value)
        if ret != EbResult.EB_OK:
            print(f"--- write uint32 = {uint32_value} ---")
            print(f'write returned: {ret}')

    async def write_int16_array():
        ret = await c.single_write(DPID_INT16_ARRAY, int16_values)
        if ret != EbResult.EB_OK:
            print(f"--- write int16 array {int16_values} ---")
            print(f'write returned: {ret}')

    async def write_double():
        ret = await c.single_write(DPID_DOUBLE, double_value)
        if ret != EbResult.EB_OK:
            print(f"--- write double = {double_value} ---")
            print(f'write returned: {ret}')

    if not read_only:
        await write_uint32()
        await write_int16_array()
        await write_double()

    ret = c.close()
    print(f'close returned {ret}')
    # exit(1)
    ret = await c.connect(ip, port, recv_timeout_ms=500)
    print(f'connect: {ret}')
    if ret != 0:
        print(f"Make sure an electabuzz multiplexer & test server are running at {ip}:{port}")
        print(f'check server_and_mux.c in electabuzz-multiplexer repo')
        exit()
    error_count = 0
    for i in range(0, 200000):

        try:
            if not read_only:
                if (random.randrange(0, 10) % 10) == 0:
                    uint32_value = random.randrange(0, 0xFFFFFFFF + 1)
                    await write_uint32()
                if (random.randrange(0, 10) % 10) == 0:
                    int16_values = [random.randrange(-32768, 32768) for _ in range(0, 16)]
                    await write_int16_array()
                if (random.randrange(0, 10) % 10) == 0:
                    double_value = random.random()
                    await write_double()

            count += 1
            # print(f"--- read {count} ---")
            read_res = await c.multi_read([DPID_UINT32, DPID_DOUBLE, DPID_INT16_ARRAY, 3, DPID_UINT32_RO])
        except Exception as e:
            error_count += 1
            print(f"Exception: {e}")
            continue

        # check result
        # print(f'{i}: read res: {read_res}')
        if read_res is None:
            print(f"{i}: timeout")
            ok = False
        else:
            ok = True
            if read_res[DPID_UINT32]['result_string'] != 'EB_OK':
                print(f'ERROR: reading uint32 failed')
                ok = False
            if read_res[DPID_DOUBLE]['result_string'] != 'EB_OK':
                print(f'ERROR: reading double failed')
                ok = False
            if read_res[DPID_INT16_ARRAY]['result_string'] != 'EB_OK':
                print(f'ERROR: reading int16 array failed')
                ok = False
            if read_res[DPID_INT16_ARRAY]['result_string'] != 'EB_OK':
                print(f'ERROR: reading int16 array failed')
                ok = False
            if read_res[DPID_UINT32_RO]['result_string'] != 'EB_OK':
                print(f'ERROR: reading RO uint32 failed')
                ok = False
            if read_res[3]['result_string'] != 'EB_ERR_NOT_FOUND':
                print(f'ERROR: reading non-existing DP did not return correct error')
                ok = False
            if read_res[DPID_UINT32_RO]['value'] != 0xBEEF:  # magic constant hardcoded in server
                print(f'ERROR: RO uint32 readback value missmatch')
                ok = False

            if not read_only:
                # can only check the actual values if we also write them
                if read_res[DPID_UINT32]['value'] != uint32_value:
                    print(f'ERROR: uint32 readback value missmatch')
                    ok = False

                if read_res[DPID_DOUBLE]['value'] != double_value:
                    print(
                        f"ERROR: double readback value missmatch expected {double_value}, got {read_res[DPID_DOUBLE]['value']}")
                    ok = False

                if read_res[DPID_INT16_ARRAY]['value'] != int16_values:
                    print(
                        f"ERROR: int16 array readback value missmatch: expected {int16_values}, got {read_res[DPID_INT16_ARRAY]['value']}")
                    ok = False

        if not ok:
            print(read_res)
            error_count += 1
            # exit(1)

        # time.sleep(1)
        if count % 10000 == 0:
            print(f"{error_count} errors in {count} transfers")

    print("-----")
    print(f"{error_count} errors in {count} transfers")
    return None


async def a_clients(read_only: bool = False):
    import time
    import random
    import pprint
    pp = pprint.PrettyPrinter(depth=4)
    c = Client()
    c.set_verbose(False)
    ip = '127.0.0.1'
    port = 5554
    ret = await c.connect(ip, port, recv_timeout_ms=500)
    print(f'connect: {ret}')
    for i in range(0, 200000):
        _, clients = await c.get_connected_clients()
        print(f'clients: {clients}')
        time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'clients':
            asyncio.run(a_clients())
        if sys.argv[1] == 'read-only':
            asyncio.run(a_main(True))
    asyncio.run(a_main())
