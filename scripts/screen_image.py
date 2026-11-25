#!/usr/bin/env python3
"""Add (or resize/move) an extra LVGL image on an M64 menu screen, in a RAW slot-A image (VA 0x08000000).

Technique (verified on a real unit, see docs/CLAUDE_GUIDE.md "UI image mods"):
  * the hook is an existing `bl <target>` inside the screen's create function, at a point where
    r4 holds the screen's module struct and [r4 + screen_field] is the screen lv_obj;
  * that bl is redirected to a 40-byte Thumb cave appended after the image, which
      1. performs the original call (r0..r3 untouched),
      2. lv_image_create(screen), 3. lv_image_set_src(img, &dsc), 4. lv_obj_align(img, TOP_LEFT, x, y);
  * a 28-byte lv_image_dsc_t and the pixel payload follow the cave.

Subcommands
  add     append cave + descriptor + payload to BASE and patch the hook       -> OUT
  resize  BASE already has a cave from `add` and its payload is the LAST thing in the file:
          rewrite x/y, descriptor w/h/stride/size and the payload in place    -> OUT

PNG input must already be the final RGBA sprite (see sprite_prep.py). Packing uses make_lvgl_image.py.
BUILD ONLY: this script never touches USB/DFU.

Examples (1.26.4 "No Cartridge Detected" screen, hook = its `bl lv_obj_center(console icon)`):
  python screen_image.py add    mcu_in.bin mcu_out.bin sprite.png --x 22 --y 34 --hook 0x0801FBD4 --orig 0x0803758C
  python screen_image.py resize mcu_in.bin mcu_out.bin small.png  --x 44 --y 66 --cave 0x080D05E4
"""
from __future__ import annotations

import argparse, hashlib, struct, subprocess, sys, tempfile
from pathlib import Path

BASE = 0x08000000
SLOT_A = 0x100000
HERE = Path(__file__).resolve().parent

# LVGL 9 entry points in the 1.26.4 MCU image (found by disassembly)
LV_IMAGE_CREATE = 0x08050394
LV_IMAGE_SET_SRC = 0x08050888
LV_OBJ_ALIGN = 0x08035FF8
LV_ALIGN_TOP_LEFT = 1
CAVE_LEN = 40
DSC_FMT = "<BBHHHHHIIII"  # magic cf flags w h stride rsvd data_size data rsvd rsvd  (28 bytes)


def bl(src: int, dst: int) -> bytes:
    """Thumb-2 BL (T1) from src to dst."""
    off = dst - (src + 4)
    assert -(1 << 24) <= off < (1 << 24) and off % 2 == 0, "BL out of range"
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    return struct.pack("<HH", 0xF000 | (s << 10) | ((off >> 12) & 0x3FF),
                       0xD000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF))


def bl_target(src: int, ins: bytes) -> int | None:
    h1, h2 = struct.unpack("<HH", ins)
    if (h1 & 0xF800) != 0xF000 or (h2 & 0xD000) != 0xD000:
        return None
    s = (h1 >> 10) & 1
    j1, j2 = (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if s:
        off -= 1 << 25
    return src + 4 + off


def cave_code(cave_va: int, orig: int, dsc_va: int, x: int, y: int, screen_field: int) -> bytes:
    assert 0 <= x < 256 and 0 <= y < 256, "x/y must fit a movs imm8 (0..255)"
    assert screen_field % 4 == 0 and 0 <= screen_field <= 124
    c = cave_va
    code = struct.pack("<H", 0xB510)                              # +0  push {r4, lr}
    code += bl(c + 2, orig)                                       # +2  bl <original target>
    code += struct.pack("<H", 0x6800 | (screen_field // 4) << 6 | (4 << 3))  # +6  ldr r0, [r4, #field]
    code += bl(c + 8, LV_IMAGE_CREATE)                            # +8
    code += struct.pack("<H", 0x4604)                             # +12 mov r4, r0
    code += struct.pack("<H", 0xB140)                             # +14 cbz r0, +34 (alloc failed -> skip)
    code += struct.pack("<H", 0x4904)                             # +16 ldr r1, [pc, #16] (literal at +36)
    code += bl(c + 18, LV_IMAGE_SET_SRC)                          # +18
    code += struct.pack("<H", 0x4620)                             # +22 mov r0, r4
    code += struct.pack("<H", 0x2100 | LV_ALIGN_TOP_LEFT)         # +24 movs r1, #1
    code += struct.pack("<H", 0x2200 | x)                         # +26 movs r2, #x
    code += struct.pack("<H", 0x2300 | y)                         # +28 movs r3, #y
    code += bl(c + 30, LV_OBJ_ALIGN)                              # +30
    code += struct.pack("<H", 0xBD10)                             # +34 pop {r4, pc}
    code += struct.pack("<I", dsc_va)                             # +36 .word dsc
    assert len(code) == CAVE_LEN
    return code


def pack(png: str, data_va: int, cf: str) -> tuple[bytes, bytes]:
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "img"
        subprocess.run([sys.executable, str(HERE / "make_lvgl_image.py"), png, "--cf", cf,
                        "--data-va", hex(data_va), "--out", str(prefix)], check=True)
        dsc = Path(f"{prefix}.dsc.bin").read_bytes()
        payload = Path(f"{prefix}.payload.bin").read_bytes()
    assert len(dsc) == 28 and struct.unpack_from(DSC_FMT, dsc)[0] == 0x19
    return dsc, payload


def disasm(buf: bytes, va: int, n: int):
    try:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    except ImportError:
        print("  (capstone not installed; skipping disassembly)")
        return
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    for ins in md.disasm(buf[va - BASE:va - BASE + n], va):
        print(f"  0x{ins.address:08x}: {ins.bytes.hex():10s} {ins.mnemonic} {ins.op_str}")


def report(src: bytes, out: bytes, cave_va: int):
    assert len(out) <= SLOT_A, f"image {len(out)} > slot A {SLOT_A}"
    assert out[:0x400] == src[:0x400], "vector table area changed"
    n = min(len(src), len(out))
    diffs = [i for i in range(n) if src[i] != out[i]]
    print("== cave ==")
    disasm(out, cave_va, CAVE_LEN - 4)
    print(f"  0x{cave_va + 36:08x}: .word 0x{struct.unpack_from('<I', out, cave_va + 36 - BASE)[0]:08x}")
    dsc_va = struct.unpack_from("<I", out, cave_va + 36 - BASE)[0]
    m, cf, _, w, h, st, _, ds, dp, _, _ = struct.unpack_from(DSC_FMT, out, dsc_va - BASE)
    x, y = out[cave_va - BASE + 26], out[cave_va - BASE + 28]
    print(f"== image == cf 0x{cf:02x} {w}x{h} stride {st} size {ds} data 0x{dp:08x}; screen ({x},{y})..({x + w - 1},{y + h - 1})")
    print(f"== diff == {len(diffs)} differing bytes in the common {n} bytes; len {len(src)} -> {len(out)}")
    if len(diffs) <= 64:
        for i in diffs:
            print(f"  0x{BASE + i:08x} off 0x{i:x}: {src[i]:02x} -> {out[i]:02x}")
    print(f"size {len(out)} (0x{len(out):x}) / {SLOT_A}; free {SLOT_A - len(out)}")
    print(f"SHA-256 {hashlib.sha256(out).hexdigest()}")
    return diffs


def cmd_add(a):
    src = Path(a.base).read_bytes()
    ho = a.hook - BASE
    tgt = bl_target(a.hook, src[ho:ho + 4])
    assert tgt == a.orig, f"hook 0x{a.hook:08x} is not `bl 0x{a.orig:08x}` (decodes to {tgt and hex(tgt)})"
    cave_va = BASE + ((len(src) + 3) & ~3)
    dsc_va, data_va = cave_va + CAVE_LEN, cave_va + CAVE_LEN + 28
    dsc, payload = pack(a.png, data_va, a.cf)
    out = bytearray(src)
    out[ho:ho + 4] = bl(a.hook, cave_va)
    out += b"\0" * (cave_va - BASE - len(src))
    out += cave_code(cave_va, a.orig, dsc_va, a.x, a.y, a.screen_field) + dsc + payload
    diffs = report(src, bytes(out), cave_va)
    assert diffs and min(diffs) >= ho and max(diffs) < ho + 4, "unexpected change inside the base image"
    Path(a.out).write_bytes(out)
    print(f"wrote {a.out}")


def cmd_resize(a):
    src = Path(a.base).read_bytes()
    co = a.cave - BASE
    assert struct.unpack_from("<H", src, co)[0] == 0xB510 and src[co + 25] == 0x21, "no screen_image cave at that VA"
    dsc_va = struct.unpack_from("<I", src, co + 36)[0]
    old = struct.unpack_from(DSC_FMT, src, dsc_va - BASE)
    data_va, old_size = old[8], old[7]
    assert data_va - BASE + old_size == len(src), "payload is not the last thing in the file; use `add` on a clean base"
    dsc, payload = pack(a.png, data_va, a.cf)
    out = bytearray(src[:data_va - BASE])
    out[co + 26], out[co + 28] = a.x, a.y
    out[dsc_va - BASE:dsc_va - BASE + 28] = dsc
    out += payload
    diffs = report(src, bytes(out), a.cave)
    allowed = {co + 26, co + 28} | set(range(dsc_va - BASE, dsc_va - BASE + 28)) | set(range(data_va - BASE, len(src)))
    assert set(diffs) <= allowed, "unexpected change outside cave x/y, descriptor and payload"
    Path(a.out).write_bytes(out)
    print(f"wrote {a.out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in ("add", "resize"):
        q = sp.add_parser(name)
        q.add_argument("base"); q.add_argument("out"); q.add_argument("png")
        q.add_argument("--x", type=int, required=True); q.add_argument("--y", type=int, required=True)
        q.add_argument("--cf", default="RGB565A8")
    q = sp.choices["add"]
    q.add_argument("--hook", type=lambda s: int(s, 16), required=True, help="VA of the bl to redirect")
    q.add_argument("--orig", type=lambda s: int(s, 16), required=True, help="its original target")
    q.add_argument("--screen-field", type=lambda s: int(s, 0), default=4, help="offset of screen obj in [r4] (default 4)")
    sp.choices["resize"].add_argument("--cave", type=lambda s: int(s, 16), required=True)
    a = p.parse_args()
    {"add": cmd_add, "resize": cmd_resize}[a.cmd](a)


if __name__ == "__main__":
    main()
