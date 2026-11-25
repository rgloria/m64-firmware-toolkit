"""Disassembler/inspector for a RAW slot-A image (VA = 0x08000000 + offset), set M64BIN=<file.bin>.
Subcommands: str <text> | xref <hexVA> | d <hexVA> <n> | dsc <hexVA> | w <hexVA> <nwords>.  ldr-pc literals are
annotated with the value, any string, and any lv_image_dsc_t they point at."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x08000000
import os
PATH = os.environ.get("M64BIN") or sys.exit("set M64BIN to a raw slot-A .bin (VA 0x08000000)")
data = open(PATH, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.skipdata = True


def cstr(off):
    e = data.find(b"\x00", off)
    return data[off:e].decode("latin1", "replace")


def u32(va):
    return struct.unpack_from("<I", data, va - BASE)[0]


def annotate(ins):
    """Resolve pc-relative literal loads to their value (+ string if it points to one)."""
    s = ins.op_str
    if ins.mnemonic.startswith("ldr") and "[pc" in s:
        try:
            imm = int(s.split("#")[1].rstrip("]"), 0)
        except Exception:
            return ""
        lit = ((ins.address + 4) & ~3) + imm
        if BASE <= lit < BASE + len(data) - 4:
            v = u32(lit)
            extra = ""
            if BASE <= v < BASE + len(data):
                o = v - BASE
                if data[o] == 0x19 and data[o + 2:o + 4] == b"\0\0":
                    cf, _, w, h = struct.unpack_from("<BHHH", data, o + 1)
                    extra = f"  <dsc cf=0x{cf:02x} {w}x{h}>"
                else:
                    t = cstr(o)
                    if 2 <= len(t) <= 80 and all(32 <= ord(c) < 127 or c in "\n" for c in t):
                        extra = f"  {t!r}"
            return f"   ; [0x{lit:08x}] = 0x{v:08x}{extra}"
    return ""


def disasm(va, n):
    off = va - BASE
    for ins in md.disasm(data[off:off + n], va):
        print(f"0x{ins.address:08x}: {ins.bytes.hex():10s} {ins.mnemonic:8s} {ins.op_str}{annotate(ins)}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "str":
        needle = sys.argv[2].encode()
        i = data.find(needle)
        while i != -1:
            s = i
            while s > 0 and data[s - 1] != 0:
                s -= 1
            print(f"off 0x{i:x} VA 0x{BASE + i:08x} (str start VA 0x{BASE + s:08x}) {cstr(s)!r}")
            i = data.find(needle, i + 1)
    elif cmd == "xref":
        va = int(sys.argv[2], 16)
        t = struct.pack("<I", va)
        i = data.find(t)
        while i != -1:
            print(f"literal @ VA 0x{BASE + i:08x} -> 0x{va:08x}" + ("" if i % 4 == 0 else "  (unaligned)"))
            i = data.find(t, i + 1)
    elif cmd == "d":
        disasm(int(sys.argv[2], 16), int(sys.argv[3], 0))
    elif cmd == "dsc":
        va = int(sys.argv[2], 16)
        m, cf, fl, w, h, st, r, ds, dp, r1, r2 = struct.unpack_from("<BBHHHHHIIII", data, va - BASE)
        print(f"dsc 0x{va:08x}: magic=0x{m:02x} cf=0x{cf:02x} flags={fl} {w}x{h} stride={st} size={ds} data=0x{dp:08x}")
    elif cmd == "w":
        va = int(sys.argv[2], 16)
        n = int(sys.argv[3], 0)
        for k in range(n):
            print(f"0x{va + 4 * k:08x}: 0x{u32(va + 4 * k):08x}")
