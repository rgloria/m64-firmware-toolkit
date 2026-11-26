"""Disassembler/inspector for a RAW slot-A image (VA = 0x08000000 + offset), set M64BIN=<file.bin>.

  str <text>              find a string (VA of the match and of the string start)
  xref <hexVA>            literal-pool words holding that VA
  d <hexVA> <n>           disassemble n bytes; ldr-pc literals are annotated with value, string, lv_image_dsc_t
  dsc <hexVA>             decode an LVGL image descriptor
  w <hexVA> <nwords>      dump 32-bit words
  callers <hexVA> [...]   every BL / B.W that targets these functions
  cli [filter]            the debug-shell command table: name, handler, help text
  events                  event IDs and names (index = the number passed to Event_Post)
  ramrefs <lo> <hi>       literals pointing into a RAM range (check before using RAM as free)

Good first moves for a new feature: `cli <keyword>` (the shell commands lead straight to the core functions),
then `callers` on those functions, then `d` around each call site."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

BASE = 0x08000000
import os
PATH = os.environ.get("M64BIN") or sys.exit("set M64BIN to a raw slot-A .bin (VA 0x08000000)")
data = open(PATH, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.skipdata = True


CODE_END = 0x08083000      # 1.26.4: Thumb code ends before here; rodata follows
IMAGE_END = 0x080BDF90     # end of the stock image (appended add-ons are excluded from RAM checks)


def branch_target(off):
    """(target, 'bl'|'b.w') if the halfword pair at file offset off is a Thumb-2 BL or B.W"""
    h1, h2 = struct.unpack_from("<HH", data, off)
    if (h1 & 0xF800) != 0xF000 or (h2 & 0xD000) not in (0xD000, 0x9000):
        return None
    s = (h1 >> 10) & 1
    i1, i2 = (~(((h2 >> 13) & 1) ^ s)) & 1, (~(((h2 >> 11) & 1) ^ s)) & 1
    o = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if s:
        o -= 1 << 25
    return BASE + off + 4 + o, ("bl" if (h2 & 0xD000) == 0xD000 else "b.w")


def text_at(va, maxlen=200):
    """printable C string at va, else None"""
    if not (BASE <= va < BASE + len(data)):
        return None
    s = cstr(va - BASE)
    return s if 1 <= len(s) <= maxlen and all(32 <= ord(c) < 127 or c in "\r\n\t" for c in s) else None


def cli_table():
    out = []
    for off in range(0, len(data) - 15, 4):
        name, helptext, usage, handler = struct.unpack_from("<IIII", data, off)
        if not (handler & 1 and BASE <= handler < CODE_END):
            continue
        n, h = text_at(name, 40), text_at(helptext)
        if n and h and " " not in n and (usage == 0 or text_at(usage, 400)):
            out.append((n, h.strip(), handler, BASE + off))
    return out


def event_names():
    i = data.find(b"BT_ConnectedPort\x00")
    if i < 0:
        return []
    t = data.find(struct.pack("<I", BASE + i))
    names = []
    while t >= 0 and t + 4 <= len(data):
        v = struct.unpack_from("<I", data, t)[0]
        if v == 0:
            names.append("(none)")
        else:
            s = text_at(v, 40)
            if not s or " " in s:          # event names are identifiers; the table ends at the first non-name
                break
            names.append(s)
        t += 4
    return names


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
    elif cmd == "callers":
        # every Thumb-2 BL / B.W whose target is one of the given VAs (the fastest way to see who uses a function)
        targets = {int(a, 16) & ~1 for a in sys.argv[2:]}
        hits = {t: [] for t in targets}
        for off in range(0, min(len(data), CODE_END - BASE) - 3, 2):
            r = branch_target(off)
            if r and r[0] in targets:
                hits[r[0]].append(f"0x{BASE + off:08x}" + ("" if r[1] == "bl" else "(b.w)"))
        for t in sorted(hits):
            print(f"callers of 0x{t:08x}: {' '.join(hits[t]) or '-'}")
    elif cmd == "cli":
        # the debug-shell command table: 16-byte records {name, help, usage-or-0, handler}. Optional filter text.
        flt = sys.argv[2] if len(sys.argv) > 2 else ""
        for name, helptext, handler, at in cli_table():
            if flt in name or flt in helptext:
                print(f"{name:26s} handler 0x{handler & ~1:08x}  (entry 0x{at:08x})  {helptext}")
    elif cmd == "events":
        # event-name table (index = event ID posted with Event_Post), found from its first name
        for i, name in enumerate(event_names()):
            print(f"0x{i:02x} {name}")
    elif cmd == "ramrefs":
        # 4-byte-aligned literals that point into [lo, hi): use before claiming RAM as free
        lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
        seen = {}
        for off in range(0, min(len(data), IMAGE_END - BASE) - 3, 4):
            v = struct.unpack_from("<I", data, off)[0]
            if lo <= v < hi:
                seen.setdefault(v, []).append(BASE + off)
        for v in sorted(seen):
            print(f"0x{v:08x}  x{len(seen[v])}  first literal @ 0x{seen[v][0]:08x}")
        print(f"{len(seen)} distinct addresses referenced in 0x{lo:08x}..0x{hi:08x}")
    else:
        sys.exit(__doc__)
