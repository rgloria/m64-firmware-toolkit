#!/usr/bin/env python3
"""Extract the raw slot-A MCU image from an M64.BIN container.

The MCU section is file offset 0x118 .. 0xBE0A8 (end exclusive),
0xBDF90 bytes (778,128), mapped 1:1 at VA 0x08000000.

Usage:
    python extract_slota.py <input M64.BIN> <output.bin>
"""
import sys

PAYLOAD_START = 0x118
PAYLOAD_END = 0xBE0A8  # exclusive
PAYLOAD_SIZE = PAYLOAD_END - PAYLOAD_START  # 0xBDF90 == 778128


def extract(src, dst):
    data = open(src, "rb").read()
    if len(data) < PAYLOAD_END:
        raise SystemExit(
            f"{src}: file is only {len(data)} bytes, need at least {PAYLOAD_END}"
        )
    payload = data[PAYLOAD_START:PAYLOAD_END]
    if len(payload) != PAYLOAD_SIZE:
        raise SystemExit(f"internal error: sliced {len(payload)} bytes, expected {PAYLOAD_SIZE}")
    open(dst, "wb").write(payload)
    print(f"wrote {dst} ({len(payload)} bytes) from {src} [0x{PAYLOAD_START:X}..0x{PAYLOAD_END:X}]")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_slota.py <input M64.BIN> <output.bin>")
    extract(sys.argv[1], sys.argv[2])
