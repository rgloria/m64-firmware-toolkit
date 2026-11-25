#!/usr/bin/env python3
"""Apply a same-length in-place string edit to an M64.BIN container and
recompute the two integrity fields the updater checks (section CRC32 and
header CRC16).

By default this is a worked example for stock firmware 1.26.4: it replaces
the menu status string "M64.BIN Ready" at file offset 0x08c918 with the
same-length placeholder "CUSTOM READY!". Edit STR_OFF / OLD / NEW for any
other same-length patch (preserve the trailing NUL; do not shift pointers).

Usage:
    # place a stock official M64.BIN in the current directory, then:
    python scripts/repack.py

Writes M64_mod.BIN next to the input. This does NOT (re)sign the image.
Do not use this to forge a vendor signature; flash via USB-DFU (Route A)
or self-sign with your own key for the dev-mode updater path (Route B).
"""
import zlib, sys

STOCK = "M64.BIN"
OUT = "M64_mod.BIN"

# ---- integrity helpers ----
def crc32_jamcrc(data):
    # zlib/IEEE CRC32 without the final XOR (JAMCRC)
    return zlib.crc32(data) ^ 0xFFFFFFFF

def crc16_ccitt_false(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

# ---- container offsets ----
PAYLOAD_START = 0x118
PAYLOAD_SIZE = 0xBDF90
PAYLOAD_END = PAYLOAD_START + PAYLOAD_SIZE          # 0xBE0A8
SEC_CRC32_OFF = 0xA5                                # section CRC32 (JAMCRC of payload)
MFW1_HDR = 0x98
HDR_CRC16_OFF = 0x116                               # = MFW1_HDR + 0x7E
# header bytes 0x00..0x7D  ->  file MFW1_HDR .. MFW1_HDR+0x7E (exclusive)
HDR_CRC_RANGE = (MFW1_HDR, MFW1_HDR + 0x7E)

# Worked example (stock 1.26.4). Both strings MUST be the same length.
STR_OFF = 0x08c918
OLD = b"M64.BIN Ready"
NEW = b"CUSTOM READY!"   # 13 bytes, same length -> no pointer shifts

def main():
    data = bytearray(open(STOCK, "rb").read())

    # ---- verify we can reproduce stock 1.26.4 integrity values ----
    stock_sec = crc32_jamcrc(bytes(data[PAYLOAD_START:PAYLOAD_END]))
    stock_hdr = crc16_ccitt_false(bytes(data[HDR_CRC_RANGE[0]:HDR_CRC_RANGE[1]]))
    print("recomputed stock section CRC32 =", hex(stock_sec),
          "stored =", hex(int.from_bytes(data[SEC_CRC32_OFF:SEC_CRC32_OFF+4], "little")))
    print("recomputed stock header  CRC16 =", hex(stock_hdr),
          "stored =", hex(int.from_bytes(data[HDR_CRC16_OFF:HDR_CRC16_OFF+2], "little")))
    assert stock_sec == 0x3D847C84, (
        "section CRC32 mismatch - formula wrong, or this is not stock 1.26.4"
    )
    assert stock_hdr == 0x7536, (
        "header CRC16 mismatch - formula wrong, or this is not stock 1.26.4"
    )
    print("OK: integrity formulas reproduce stock 1.26.4 values exactly.\n")

    # ---- apply the string edit ----
    assert len(OLD) == len(NEW), "OLD and NEW must be the same length"
    assert bytes(data[STR_OFF:STR_OFF+len(OLD)]) == OLD, (
        "expected string not where expected (wrong firmware version or already patched?)"
    )
    assert data[STR_OFF+len(OLD)] == 0x00, "NUL terminator missing after string"
    data[STR_OFF:STR_OFF+len(NEW)] = NEW
    print(f"patched menu string @0x{STR_OFF:06x}: {OLD!r} -> {NEW!r}")

    # ---- recompute & write integrity fields ----
    new_sec = crc32_jamcrc(bytes(data[PAYLOAD_START:PAYLOAD_END]))
    data[SEC_CRC32_OFF:SEC_CRC32_OFF+4] = new_sec.to_bytes(4, "little")
    new_hdr = crc16_ccitt_false(bytes(data[HDR_CRC_RANGE[0]:HDR_CRC_RANGE[1]]))
    data[HDR_CRC16_OFF:HDR_CRC16_OFF+2] = new_hdr.to_bytes(2, "little")
    print("new section CRC32 =", hex(new_sec))
    print("new header  CRC16 =", hex(new_hdr))

    open(OUT, "wb").write(data)
    print(f"\nwrote {OUT} ({len(data)} bytes)")

if __name__ == "__main__":
    main()
