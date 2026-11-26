"""Build <base image> + the Game Library add-on (library, per-game profiles, cover art, virtual Controller Paks).

  python build.py --base path/to/raw_slotA.bin --out path/to/output.bin [--gcc-dir <toolchain bin>]

BUILD ONLY. Nothing here talks to USB/DFU.
The toolchain is found with --gcc-dir, else the M64_GCC environment variable, else PATH.
The base must be a 1.26.4 raw slot-A image whose six hook sites are still stock (stock itself, or stock plus
appended-image mods). It must NOT already contain this add-on: always rebuild from the pre-add-on image.
Compiles src/lib.c with arm-none-eabi-gcc, appends the code after the base image and redirects six
instructions of the stock firmware to it. Every hook asserts the bytes it expects to replace.
"""
import argparse, hashlib, json, os, shutil, struct, subprocess, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

R = Path(__file__).resolve().parent
BASE = 0x08000000
SLOT_A = 0x100000
RAM_ORG, RAM_LEN = 0x240F0000, 0x8000

CFLAGS = ["-mcpu=cortex-m7", "-mthumb", "-mfloat-abi=soft", "-Os", "-ffreestanding", "-fno-builtin",
          "-fno-tree-loop-distribute-patterns", "-fno-jump-tables", "-Wall", "-Wextra", "-Werror"]


def branch(src, dst, link):
    off = dst - (src + 4)
    assert -(1 << 24) <= off < (1 << 24) and off % 2 == 0
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    return struct.pack("<HH", 0xF000 | (s << 10) | ((off >> 12) & 0x3FF),
                       (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF))


def bl(src, dst): return branch(src, dst, True)
def bw(src, dst): return branch(src, dst, False)


# (name, VA, expected original bytes, kind, symbol)
HOOKS = [
    ("H1 reset: bl fw_reset_init",          0x08014FAE, bl(0x08014FAE, 0x08000AB0), "bl", "lib_early_init"),
    ("H2 overlay loop: bl lv_timer_handler", 0x080142A8, bl(0x080142A8, 0x080464B0), "bl", "lib_timer_wrap"),
    ("H3 Settings_Write: push.w prologue",  0x080146B0, bytes.fromhex("2de9f047"),  "b",  "lib_settings_write_tramp"),
    ("H4 PgExp: bl MRW_Label_Create",       0x0802521C, bl(0x0802521C, 0x0802C15C), "bl", "lib_label_create"),
    ("H5 PgExp: bl MRW_Table_Create",       0x0802526C, bl(0x0802526C, 0x0802F328), "bl", "lib_table_create"),
    ("H6 PgExp focus: strd r4,r4,[r5,#8]",  0x0802501C, bytes.fromhex("c5e90244"),  "bl", "lib_nav_tail"),
    ("H7 Cpak_Load entry",                   0x0801BF54, bytes.fromhex("431edbb2"),  "b",  "lib_pak_load"),
    ("H8 Cpak_Save entry",                   0x0801C02C, bytes.fromhex("2de9f74f"),  "b",  "lib_pak_save"),
]


def run(*a):
    subprocess.run([str(x) for x in a], check=True)


def tool(gcc_dir, name):
    exe = name + (".exe" if os.name == "nt" else "")
    if gcc_dir:
        return Path(gcc_dir) / exe
    found = shutil.which(name)
    if not found:
        sys.exit(f"{name} not found: pass --gcc-dir, set M64_GCC, or put the Arm GNU toolchain on PATH")
    return Path(found)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gcc-dir", default=os.environ.get("M64_GCC"))
    a = ap.parse_args()
    SRC, OUT = Path(a.base), Path(a.out)
    gcc, ld, objcopy, nm_ = (tool(a.gcc_dir, "arm-none-eabi-" + t) for t in ("gcc", "ld", "objcopy", "nm"))
    src = SRC.read_bytes()
    print(f"base {SRC.name}: {len(src)} bytes, SHA-256 {hashlib.sha256(src).hexdigest()}")
    assert struct.unpack_from("<II", src, 0) == (0x20020000, 0x08014F71), "not a 1.26.4 raw slot-A image"
    text_org = BASE + ((len(src) + 3) & ~3)
    pad = text_org - BASE - len(src)

    o, elf, blobf = R / "src" / "lib.o", R / "src" / "lib.elf", R / "src" / "lib.text.bin"
    run(gcc, *CFLAGS, "-c", R / "src" / "lib.c", "-o", o)
    run(ld, "-T", R / "src" / "link.ld", "--defsym", f"TEXT_ORG={text_org:#x}", o, "-o", elf,
        "-Map", R / "src" / "lib.map")
    run(objcopy, "-O", "binary", "-j", ".text", elf, blobf)
    blob = blobf.read_bytes()
    nm = subprocess.run([str(nm_), "-n", str(elf)], check=True, capture_output=True, text=True).stdout
    sym = {}
    for line in nm.splitlines():
        a, t, n = line.split()
        sym[n] = int(a, 16)
    undef = subprocess.run([str(nm_), "-u", str(elf)], check=True, capture_output=True, text=True).stdout
    assert not undef.strip(), f"undefined symbols: {undef}"
    bss_len = sym["__bss_end__"] - sym["__bss_start__"]
    assert sym["__bss_start__"] == RAM_ORG and bss_len <= RAM_LEN

    out = bytearray(src) + b"\0" * pad + blob
    patched = []
    for name, va, old, kind, s in HOOKS:
        off = va - BASE
        assert bytes(out[off:off + 4]) == old, f"{name}: found {out[off:off + 4].hex()}, expected {old.hex()}"
        tgt = sym[s]
        assert text_org <= tgt < text_org + len(blob)
        new = bl(va, tgt) if kind == "bl" else bw(va, tgt)
        out[off:off + 4] = new
        patched.append((name, va, old, new, s, tgt))
    OUT.write_bytes(out)

    # ---- verify ----
    out = OUT.read_bytes()
    assert len(out) <= SLOT_A
    assert out[:0x400] == src[:0x400] and struct.unpack_from("<II", out, 0) == (0x20020000, 0x08014F71)
    diffs = [i for i in range(len(src)) if src[i] != out[i]]
    allowed = set()
    for _, va, *_ in patched:
        allowed |= set(range(va - BASE, va - BASE + 4))
    assert set(diffs) <= allowed, [hex(i) for i in diffs if i not in allowed]
    assert out[len(src):len(src) + pad] == b"\0" * pad and out[text_org - BASE:] == blob

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    print("== hooks ==")
    for name, va, old, new, s, tgt in patched:
        ins = next(md.disasm(out[va - BASE:va - BASE + 4], va))
        print(f"  0x{va:08x} (off 0x{va - BASE:x}): {old.hex()} -> {new.hex()}   {ins.mnemonic} {ins.op_str}  = {s}   [{name}]")
        assert int(ins.op_str.lstrip("#"), 16) == tgt
    print("== summary ==")
    print(f"changed bytes inside base image: {len(diffs)} (all inside the {len(patched)} hooked instructions)")
    print(f"pad {pad} @ off 0x{len(src):x}; code+rodata {len(blob)} bytes @ 0x{text_org:08x}..0x{text_org + len(blob):08x}")
    print(f"RAM (bss) {bss_len} bytes @ 0x{RAM_ORG:08x}")
    print(f"size {len(out)} (0x{len(out):x}) / {SLOT_A}; free {SLOT_A - len(out)}")
    print(f"SHA-256 {hashlib.sha256(out).hexdigest()}")
    (R / "src" / "symbols.json").write_text(json.dumps({"image": str(OUT.resolve()), "text_org": text_org, "text_len": len(blob), "sym": sym}, indent=1))


if __name__ == "__main__":
    main()
