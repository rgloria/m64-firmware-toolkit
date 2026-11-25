#!/usr/bin/env python3
"""Convert cover images for the M64 Game Library add-on.

Output: COVERS/<CODE>.BIN  ("M64C", u16 80, u16 80, then an 80x80 RGB565 plane and an 80x80 A8 plane).
<CODE> is the 4-character game code the console shows next to a game that has no cover yet
(Menu -> EXPERIMENTAL -> Game Library, e.g. "COVERS/NSME.BIN").

  python make_cover.py mario.png NSME --out E:/            one image
  python make_cover.py --dir my_covers --out E:/           every image in the folder named <CODE>.png/.jpg/...
  python make_cover.py --decode E:/COVERS/NSME.BIN x.png   turn a .BIN back into a PNG (to check it)

--out is the SD card root (or any folder); the COVERS folder is created inside it.
The image is scaled to fit 80x80, keeping its shape; the rest of the square is transparent.
"""
import argparse
import struct
import sys
from pathlib import Path

from PIL import Image

W = H = 80
MAGIC = b"M64C"
EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def encode(img: Image.Image) -> bytes:
    im = img.convert("RGBA")
    im.thumbnail((W, H), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    px = list(canvas.getdata())
    rgb = bytearray()
    for r, g, b, a in px:
        rgb += struct.pack("<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    alpha = bytes(p[3] for p in px)
    out = MAGIC + struct.pack("<HH", W, H) + bytes(rgb) + alpha
    assert len(out) == 8 + W * H * 3
    return out


def decode(data: bytes) -> Image.Image:
    ok = data[:4] == MAGIC and struct.unpack_from("<HH", data, 4) == (W, H) and len(data) == 8 + W * H * 3
    assert ok, "not a cover file"
    im = Image.new("RGBA", (W, H))
    px = im.load()
    for i in range(W * H):
        v = struct.unpack_from("<H", data, 8 + 2 * i)[0]
        r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
        px[i % W, i // W] = ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), data[8 + W * H * 2 + i])
    return im


def good_code(code: str) -> bool:
    return len(code) == 4 and all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in code)


def write(src: Path, code: str, out_root: Path) -> bool:
    code = code.upper()
    if not good_code(code):
        print(f"skip {src.name}: {code!r} is not a 4-character game code (A-Z, 0-9)")
        return False
    d = out_root / "COVERS"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{code}.BIN").write_bytes(encode(Image.open(src)))
    print(f"{src.name} -> {d / (code + '.BIN')}")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("image", nargs="?")
    p.add_argument("code", nargs="?")
    p.add_argument("--dir")
    p.add_argument("--out", default=".")
    p.add_argument("--decode", nargs=2, metavar=("BIN", "PNG"))
    a = p.parse_args()
    if a.decode:
        decode(Path(a.decode[0]).read_bytes()).save(a.decode[1])
        return
    out = Path(a.out)
    if a.dir:
        n = 0
        for f in sorted(Path(a.dir).iterdir()):
            if f.suffix.lower() in EXTS:
                n += write(f, f.stem, out)
        print(f"{n} cover(s) written")
    elif a.image and a.code:
        sys.exit(0 if write(Path(a.image), a.code, out) else 1)
    else:
        p.error("give IMAGE CODE, or --dir FOLDER")


if __name__ == "__main__":
    main()
