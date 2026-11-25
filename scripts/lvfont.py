"""Minimal LVGL 9 fmt_txt font + image decoder that reads straight from the firmware image."""
import struct
from PIL import Image

BASE = 0x08000000


class FW:
    def __init__(self, path):
        self.d = open(path, "rb").read()

    def u8(self, va): return self.d[va - BASE]
    def s8(self, va): return struct.unpack_from("<b", self.d, va - BASE)[0]
    def u16(self, va): return struct.unpack_from("<H", self.d, va - BASE)[0]
    def u32(self, va): return struct.unpack_from("<I", self.d, va - BASE)[0]
    def raw(self, va, n): return self.d[va - BASE: va - BASE + n]


class Font:
    def __init__(self, fw, va):
        self.fw = fw
        self.line_height = fw.u32(va + 12)
        self.base_line = fw.u32(va + 16)
        dsc = fw.u32(va + 24)
        self.bitmap = fw.u32(dsc)
        self.gdsc = fw.u32(dsc + 4)
        self.cmaps = fw.u32(dsc + 8)
        self.kern = fw.u32(dsc + 12)
        bits = fw.u16(dsc + 18)
        self.cmap_num = bits & 0x1FF
        self.bpp = (bits >> 9) & 0xF
        self.kern_classes = (bits >> 13) & 1
        self.bitmap_format = (bits >> 14) & 3

    def gid(self, cp):
        fw = self.fw
        for i in range(self.cmap_num):
            c = self.cmaps + 20 * i   # start u32, len u16, gid_start u16, ulist ptr, ofslist ptr, list_len u16, type u8
            start, length, gstart = fw.u32(c), fw.u16(c + 4), fw.u16(c + 6)
            ulist, olist, llen, typ = fw.u32(c + 8), fw.u32(c + 12), fw.u16(c + 16), fw.u8(c + 18)
            rcp = cp - start
            if rcp < 0 or rcp >= length:
                continue
            if typ == 2:      # FORMAT0_TINY
                return gstart + rcp
            if typ == 0:      # FORMAT0_FULL
                return gstart + fw.u8(olist + rcp)
            if typ == 3:      # SPARSE_TINY
                for k in range(llen):
                    if fw.u16(ulist + 2 * k) == rcp:
                        return gstart + k
            if typ == 1:      # SPARSE_FULL
                for k in range(llen):
                    if fw.u16(ulist + 2 * k) == rcp:
                        return gstart + fw.u16(olist + 2 * k)
        return 0

    def glyph(self, cp):
        g = self.gid(cp)
        a = self.gdsc + 8 * g
        w0 = self.fw.u32(a)
        return dict(idx=w0 & 0xFFFFF, adv=((w0 >> 20) + 8) >> 4, bw=self.fw.u8(a + 4), bh=self.fw.u8(a + 5),
                    ox=self.fw.s8(a + 6), oy=self.fw.s8(a + 7))

    def width(self, text):
        return sum(self.glyph(ord(c))["adv"] for c in text)

    def draw(self, img, x, y, text, color):
        """Draw onto RGBA image with top-left (x, y) of the line box."""
        assert self.bitmap_format == 0
        px = img.load()
        maxv = (1 << self.bpp) - 1
        for ch in text:
            g = self.glyph(ord(ch))
            gx = x + g["ox"]
            gy = y + (self.line_height - self.base_line) - g["bh"] - g["oy"]
            nbits = g["bw"] * g["bh"] * self.bpp
            raw = self.fw.raw(self.bitmap + g["idx"], (nbits + 7) // 8)
            bit = 0
            for r in range(g["bh"]):
                for c in range(g["bw"]):
                    v = 0
                    for _ in range(self.bpp):
                        v = (v << 1) | ((raw[bit >> 3] >> (7 - (bit & 7))) & 1)
                        bit += 1
                    if v and 0 <= gx + c < img.width and 0 <= gy + r < img.height:
                        a = v * 255 // maxv
                        br, bg, bb, ba = px[gx + c, gy + r]
                        px[gx + c, gy + r] = ((color[0] * a + br * (255 - a)) // 255,
                                              (color[1] * a + bg * (255 - a)) // 255,
                                              (color[2] * a + bb * (255 - a)) // 255, 255)
            x += g["adv"]
        return x


def decode_image(fw, va):
    """Decode an lv_image_dsc_t (I4 / I8 / RGB565A8 / ARGB8888) to an RGBA PIL image."""
    m, cf, fl, w, h, st, _, ds, dp, _, _ = struct.unpack_from("<BBHHHHHIIII", fw.d, va - BASE)
    assert m == 0x19, hex(m)
    raw = fw.raw(dp, ds)
    im = Image.new("RGBA", (w, h))
    px = im.load()
    if cf in (0x09, 0x0A):
        n = 16 if cf == 0x09 else 256
        pal = [(raw[4 * i + 2], raw[4 * i + 1], raw[4 * i], raw[4 * i + 3]) for i in range(n)]
        pix = raw[4 * n:]
        for y in range(h):
            for x in range(w):
                if cf == 0x09:
                    b = pix[y * st + x // 2]
                    v = (b >> 4) if x % 2 == 0 else (b & 0xF)
                else:
                    v = pix[y * st + x]
                px[x, y] = pal[v]
    elif cf == 0x14:
        for y in range(h):
            for x in range(w):
                v = struct.unpack_from("<H", raw, y * st + 2 * x)[0]
                a = raw[st * h + y * w + x]
                r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
                px[x, y] = ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), a)
    elif cf == 0x10:
        for y in range(h):
            for x in range(w):
                b, g, r, a = raw[y * st + 4 * x: y * st + 4 * x + 4]
                px[x, y] = (r, g, b, a)
    else:
        raise ValueError(hex(cf))
    return im
