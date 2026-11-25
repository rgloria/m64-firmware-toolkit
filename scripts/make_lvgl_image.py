#!/usr/bin/env python3
"""Pack a PNG into an LVGL 9 lv_image_dsc_t + payload (M64 firmware format).

Does not modify M64.BIN. Writes a .dsc.bin (28-byte header with a placeholder
data pointer of 0) and a .payload.bin, plus a preview PNG.

Usage:
  python make_lvgl_image.py input.png --cf I8 --data-va 0x080BDED8 --out name
  python make_lvgl_image.py input.png --cf I4 --out name   # header ptr left 0

Color formats: I4, I8, A8, RGB565, RGB565A8, ARGB8888
Indexed palettes are stored as BGRA (lv_color32_t). I4/I2/I1 pack high bits first
(left-most pixel in the high nibble / high bits), matching the stock M64 assets.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PIL import Image

CF = {
    "I4": 0x09,
    "I8": 0x0A,
    "A8": 0x0E,
    "RGB565": 0x12,
    "RGB565A8": 0x14,
    "ARGB8888": 0x10,
}


def quantize_rgba(im: Image.Image, ncolors: int) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Return a palette-index image (mode P) and a list of (R,G,B,A) colors.

    Color 0 is reserved for fully transparent (or near-transparent) pixels when
    any alpha is present, matching the stock M64 convention.
    """
    im = im.convert("RGBA")
    w, h = im.size
    pixels = list(im.getdata())
    transparent = [i for i, (r, g, b, a) in enumerate(pixels) if a < 16]
    use_key = len(transparent) > 0
    opaque = [(r, g, b, a) for (r, g, b, a) in pixels if a >= 16]
    n_rgb = max(1, ncolors - (1 if use_key else 0))
    # Quantize the non-transparent pixels in RGB, keep a rough alpha of 255.
    src = Image.new("RGB", (w, h), (0, 0, 0))
    src.putdata([(r, g, b) if a >= 16 else (0, 0, 0) for r, g, b, a in pixels])
    pal_im = src.quantize(colors=n_rgb, method=Image.Quantize.MEDIANCUT)
    raw_pal = pal_im.getpalette()[: n_rgb * 3]
    rgb_cols = [tuple(raw_pal[i : i + 3]) for i in range(0, len(raw_pal), 3)]
    if use_key:
        colors = [(0, 0, 0, 0)] + [(r, g, b, 255) for r, g, b in rgb_cols]
        # shift indices by 1, then force transparent pixels to 0
        idx = list(pal_im.getdata())
        out_idx = [0 if i in set(transparent) else min(p + 1, ncolors - 1) for i, p in enumerate(idx)]
    else:
        colors = [(r, g, b, 255) for r, g, b in rgb_cols]
        out_idx = list(pal_im.getdata())
    while len(colors) < ncolors:
        colors.append((0, 0, 0, 0))
    out = Image.new("P", (w, h))
    out.putdata(out_idx)
    return out, colors[:ncolors]


def pack_indexed(idx_im: Image.Image, colors, bpp: int) -> tuple[bytes, int]:
    w, h = idx_im.size
    ncolors = 1 << bpp
    pal = b"".join(bytes((b, g, r, a)) for (r, g, b, a) in colors[:ncolors])
    pix = list(idx_im.getdata())
    rows = []
    if bpp == 8:
        stride = w
        for y in range(h):
            rows.append(bytes(pix[y * w : (y + 1) * w]))
    elif bpp == 4:
        stride = (w + 1) // 2
        for y in range(h):
            row = pix[y * w : (y + 1) * w]
            out = bytearray(stride)
            for x, v in enumerate(row):
                if x % 2 == 0:
                    out[x // 2] = (v & 0xF) << 4
                else:
                    out[x // 2] |= v & 0xF
            rows.append(bytes(out))
    else:
        raise ValueError(f"unsupported bpp {bpp}")
    payload = pal + b"".join(rows)
    return payload, stride


def pack_a8(im: Image.Image) -> tuple[bytes, int]:
    a = im.convert("RGBA")
    w, h = a.size
    pix = [p[3] for p in a.getdata()]
    return bytes(pix), w


def pack_rgb565(im: Image.Image, with_a: bool) -> tuple[bytes, int]:
    im = im.convert("RGBA")
    w, h = im.size
    rgb = bytearray()
    alpha = bytearray()
    for r, g, b, a in im.getdata():
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        rgb += struct.pack("<H", v)
        alpha.append(a)
    if with_a:
        return bytes(rgb) + bytes(alpha), w * 2
    return bytes(rgb), w * 2


def pack_argb8888(im: Image.Image) -> tuple[bytes, int]:
    im = im.convert("RGBA")
    w, h = im.size
    out = bytearray()
    for r, g, b, a in im.getdata():
        out += bytes((b, g, r, a))  # lv_color32_t BGRA in memory
    return bytes(out), w * 4


def build_dsc(cf: int, w: int, h: int, stride: int, data_size: int, data_va: int) -> bytes:
    # 28-byte lv_image_dsc_t: magic, cf, flags, w, h, stride, reserved16, data_size, data, reserved, reserved2
    return struct.pack(
        "<BBHHHHHIIII",
        0x19,
        cf,
        0,
        w,
        h,
        stride,
        0,
        data_size,
        data_va & 0xFFFFFFFF,
        0,
        0,
    )


def preview_from(im: Image.Image, path: Path) -> None:
    im.convert("RGBA").save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("png")
    ap.add_argument("--cf", default="I8", choices=sorted(CF))
    ap.add_argument("--data-va", default="0", help="VA to store in the descriptor's data pointer")
    ap.add_argument("--out", required=True, help="output prefix")
    args = ap.parse_args()

    im = Image.open(args.png).convert("RGBA")
    w, h = im.size
    cf_name = args.cf.upper()
    cf = CF[cf_name]
    if cf_name == "I4":
        idx, colors = quantize_rgba(im, 16)
        payload, stride = pack_indexed(idx, colors, 4)
    elif cf_name == "I8":
        idx, colors = quantize_rgba(im, 256)
        payload, stride = pack_indexed(idx, colors, 8)
    elif cf_name == "A8":
        payload, stride = pack_a8(im)
    elif cf_name == "RGB565":
        payload, stride = pack_rgb565(im, False)
    elif cf_name == "RGB565A8":
        payload, stride = pack_rgb565(im, True)
    elif cf_name == "ARGB8888":
        payload, stride = pack_argb8888(im)
    else:
        raise SystemExit(cf_name)

    data_va = int(args.data_va, 0)
    dsc = build_dsc(cf, w, h, stride, len(payload), data_va)
    assert len(dsc) == 28, len(dsc)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Path(str(out) + ".dsc.bin").write_bytes(dsc)
    Path(str(out) + ".payload.bin").write_bytes(payload)
    preview_from(im, Path(str(out) + ".preview.png"))
    print(f"cf={cf_name}(0x{cf:02x}) {w}x{h} stride={stride} data_size={len(payload)} data_va=0x{data_va:08x}")
    print(f"  wrote {out}.dsc.bin (28) and {out}.payload.bin ({len(payload)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
