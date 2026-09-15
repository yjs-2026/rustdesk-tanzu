#!/usr/bin/env python3
"""Manually construct RustDesk signaling messages and send to Worker.
This bypasses any client caching and tells us exactly what the server does.

The RustDesk signaling protocol uses protobuf. The top-level RendezvousMessage
has a `union` oneof with many fields including register_pk (field 15).

Protobuf wire format reminder:
  varint = (7-bit groups, MSB=continue)
  field = (field_number << 3) | wire_type
  wire_type: 0=varint, 1=64-bit, 2=length-delimited, 5=32-bit
"""
import asyncio
import sys
import struct
import websockets


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field_varint(field_num: int, value: int) -> bytes:
    return varint((field_num << 3) | 0) + varint(value)


def field_bytes(field_num: int, data: bytes) -> bytes:
    return varint((field_num << 3) | 2) + varint(len(data)) + data


def field_string(field_num: int, s: str) -> bytes:
    return field_bytes(field_num, s.encode("utf-8"))


# Build a RegisterPk message:
#   string id = 1
#   bytes uuid = 2
#   bytes pk = 3
#   string old_id = 4
#   bool no_register_device = 5
register_pk = b""
register_pk += field_string(1, "123456789")  # 9-digit peer ID
register_pk += field_bytes(2, b"\x00" * 16)   # fake 16-byte uuid
register_pk += field_bytes(3, b"\x00" * 32)   # fake 32-byte public key
register_pk += field_string(4, "")
register_pk += field_varint(5, 0)             # no_register_device = false

# Wrap in RendezvousMessage union:
#   hbb.RegisterPk register_pk = 15
# RendezvousMessage has no required fields; the union is a oneof at the
# top level. field 15, wire type 2 (length-delimited), value = RegisterPk bytes.
rendezvous_msg = field_bytes(15, register_pk)


async def main():
    uri = "wss://rust.tanzu.eu.org/ws/id"
    print(f"connecting to {uri} ...")
    async with websockets.connect(uri, max_size=2**20) as ws:
        print("handshake done. sending RegisterPk ({} bytes)".format(len(rendezvous_msg)))
        await ws.send(rendezvous_msg)
        print("sent. waiting for response (5s)...")
        try:
            for _ in range(5):
                resp = await asyncio.wait_for(ws.recv(), timeout=2)
                print(f"got response: {resp!r}")
                # Decode top-level protobuf
                print(f"  hex: {resp.hex()}")
        except asyncio.TimeoutError:
            print("5s timeout — no more responses")
        except websockets.ConnectionClosed as e:
            print(f"connection closed: code={e.code} reason={e.reason!r}")


if __name__ == "__main__":
    asyncio.run(main())
