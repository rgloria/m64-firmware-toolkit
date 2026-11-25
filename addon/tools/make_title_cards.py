#!/usr/bin/env python3
"""Generate original title-card covers (coloured card + the game's title as text) for the M64 Game Library.

No box art is used or copied: each card is drawn here from the title string alone.
Input: a JSON object {game code: title}. Output: <out>/COVERS/<CODE>.BIN via make_cover.encode().

  python make_title_cards.py codes.json --out F:/ [--skip-existing] [--sheet preview.png]

--skip-existing leaves any COVERS/<CODE>.BIN already on the card alone (e.g. a real cover you made yourself).
"""
import argparse
import colorsys
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_cover  # noqa: E402

CW, CH = 80, 60                      # card size inside the 80x80 canvas
S = 4                                # supersampling factor
REGION = {"E": "USA", "P": "EUR", "J": "JPN", "D": "GER", "F": "FRA", "I": "ITA", "S": "SPA", "U": "AUS", "X": "EUR", "Y": "EUR", "A": "ASIA", "B": "BRA", "K": "KOR", "C": "CHN"}
FONT_CANDIDATES = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def wrap(draw, words, fnt, width):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def card(code: str, title: str) -> Image.Image:
    h = hashlib.sha256(title.encode()).digest()
    hue = h[0] / 255.0
    base = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.62, 0.50))
    band = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.08) % 1.0, 0.70, 0.88))
    W, H = CW * S, CH * S
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=5 * S, fill=base + (255,), outline=(245, 245, 245, 255), width=S)
    d.rounded_rectangle((3 * S, 3 * S, W - 3 * S - 1, 9 * S), radius=2 * S, fill=band + (255,))
    # title: largest size that fits in 4 lines
    text = title.replace(" - ", " ").replace("  ", " ")
    words = text.split()
    box_w, box_h = W - 10 * S, H - 26 * S
    for size in range(15 * S, 6 * S, -S // 2):
        fnt = font(size)
        lines = wrap(d, words, fnt, box_w)
        lh = int(size * 1.08)
        if len(lines) * lh <= box_h and all(d.textlength(l, font=fnt) <= box_w for l in lines):
            break
    y = 12 * S + (box_h - len(lines) * lh) // 2
    for l in lines:
        x = (W - d.textlength(l, font=fnt)) // 2
        d.text((x + S // 2, y + S // 2), l, font=fnt, fill=(0, 0, 0, 150))
        d.text((x, y), l, font=fnt, fill=(255, 255, 255, 255))
        y += lh
    small = font(7 * S)
    tag = f"{code}  {REGION.get(code[3], '')}".strip()
    d.text(((W - d.textlength(tag, font=small)) // 2, H - 11 * S), tag, font=small, fill=(255, 255, 255, 200))
    return im.resize((CW, CH), Image.LANCZOS)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("codes")
    p.add_argument("--out", required=True)
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--sheet")
    a = p.parse_args()
    codes = json.loads(Path(a.codes).read_text(encoding="utf-8"))
    d = Path(a.out) / "COVERS"
    d.mkdir(parents=True, exist_ok=True)
    n = skipped = 0
    thumbs = []
    for code, title in sorted(codes.items()):
        if not make_cover.good_code(code):
            continue
        im = card(code, title)
        f = d / f"{code}.BIN"
        if a.skip_existing and f.exists():
            skipped += 1
        else:
            f.write_bytes(make_cover.encode(im))
            n += 1
        if len(thumbs) < 48 or code in ("NSME", "NKTE", "CZLE", "NGEE"):
            thumbs.append(im)
    print(f"{n} title card(s) written to {d}, {skipped} existing file(s) kept")
    if a.sheet:
        cols = 8
        sh = Image.new("RGBA", (cols * 84 + 4, ((len(thumbs) + cols - 1) // cols) * 64 + 4), (0x22, 0x22, 0x22, 255))
        for i, t in enumerate(thumbs):
            sh.alpha_composite(t, (4 + (i % cols) * 84, 4 + (i // cols) * 64))
        sh.convert("RGB").resize((sh.width * 2, sh.height * 2), Image.NEAREST).save(a.sheet)


if __name__ == "__main__":
    main()
