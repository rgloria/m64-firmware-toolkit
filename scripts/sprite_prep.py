"""Turn one frame of a sprite sheet (flat light background) into an RGBA sprite ready for make_lvgl_image.py.

  * crop BOX from the sheet, key the background by flood fill FROM THE BORDER (interior whites such as
    eyes/teeth survive), median + 1 px erode + slight blur on the matte to kill the light fringe;
  * scale to HEIGHT with premultiplied-alpha Lanczos (no light halo);
  * optional 1 px outline (needed when dark art sits on a dark screen, e.g. the black NoCart screen).
HEIGHT is the final image height INCLUDING the 1 px outline on each side.

usage: python sprite_prep.py sheet.png out.png HEIGHT --box x0,y0,x1,y1 [--outline 0,215,75,215 | --outline none]
"""
import sys
from collections import deque
from PIL import Image, ImageFilter, ImageChops

OUTLINE_RGB = (0, 215, 75)   # bright green; high contrast on a dark screen
OUTLINE_ALPHA = 215


def cut_frame(sheet_path, box=None):
    sheet = Image.open(sheet_path).convert("RGB")
    fr = sheet.crop(box) if box is not None else sheet
    w, h = fr.size
    px = fr.load()
    bgc = px[0, 0]

    def is_bg(p, tol):
        return max(abs(p[0] - bgc[0]), abs(p[1] - bgc[1]), abs(p[2] - bgc[2])) <= tol

    # flood fill from the border so interior whites (eyes/teeth/highlights) are kept
    TOL = 26
    seen = bytearray(w * h)
    dq = deque()
    for x in range(w):
        dq.append((x, 0)); dq.append((x, h - 1))
    for y in range(h):
        dq.append((0, y)); dq.append((w - 1, y))
    while dq:
        x, y = dq.popleft()
        if x < 0 or y < 0 or x >= w or y >= h or seen[y * w + x]:
            continue
        if not is_bg(px[x, y], TOL):
            continue
        seen[y * w + x] = 1
        dq.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    alpha = Image.new("L", (w, h))
    alpha.putdata([0 if s else 255 for s in seen])
    # drop isolated specks, then pull the matte in a hair to kill the off-white fringe
    alpha = alpha.filter(ImageFilter.MedianFilter(3))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    rgba = fr.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba.crop(rgba.getbbox())


def scale_premult(im, height):
    w = max(1, round(im.width * height / im.height))
    r, g, b, a = im.split()
    pm = Image.merge("RGBA", (ImageChops.multiply(r, a), ImageChops.multiply(g, a), ImageChops.multiply(b, a), a))
    pm = pm.resize((w, height), Image.LANCZOS)
    out = Image.new("RGBA", (w, height))
    op, ip = out.load(), pm.load()
    for y in range(height):
        for x in range(w):
            pr, pg, pb, pa = ip[x, y]
            if pa < 10:
                op[x, y] = (0, 0, 0, 0)
            else:
                op[x, y] = (min(255, pr * 255 // pa), min(255, pg * 255 // pa), min(255, pb * 255 // pa), pa)
    return out


def add_outline(im, rgb=OUTLINE_RGB, alpha=OUTLINE_ALPHA):
    w, h = im.size
    big = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    big.paste(im, (1, 1))
    a = big.getchannel("A")
    solid = a.point(lambda v: 255 if v >= 96 else 0)
    ring = solid.filter(ImageFilter.MaxFilter(3))             # 1 px dilation (8-neighbourhood)
    ol = Image.new("RGBA", big.size, tuple(rgb) + (0,))
    ol.putalpha(ring.point(lambda v: alpha if v else 0))
    ol.alpha_composite(big)
    return ol


def make(sheet_path, height, out_png, box=None, outline=(OUTLINE_RGB, OUTLINE_ALPHA)):
    """height = total image height including the 1 px outline on each side (outline=None: no outline)."""
    fr = cut_frame(sheet_path, box)
    if outline:
        sp = add_outline(scale_premult(fr, height - 2), *outline)
    else:
        sp = scale_premult(fr, height)
    sp.save(out_png)
    return sp


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sheet"); p.add_argument("out"); p.add_argument("height", type=int)
    p.add_argument("--box", default=None, help="crop box x0,y0,x1,y1 (omit to use the whole image; a little margin is fine)")
    p.add_argument("--outline", default="0,215,75,215", help="r,g,b,a or 'none'")
    a = p.parse_args()
    ol = None if a.outline == "none" else (tuple(map(int, a.outline.split(",")))[:3], int(a.outline.split(",")[3]))
    box = tuple(map(int, a.box.split(","))) if a.box else None
    sp = make(a.sheet, a.height, a.out, box, ol)
    print(sp.size)
    bg = Image.new("RGBA", sp.size, (0, 0, 0, 255))
    bg.alpha_composite(sp)
    bg.resize((sp.width * 4, sp.height * 4), Image.NEAREST).save(a.out.replace(".png", "_4x_black.png"))
