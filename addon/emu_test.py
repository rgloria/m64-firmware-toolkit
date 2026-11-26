"""Usage: python emu_test.py [image.bin]   (default: the image the last build.py run produced)

Run the compiled add-on in Unicorn against Python models of the
firmware functions it calls. Tests the add-on's own logic; it does NOT prove the firmware side."""
import json, struct, sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn.arm_const import *

R = Path(__file__).resolve().parent
SYM = json.loads((R / "src" / "symbols.json").read_text())      # written by build.py
IMG = Path(sys.argv[1] if len(sys.argv) > 1 else SYM["image"]).read_bytes()   # the image build.py just made
sym = SYM["sym"]
HDR = 0x20006DCE
STOP = 0x08000400                        # fake return address


def pak_id_ok(b):
    """N64 Controller Pak ID block checksum (offset 0x20..0x3F), as checked by the stock firmware"""
    s = sum(struct.unpack_from(">H", b, 0x20 + 2 * i)[0] for i in range(14)) & 0xFFFF
    a, c = struct.unpack_from(">HH", b, 0x3C)
    return a == s and c == ((0xFFF2 - s) & 0xFFFF)


def make_pak(tag: bytes) -> bytes:
    p = bytearray(0x8000)
    idb = bytearray(32); idb[0:len(tag)] = tag; idb[25] = 1      # arbitrary ID content
    s = sum(struct.unpack_from(">H", idb, 2 * i)[0] for i in range(14)) & 0xFFFF
    struct.pack_into(">HH", idb, 28, s, (0xFFF2 - s) & 0xFFFF)
    p[0x20:0x40] = idb
    p[0x100:0x100 + len(tag)] = tag                                # recognisable data
    return bytes(p)


class Sim:
    def __init__(self):
        self.store = {}                  # (tag, idx) -> bytes   (the settings EEPROM)
        self.now = 1000
        self.fpga = 1
        self.log = []
        self.oc_fail = False
        self.sd = {}                     # path -> bytes ; None = card not ready
        self.objs = {}                   # live LVGL objects: handle -> dict(kind, hidden, ...)
        self.nobj = 0
        self.busy = set()                # firmware mutexes currently owned by another thread
        self.mutex_waits = []
        self.psram = {}                  # FPGA PSRAM (sparse)
        self.eeprom_pak = make_pak(b"SHARED")
        self.paks_dir = False
        self.sd_write_fail = False
        self.held = []                   # ... owned by the add-on
        self.boot()

    def boot(self):
        """power cycle: RAM lost, settings store kept"""
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.mem_map(0x08000000, 0x100000); u.mem_write(0x08000000, IMG)
        u.mem_map(0x20000000, 0x20000)
        u.mem_map(0x24000000, 0x100000)
        u.mem_write(0x240F0000, b"\xA5" * 0x8000)        # RAM is NOT zero at reset
        u.hook_add(UC_HOOK_CODE, self.code, begin=0x08000000, end=SYM["text_org"] - 1)
        u.hook_add(UC_HOOK_MEM_UNMAPPED, self.bad)
        u.mem_write(0x2000C514, bytes([1]))                 # firmware's "SD mounted" flag
        self.call("lib_early_init")

    def bad(self, u, access, addr, size, value, _):
        raise RuntimeError(f"unmapped access @0x{addr:08x} pc=0x{u.reg_read(UC_ARM_REG_PC):08x}")

    # ---- helpers
    def r(self, n): return self.u.reg_read(n)
    def ret(self, v=None):
        if v is not None: self.u.reg_write(UC_ARM_REG_R0, v & 0xFFFFFFFF)
        self.u.reg_write(UC_ARM_REG_PC, self.r(UC_ARM_REG_LR) | 1)
    def g(self, tag, default, n=1):
        v = self.store.get((tag, 0))
        return int.from_bytes(v[:n], "little") if v else default
    def settings_write_via_fw(self, tag, val, n):
        """model a firmware function that ends in Settings_Write(tag, 0, &val, n): jump into the hooked entry"""
        u = self.u
        sp = self.r(UC_ARM_REG_SP) - 8
        u.mem_write(sp, val.to_bytes(n, "little").ljust(8, b"\0"))
        self._fix_sp = True
        u.reg_write(UC_ARM_REG_SP, sp)
        u.reg_write(UC_ARM_REG_R0, tag); u.reg_write(UC_ARM_REG_R1, 0)
        u.reg_write(UC_ARM_REG_R2, sp); u.reg_write(UC_ARM_REG_R3, n)
        u.reg_write(UC_ARM_REG_PC, 0x080146B0 | 1)

    # ---- firmware models
    def code(self, u, addr, size, _):
        r0, r1, r2, r3 = (self.r(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        if addr == STOP: u.emu_stop(); return
        if addr == 0x080146B0: return                       # hooked entry: real b.w to the trampoline runs
        if addr == 0x080146B4:                              # Settings_Write body (after the displaced push)
            self.store[(r0, r1)] = bytes(u.mem_read(r2, r3))
            self.log.append(("write", r0, r1))
            sp = self.r(UC_ARM_REG_SP)
            regs = struct.unpack("<8I", u.mem_read(sp, 32))
            for reg, v in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                               UC_ARM_REG_R9, UC_ARM_REG_R10), regs):
                u.reg_write(reg, v)
            sp += 32
            if getattr(self, "_fix_sp", False): sp += 8; self._fix_sp = False
            u.reg_write(UC_ARM_REG_SP, sp)
            u.reg_write(UC_ARM_REG_R0, 1); u.reg_write(UC_ARM_REG_PC, regs[7] | 1)
            return
        f = {
            0x08000AB0: lambda: self.ret(),
            0x080464B0: lambda: self.ret(33),
            0x0807E264: lambda: self.ret(self.now),
            0x0801462C: lambda: self.sread(r0, r1, r2, r3),
            0x0800AEC8: lambda: self.ret(self.fpga),
            0x0801315A: lambda: self.ret(self.g(0x10, 0)),
            0x08012FD4: lambda: self.ret(self.g(0x09, 0, 4)),
            0x080130AC: lambda: self.ret(self.g(0x0D, 0, 4)),
            0x08012EA4: lambda: self.ret(self.g(0x04, 0)),
            0x08013186: lambda: (self.log.append(("os_set_oc", r0)), self.settings_write_via_fw(0x10, r0, 1)),
            0x08011A64: lambda: (self.log.append(("ui_vp", self.rd32(r0))), self.settings_write_via_fw(0x09, self.rd32(r0), 4)),
            0x08011C10: lambda: (self.log.append(("ui_img", self.rd32(r0))), self.settings_write_via_fw(0x0D, self.rd32(r0), 4)),
            0x08011BBC: lambda: (self.log.append(("ui_str", self.rd32(r0))), self.settings_write_via_fw(0x04, self.rd32(r0), 1)),
            0x08011DCC: lambda: (self.log.append(("fpga_oc", r0)), self.ret()),
            0x0800882C: lambda: (u.mem_write(r0, bytes([0 if self.oc_fail else 1])), self.ret(1)),
            0x0801C1EC: lambda: (self.log.append(("cpak_flush",)), self.ret()),
            0x08004BE4: lambda: (self.log.append(("event", r0)), self.ret()),
            0x0802C15C: lambda: (self.log.append(("label", bytes(u.mem_read(r1 + 0x29, 16)).split(b"\0")[0].decode())), self.ret(1)),
            0x0802F328: lambda: (self.log.append(("table",)), u.mem_write(r0 + 0x20, struct.pack("<I", 0x0802F265)), self.ret(1)),
            0x0802F264: lambda: (self.log.append(("stock_table_key", r0)), self.ret(r1)),
            0x0803664C: lambda: (self.log.append(("invalidate", r0)), self.ret()),
            0x08034A78: lambda: self.ret(1 if r0 in self.objs else 0),
            0x08039B10: lambda: self.ret(0xBEEF0000),
            0x08039934: lambda: (self.objs[r0].__setitem__("color", r1), self.ret()),
            0x08050394: lambda: self.ret(self.newobj("img")),
            0x08051538: lambda: self.ret(self.newobj("lbl")),
            0x080349F0: lambda: (self.objs[r0].__setitem__("hidden", bool(r2)) if r1 == 1 else None, self.ret()),
            0x08050888: lambda: (self.objs[r0].__setitem__("src", struct.unpack("<7I", u.mem_read(r1, 28))), self.log.append(("set_src", r0)), self.ret()),
            0x08051DFC: lambda: (self.objs[r0].__setitem__("text", bytes(u.mem_read(r1, 32)).split(bytes(1))[0].decode()), self.ret()),
            0x080371BC: lambda: (self.objs[r0].__setitem__("align", (r1, r2, r3, struct.unpack("<i", u.mem_read(self.r(UC_ARM_REG_SP), 4))[0])), self.ret()),
            0x08006314: lambda: self.fopen(r0, r1, r2),
            0x080064D0: lambda: self.fread(r0, r1, r2, r3),
            0x0800684A: lambda: self.fclose(),
            0x08006632: lambda: self.fwrite(r0, r1, r2, r3),
            0x080077B4: lambda: (u.mem_write(r2, bytes(self.psram_get(r0, r1))), self.ret(1)),
            0x0800A9F0: lambda: (self.psram_put(r0, bytes(u.mem_read(r2, r1))), self.ret(1)),
            0x0801B9C8: lambda: self.ret(1 if pak_id_ok(bytes(u.mem_read(r0, 0x40))) else 0),
            0x0801BF58: lambda: self.stock_load(r0),
            0x0801C030: lambda: self.stock_save(),
            0x0807E6A0: lambda: self.mget(r0, r1),
            0x0807E6F4: lambda: (self.held.remove(r0), self.ret(0)),
        }.get(addr)
        if f is None:
            raise RuntimeError(f"add-on jumped to unmodelled firmware address 0x{addr:08x}")
        f()

    def rd32(self, a): return struct.unpack("<I", self.u.mem_read(a, 4))[0]

    def newobj(self, kind):
        self.nobj += 1
        h = 0xC0DE0000 + self.nobj
        self.objs[h] = dict(kind=kind, hidden=False)
        return h

    def mget(self, m, wait):
        if m == 0x20010D60:
            assert 0 < wait <= 5000, "Controller Pak mutex: bounded wait expected"
        else:
            assert m in (0x20008210, 0x200078C4) and wait in (0, 4000), f"file mutex {m:#x} wait {wait}"
            self.mutex_waits.append(wait)
        if m in self.busy: return self.ret(0x1D)            # TX_NOT_AVAILABLE
        self.held.append(m); self.ret(0)

    def fopen(self, fil, path, mode):
        assert self.held[:2] == [0x20008210, 0x200078C4], "file access without both firmware mutexes"
        p = bytes(self.u.mem_read(path, 32)).split(bytes(1))[0].decode()
        self.log.append(("f_open", p, mode))
        if self.sd is None: return self.ret(3)              # FR_NOT_READY
        if p.startswith("PAKS/") and not self.paks_dir: return self.ret(5)   # FR_NO_PATH
        self.fpath, self.fpos, self.fmode = p, 0, mode
        if mode == 1:
            if p not in self.sd: return self.ret(4)         # FR_NO_FILE
        else:
            assert mode == 0x12, f"unexpected open mode {mode:#x}"
            if self.sd_write_fail: return self.ret(7)       # FR_DENIED
            self.sd.setdefault(p, b"")
        self.fdata = self.sd[p]
        self.ret(0)

    def fread(self, fil, buf, n, got):
        d = self.fdata[self.fpos:self.fpos + n]; self.fpos += len(d)
        self.u.mem_write(buf, d); self.u.mem_write(got, struct.pack("<I", len(d)))
        self.ret(0)

    def fwrite(self, fil, buf, n, done):
        assert self.fmode == 0x12
        d = bytes(self.u.mem_read(buf, n))
        cur = bytearray(self.sd[self.fpath])
        if len(cur) < self.fpos + n: cur += bytes(self.fpos + n - len(cur))
        cur[self.fpos:self.fpos + n] = d; self.fpos += n
        self.sd[self.fpath] = bytes(cur)
        self.u.mem_write(done, struct.pack("<I", n)); self.ret(0)

    def fclose(self):
        self.log.append(("f_close",)); self.ret(0)

    # ---- Controller Pak models
    def psram_get(self, addr, n):
        return bytes(self.psram.get(addr + i, 0) for i in range(n))

    def psram_put(self, addr, data):
        for i, b in enumerate(data): self.psram[addr + i] = b

    def pak(self, port):
        return self.psram_get(0x20E00000 + (port - 1) * 0x8000, 0x8000)

    def stock_load(self, port):
        """body of the stock Cpak_Load after the two displaced instructions: shared EEPROM pak -> port PSRAM"""
        self.log.append(("stock_load", port))
        self.psram_put(0x20E00000 + (port - 1) * 0x8000, self.eeprom_pak)
        m = self.u.mem_read(0x20010D94, 1)[0] | (1 << port)
        self.u.mem_write(0x20010D94, bytes([m]))
        self.ret(0)

    def stock_save(self):
        """body of the stock Cpak_Save after the displaced push.w {r0-r2,r4-r11,lr}: port PSRAM -> EEPROM"""
        u = self.u
        sp = self.r(UC_ARM_REG_SP)
        regs = struct.unpack("<12I", u.mem_read(sp, 48))
        port = regs[0]
        self.log.append(("stock_save", port))
        self.eeprom_pak = self.pak(port)
        for reg, v in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                           UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11), regs[3:11]):
            u.reg_write(reg, v)
        u.reg_write(UC_ARM_REG_SP, sp + 48)
        u.reg_write(UC_ARM_REG_R0, 0); u.reg_write(UC_ARM_REG_PC, regs[11] | 1)

    def heading(self):
        return bytes(self.u.mem_read(self.hcfg + 0x29, 35)).split(bytes(1))[0].decode()

    def cover_objs(self):
        img = [o for o in self.objs.values() if o["kind"] == "img"][-1]
        lbl = [o for o in self.objs.values() if o["kind"] == "lbl"][-1]
        return img, lbl

    def select(self, cfg, row, ms=1000):
        self.u.mem_write(cfg + 0x24, struct.pack("<I", row)); self.run(ms)

    def sread(self, tag, idx, buf, plen):
        v = self.store.get((tag, idx))
        cap = self.rd32(plen)
        self.u.mem_write(plen, struct.pack("<I", 0))
        if v is None: return self.ret(-0x7A)
        n = min(cap, len(v))
        self.u.mem_write(buf, v[:n]); self.u.mem_write(plen, struct.pack("<I", n))
        self.ret(1 if cap >= len(v) else -0x77)

    # ---- driving
    def call(self, name, *args, addr=None):
        u = self.u
        for reg, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(reg, v & 0xFFFFFFFF)
        u.reg_write(UC_ARM_REG_SP, 0x2001F000)
        u.reg_write(UC_ARM_REG_LR, STOP | 1)
        u.emu_start((addr or sym[name]) | 1, 0, count=2_000_000)
        assert u.reg_read(UC_ARM_REG_PC) == STOP, f"{name} did not return (pc=0x{u.reg_read(UC_ARM_REG_PC):08x})"
        return u.reg_read(UC_ARM_REG_R0)

    def run(self, ms, step=33):
        for _ in range(ms // step):
            self.now += step
            assert self.call("lib_timer_wrap") == 33
    def cart(self, name=None, code=b"NSME", crc=0):
        if name is None: h = bytes(64)
        else:
            h = bytearray(64); h[0:4] = bytes.fromhex("80371240")
            h[0x10:0x18] = struct.pack(">II", crc, crc ^ 0x55AA)
            h[0x20:0x34] = name.encode().ljust(20, b" "); h[0x3B:0x3F] = code
        self.u.mem_write(HDR, bytes(h))
    def user_set(self, tag, val, n):
        """user changes a setting in the menu -> firmware calls Settings_Write"""
        sp = 0x2001E000
        self.u.mem_write(sp, val.to_bytes(n, "little"))
        assert self.call("Settings_Write", tag, 0, sp, n, addr=0x080146B0) == 1
    def recs(self):
        out = {}
        for (tag, idx), v in self.store.items():
            if tag == 0x60 and idx < 0x80:
                id_, name, plays, seq, flags, oc, vp, img, st = struct.unpack_from("<I20sHHBBBBB", v)
                out[name.split(b"\0")[0].decode()] = dict(slot=idx, plays=plays, seq=seq, on=flags & 1, oc=oc, vp=vp, img=img, str=st)
        return out
    def deflt(self):
        v = self.store.get((0x60, 0x80))
        return None if v is None else tuple(v[4:8])
    def table(self):
        cfg = 0x2001D000
        self.u.mem_write(cfg - 0xA4, struct.pack("<I", 0x0BACC001))          # dropdown cfg +0x14: page "back" callback
        self.u.mem_write(cfg, struct.pack("<10I", 0x1111, 0, 0, 0x20000508, 0x122, 0x84, 2, 0x737373, 3, 0))
        ctx = 0x2001D100
        self.u.mem_write(ctx, struct.pack("<I", 0xCAFE0000))
        self.objs = {}                                       # opening the page again: the old objects are gone
        hcfg, hctx = 0x2001DA00, 0x2001DA80
        self.u.mem_write(hcfg, bytes(0x80)); self.u.mem_write(hctx, struct.pack("<I", 0xC0DE0F00))
        assert self.call("lib_label_create", hctx, hcfg) == 1
        self.objs[0xC0DE0F00] = dict(kind="heading", hidden=False)
        self.hcfg = hcfg
        assert self.call("lib_table_create", ctx, cfg) == 1
        c = struct.unpack("<10I", self.u.mem_read(cfg, 40))
        assert c[6] == 1 and c[7] == 0xFFFFFF and c[2] == 0x0BACC001
        assert self.rd32(ctx + 0x20) == (sym["lib_table_key"] | 1)
        rows, p = [], c[3]
        while True:
            s = self.rd32(p)
            if not s: break
            rows.append(bytes(self.u.mem_read(s, 56)).split(b"\0")[0].decode()); p += 4
        return cfg, ctx, c[2], rows
    def press(self, cfg, ctx, cb, row):
        self.u.mem_write(cfg + 0x24, struct.pack("<I", row))
        assert self.call("lib_table_key", 0x81, ctx) == ctx


def main():
    s = Sim()
    ok = lambda c, m: (print(("PASS " if c else "FAIL ") + m), c or sys.exit(1))

    # 1. boot, no cart
    s.store[(0x10, 0)] = b"\0"; s.store[(0x09, 0)] = bytes(4); s.store[(0x0D, 0)] = bytes(4); s.store[(0x04, 0)] = b"\0"
    s.run(6000)
    ok(s.deflt() == (0, 0, 0, 0) and not s.recs(), "boot without cart: default profile stored, library empty")
    ok(s.table()[3] == ["No cartridges played yet"], "empty library row")

    # 2. first game
    s.log.clear(); s.cart("SUPER MARIO 64", crc=1); s.run(4000)
    r = s.recs()
    ok(r == {"SUPER MARIO 64": dict(slot=0, plays=1, seq=1, on=1, oc=0, vp=0, img=0, str=0)}, f"new game recorded: {r}")
    ok(not [l for l in s.log if l[0] in ("fpga_oc", "ui_vp", "ui_img", "ui_str")], "nothing applied when profile == current")

    # 3. user sets overclock Ultra(2) + profile 3 while Mario runs
    s.user_set(0x10, 2, 1); s.user_set(0x09, 3, 4); s.run(2000)
    r = s.recs()["SUPER MARIO 64"]
    ok((r["oc"], r["vp"]) == (2, 3) and s.deflt() == (0, 0, 0, 0), "changes saved into the game's profile, default untouched")

    # 4. swap to a new game: starts from the default profile -> settings go back
    s.cart(None); s.run(1000); s.log.clear()
    s.cart("MARIO KART 64", crc=2); s.run(4000)
    seq = [l for l in s.log if l[0] != "write"]
    ok(seq == [("ui_vp", 0), ("cpak_flush",), ("fpga_oc", 0), ("os_set_oc", 0), ("event", 0x0F)], f"default applied for new game: {seq}")
    ok(s.g(0x10, 9) == 0 and s.g(0x09, 9, 4) == 0, "global settings now default")
    r = s.recs()
    ok(r["MARIO KART 64"]["oc"] == 0 and r["SUPER MARIO 64"]["oc"] == 2, "applying a profile does not write back into any profile")

    # 5. back to Mario: its profile is restored, play count 2
    s.cart(None); s.run(1000); s.log.clear()
    s.cart("SUPER MARIO 64", crc=1); s.run(4000)
    seq = [l for l in s.log if l[0] != "write"]
    ok(seq == [("ui_vp", 3), ("cpak_flush",), ("fpga_oc", 2), ("os_set_oc", 2), ("event", 0x0F)], f"per-game profile restored: {seq}")
    ok(s.recs()["SUPER MARIO 64"]["plays"] == 2, "play count incremented")

    # 6. library table
    cfg, ctx, cb, rows = s.table()
    ok(rows == ["> SUPER MARIO 64  x2  OC Ultra  P4", "MARIO KART 64  x1  OC Off  P1"], f"rows: {rows}")

    # 7. toggle the running game's profile off -> default applied; on again -> restored
    s.log.clear(); s.press(cfg, ctx, cb, 0); s.run(700)
    ok(s.recs()["SUPER MARIO 64"]["on"] == 0 and s.g(0x10, 9) == 0 and ("invalidate", 0xCAFE0000) in s.log, "toggle off: default applied, table redrawn")
    ok(s.table()[3][0] == "> SUPER MARIO 64  x2  (default)", "row shows (default)")
    s.log.clear(); c2 = s.table()
    for k in (0x82, 0x87, 0x88, 0x8F, 0x90, 0x86):
        assert s.call("lib_table_key", k, c2[1]) == c2[1]
    ok([l[1] for l in s.log if l[0] == "stock_table_key"] == [0x82, 0x87, 0x88, 0x8F, 0x90, 0x86] and s.recs()["SUPER MARIO 64"]["on"] == 0,
       "B, d-pad, encoder and other keys go to the stock table handler untouched")
    s.user_set(0x04, 1, 1); s.run(2000)
    ok(s.deflt() == (0, 0, 0, 1) and s.recs()["SUPER MARIO 64"]["str"] == 0, "with profile off, changes go to the default profile")
    cfg, ctx, cb, rows = s.table(); s.press(cfg, ctx, cb, 0); s.run(700)
    ok(s.g(0x10, 9) == 2 and s.g(0x09, 9, 4) == 3 and s.g(0x04, 9) == 0, "toggle on: game profile restored")
    s.press(cfg, ctx, cb, 1)
    ok(s.recs()["MARIO KART 64"]["on"] == 0, "toggling a game that is not running only flips its flag")

    # 8. overclock that does not settle is reverted to Off
    s.cart(None); s.run(1000)
    s.cart("GOLDENEYE", crc=3); s.run(4000); s.user_set(0x10, 4, 1); s.run(2000)
    s.cart(None); s.run(1000); s.cart("MARIO KART 64", crc=2); s.run(4000)     # (default, oc 0)
    s.oc_fail = True; s.log.clear()
    s.cart(None); s.run(1000); s.cart("GOLDENEYE", crc=3); s.run(4000)
    seq = [l for l in s.log if l[0] in ("fpga_oc", "os_set_oc")]
    ok(seq == [("fpga_oc", 4), ("fpga_oc", 0), ("os_set_oc", 0)] and s.recs()["GOLDENEYE"]["oc"] == 0, f"failed overclock reverted and the profile corrected: {seq}")
    s.oc_fail = False

    # 9. power cycle: library reloaded from the store
    before = s.recs(); s.boot(); s.cart("GOLDENEYE", crc=3); s.run(9000)
    after = s.recs()
    ok(after["GOLDENEYE"]["plays"] == before["GOLDENEYE"]["plays"] + 1 and after["SUPER MARIO 64"] == before["SUPER MARIO 64"], "library survives a power cycle")
    ok(s.g(0x10, 9) == 0, "profile (overclock corrected to Off) in effect after boot")
    # 9b. standby/power-on with the same cart counts as a new play; a short FPGA blip does not
    p0 = s.recs()["GOLDENEYE"]["plays"]
    s.fpga = 0; s.run(500); s.fpga = 1; s.run(3000)
    ok(s.recs()["GOLDENEYE"]["plays"] == p0, "short FPGA interruption is not a new play")
    s.fpga = 0; s.run(5000); s.fpga = 1; s.run(4000)
    ok(s.recs()["GOLDENEYE"]["plays"] == p0 + 1, "power off/on with the same cart counts as a new play")
    # 9c. 20-character names print without running past the field
    s.cart(None); s.run(700); s.cart("ABCDEFGHIJKLMNOPQRST", crc=77); s.run(3000)
    ok(s.table()[3][0] == "> ABCDEFGHIJKLMNOPQRST  x1  OC Off  P1", "20-char name row")

    # 10. garbage / non-header data and the test cart are ignored
    n = len(s.recs())
    s.u.mem_write(HDR, b"\xEE" * 64); s.run(2000)
    s.u.mem_write(HDR, bytes(range(64))); s.run(2000)
    s.cart("M64 Test", crc=99); s.run(3000)
    ok(len(s.recs()) == n, "garbage, 0xEE fill and the M64 Test cart do not create entries")

    # 11. more than 20 games: least recently played is replaced
    for i in range(25):
        s.cart(None); s.run(700); s.cart(f"GAME {i:02d}", crc=100 + i); s.run(3000)
    r = s.recs()
    ok(len(r) == 20 and "GAME 24" in r and "GAME 05" in r and "GAME 04" not in r and "SUPER MARIO 64" not in r, f"LRU eviction keeps the 20 most recent ({sorted(r)[:3]}...)")
    rows = s.table()[3]
    ok(len(rows) == 20 and rows[0].startswith("> GAME 24") and all(len(x) < 56 for x in rows), "table lists 20 rows, newest first")

    # 12. odd names
    s.cart(None); s.run(700); s.cart("", code=b"NZLE", crc=500); s.run(3000)
    s.cart(None); s.run(700); s.cart("  ZELDA\x01MAJORA'S MASK", crc=501); s.run(3000)
    r = s.recs()
    ok("NZLE" in r and "ZELDA MAJORA'S MAS" in r, f"empty name -> game code, control chars/leading spaces cleaned")
    # 13. the two small UI hooks
    u = s.u
    cfg = 0x2001D400; u.mem_write(cfg, b"\0" * 0x80); u.mem_write(cfg + 0x29, b"Coming Soon\0")
    s.log.clear(); assert s.call("lib_label_create", 0x2001D300, cfg) == 1
    ok(s.log == [("label", "Game Library")], "label text replaced before MRW_Label_Create")
    dd, pg = 0x2001D500, 0x2001D700; u.mem_write(dd, b"\0" * 0x200); u.mem_write(pg, b"\0" * 0x20)
    u.reg_write(UC_ARM_REG_R4, dd); u.reg_write(UC_ARM_REG_R5, pg); s.call("lib_nav_tail")
    tb = dd + 0xB0
    ok((s.rd32(pg + 8), s.rd32(pg + 12)) == (dd, tb) and (s.rd32(dd + 0x0C), s.rd32(dd + 0x1C)) == (tb, tb)
       and (s.rd32(tb + 0x08), s.rd32(tb + 0x18)) == (dd, dd) and u.reg_read(UC_ARM_REG_R4) == dd and u.reg_read(UC_ARM_REG_R5) == pg,
       "focus links: dropdown <-> table, page first/last")
    # 14. cover art
    sys.path.insert(0, str(R / "tools"))
    import make_cover
    from PIL import Image
    cover = lambda color: make_cover.encode(Image.new("RGB", (120, 84), color))
    opens = lambda z: len([l for l in z.log if l[0] == "f_open"])
    s2 = Sim()
    for t_, n_ in ((0x10, 1), (0x09, 4), (0x0D, 4), (0x04, 1)): s2.store[(t_, 0)] = bytes(n_)
    s2.run(6000)
    s2.cart("SUPER MARIO 64", code=b"NSME", crc=1); s2.run(3000)
    s2.cart(None); s2.run(700); s2.cart("MARIO KART 64", code=b"NKTE", crc=2); s2.run(3000)
    cfg, ctx, cb, rows = s2.table(); s2.log.clear(); s2.run(1000)
    img, lbl = s2.cover_objs()
    ok(("f_open", "COVERS/NKTE.BIN", 1) in s2.log and img["hidden"] and not lbl["hidden"] and lbl["text"] == "COVERS/NKTE.BIN"
       and lbl["align"] == (0xCAFE0000, 3, 0, 2), f"no cover file: label names the file ({lbl.get('text')})")
    ok(s2.heading() == "Game Library", f"heading stays clean when a cover is simply missing: {s2.heading()}")
    n_open = opens(s2); s2.run(3000)
    ok(opens(s2) == n_open == 1, "the SD card is read once per selection, not every tick")
    s2.sd["COVERS/NSME.BIN"] = cover((200, 30, 30)); s2.sd["COVERS/NKTE.BIN"] = cover((30, 30, 200))
    s2.log.clear(); s2.select(cfg, 1)                                     # move to row 1 (Mario)
    img, lbl = s2.cover_objs(); d = img["src"]
    pix = bytes(s2.u.mem_read(d[4], 19200))
    ok(not img["hidden"] and lbl["hidden"] and d[0] & 0xFFFF == 0x1419 and d[1] == 80 | (80 << 16) and d[2] == 160 and d[3] == 19200
       and pix == s2.sd["COVERS/NSME.BIN"][8:] and ("f_close",) in s2.log, "cover loaded into the image buffer and shown")
    ok(img["align"] == (0xCAFE0000, 3, 0, 0), f"cover kept inside a short table: {img['align']}")
    ok(s2.heading() == "Game Library", f"heading stays clean when the cover loads: {s2.heading()}")
    s2.select(cfg, 0)
    ok(bytes(s2.u.mem_read(img["src"][4], 19200)) == s2.sd["COVERS/NKTE.BIN"][8:], "moving the selection loads the other cover")
    s2.sd["COVERS/NSME.BIN"] = b"JUNK" + s2.sd["COVERS/NSME.BIN"][4:]
    s2.select(cfg, 1); img, lbl = s2.cover_objs()
    ok(img["hidden"] and not lbl["hidden"], "file with a wrong header is rejected")
    s2.sd["COVERS/NSME.BIN"] = cover((1, 2, 3))[:5000]
    s2.select(cfg, 0); s2.select(cfg, 1)
    ok(s2.cover_objs()[0]["hidden"], "truncated file is rejected")
    s2.sd = None; s2.log.clear(); s2.select(cfg, 0, 5000); img, lbl = s2.cover_objs()
    ok(img["hidden"] and lbl["hidden"] and opens(s2) == 1, "SD not ready: nothing shown, one attempt, then a 10 s back-off")
    ok(s2.heading() == "Game Library [NKTE SD err 3]", f"heading status: {s2.heading()}")
    s2.u.mem_write(0x2000C514, bytes([0])); s2.sd = {}; s2.log.clear(); s2.run(11000)
    ok(s2.heading() == "Game Library [NKTE no SD]" and opens(s2) == 0, f"card not mounted: no file access ({s2.heading()})")
    s2.u.mem_write(0x2000C514, bytes([1])); s2.sd = None; s2.run(11000)
    s2.sd = {"COVERS/NKTE.BIN": cover((9, 9, 9))}; s2.run(7000)
    ok(not s2.cover_objs()[0]["hidden"], "retried after the back-off")
    ok(s2.held == [], "both firmware mutexes released after every read")
    ok(s2.mutex_waits and set(s2.mutex_waits) == {0}, "cover reads never wait on a file mutex")
    # firmware busy with the card (e.g. verifying M64.BIN): no file access until it is done
    s2.select(cfg, 1, 300); s2.busy = {0x20008210}; s2.log.clear(); s2.run(4000)
    ok(opens(s2) == 0 and s2.heading().endswith("SD busy]") and s2.held == [], f"verifier holds its mutex: no SD access ({s2.heading()})")
    s2.busy = {0x200078C4}; s2.run(3000)
    ok(opens(s2) == 0 and s2.held == [], "config-file mutex busy: no SD access, first mutex given back")
    s2.busy = set(); s2.sd["COVERS/NSME.BIN"] = cover((5, 5, 5)); s2.run(2500)
    ok(opens(s2) == 1 and s2.heading() == "Game Library" and s2.held == [], "read happens once the firmware is done")
    s2.objs = {}; s2.log.clear(); s2.run(2000)
    ok(not [l for l in s2.log if l[0] in ("f_open", "set_src")], "page closed: no more SD or LVGL calls")
    # a record made by the first version (no game code) gets its code on the next play
    k = [k for k in s2.store if k[0] == 0x60 and k[1] < 0x80 and s2.store[k][4:9] == b"SUPER"][0]
    v = bytearray(s2.store[k]); assert v[33:37] == b"NSME"; v[33:37] = bytes(4); s2.store[k] = bytes(v)
    s2.boot(); s2.sd = {}; s2.cart("SUPER MARIO 64", code=b"NSME", crc=1); s2.run(9000)
    ok(s2.store[k][33:37] == b"NSME", "old record without a game code is completed on the next play")
    s2.cart(None); s2.run(700); s2.cart("HOMEBREW", code=bytes(4), crc=9); s2.run(3000)
    cfg, ctx, cb, rows = s2.table(); s2.log.clear(); s2.run(1000); img, lbl = s2.cover_objs()
    ok(opens(s2) == 0 and img["hidden"] and lbl["hidden"], "game without a valid code: no file access, nothing shown")
    ok(s2.heading() == "Game Library", f"heading clean for a game without a code: {s2.heading()}")
    # 20-row table: the cover is centred on the row and clamped at the end
    for i in range(22):
        code = bytes([78, 71, 48 + i // 10, 48 + i % 10])                 # NG00 .. NG21
        s2.cart(None); s2.run(700); s2.cart(f"GAME {i:02d}", code=code, crc=300 + i); s2.run(2500)
        s2.sd["COVERS/" + code.decode() + ".BIN"] = cover((i * 10, 0, 0))
    cfg, ctx, cb, rows = s2.table()
    s2.select(cfg, 10); a10 = s2.cover_objs()[0]["align"][3]
    s2.select(cfg, 19); a19 = s2.cover_objs()[0]["align"][3]
    ok(a10 == 10 * 16 - 32 and a19 == 20 * 16 - 80, f"cover y offset follows the row ({a10}, {a19})")
    rt = make_cover.decode(make_cover.encode(Image.new("RGB", (200, 100), (255, 128, 0))))
    ok(rt.getpixel((40, 40))[:3] == (255, 130, 0) and rt.getpixel((40, 5))[3] == 0 and rt.getpixel((40, 40))[3] == 255,
       "make_cover: letterboxed, transparent border, round-trips")
    # 15. virtual Controller Paks
    s3 = Sim()
    for t_, n_ in ((0x10, 1), (0x09, 4), (0x0D, 4), (0x04, 1)): s3.store[(t_, 0)] = bytes(n_)
    s3.run(6000)
    load = lambda port=1: s3.call("lib_pak_load", port)
    save = lambda port=1: s3.call("lib_pak_save", port) & 0xFFFFFFFF
    neg = lambda v: v - (1 << 32) if v & 0x80000000 else v
    shared0 = s3.eeprom_pak
    s3.cart("SUPER MARIO 64", code=b"NSME", crc=1); s3.run(3000)
    ok(load() == 0 and s3.pak(1) == shared0 and ("stock_load", 1) in s3.log and s3.held == [], "no PAKS folder: stock shared pak")
    s3.psram_put(0x20E00100, b"MARIOSAVE"); s3.log.clear()
    ok(save() == 0 and ("stock_save", 1) in s3.log and s3.eeprom_pak[0x100:0x109] == b"MARIOSAVE"
       and not [k for k in s3.sd if k.startswith("PAKS/")], "no PAKS folder: saves go to the EEPROM as before")
    shared1 = s3.eeprom_pak
    s3.paks_dir = True; s3.log.clear()
    ok(load() == 0 and s3.pak(1) == shared1 and "PAKS/NSME.MPK" not in s3.sd, "first time with PAKS: game starts from a copy of the shared pak")
    s3.psram_put(0x20E00100, b"MARIO-OWN"); s3.log.clear()
    ok(save() == 0 and s3.sd["PAKS/NSME.MPK"] == s3.pak(1) and len(s3.sd["PAKS/NSME.MPK"]) == 0x8000
       and s3.eeprom_pak == shared1 and not [l for l in s3.log if l[0] == "stock_save"] and s3.held == [],
       "per-game save writes PAKS/NSME.MPK (32,768 bytes), shared EEPROM pak untouched")
    cfg, ctx, cb, rows = s3.table()
    ok(rows[0].endswith("  [pak]"), f"library row marks the game whose pak is loaded: {rows[0]}")
    # power cycle: the game's own pak comes back
    s3.boot(); s3.paks_dir = True; s3.cart("SUPER MARIO 64", code=b"NSME", crc=1); s3.psram = {}
    ok(load() == 0 and s3.pak(1)[0x100:0x109] == b"MARIO-OWN" and s3.held == [], "after a power cycle the per-game pak is loaded from the SD card")
    # another game without a file: starts from the shared pak, not from Mario's
    s3.cart("MARIO KART 64", code=b"NKTE", crc=2)
    ok(load() == 0 and s3.pak(1) == shared1, "a second game starts from the shared pak, not another game's")
    s3.psram_put(0x20E00100, b"KART-OWN!"); save()
    ok(s3.sd["PAKS/NKTE.MPK"][0x100:0x109] == b"KART-OWN!" and s3.sd["PAKS/NSME.MPK"][0x100:0x109] == b"MARIO-OWN", "two games, two files")
    # ports 2-4 are never touched
    s3.log.clear()
    ok(load(2) == 0 and save(2) == 0 and ("stock_load", 2) in s3.log and ("stock_save", 2) in s3.log, "ports 2-4: stock behaviour")
    s3.cart("MARIO KART 64", code=b"NKTE", crc=2); load()
    # SD busy while saving: error, nothing written, retry works
    before = s3.sd["PAKS/NKTE.MPK"]; s3.psram_put(0x20E00100, b"KART-NEW!")
    s3.busy = {0x20008210}; s3.mutex_waits = []
    ok(neg(save()) < 0 and s3.sd["PAKS/NKTE.MPK"] == before and s3.held == [] and s3.mutex_waits == [0],
       "card busy: save fails at once without writing (autosave retries)")
    s3.busy = set()
    ok(save() == 0 and s3.sd["PAKS/NKTE.MPK"][0x100:0x109] == b"KART-NEW!", "retry after the card is free succeeds")
    # invalid ID block in PSRAM: refuse to save (same rule as stock)
    good = s3.sd["PAKS/NKTE.MPK"]; s3.psram_put(0x20E00020, bytes(32))
    ok(neg(save()) < 0 and s3.sd["PAKS/NKTE.MPK"] == good, "corrupt pak in memory is not written over the file")
    # write failure
    load(); s3.sd_write_fail = True
    ok(neg(save()) < 0 and s3.held == [], "write failure reported, locks released"); s3.sd_write_fail = False
    # truncated file: fall back to the shared pak
    s3.sd["PAKS/NKTE.MPK"] = good[:10000]; s3.log.clear()
    ok(load() == 0 and s3.pak(1) == shared1 and [l for l in s3.log if l[0] == "stock_load"] == [("stock_load", 1)] * 2,
       "truncated file: shared pak put back")
    s3.psram_put(0x20E00100, b"NOSAVEME!"); s3.log.clear(); save()
    ok(("stock_save", 1) in s3.log and s3.sd["PAKS/NKTE.MPK"] == good[:10000], "after a failed load, saves go to the shared pak (file left alone)")
    s3.sd["PAKS/NKTE.MPK"] = good
    # no SD card / card busy at load: shared pak
    s3.u.mem_write(0x2000C514, bytes([0])); load()
    ok(s3.pak(1) == s3.eeprom_pak, "no card mounted: shared pak"); s3.u.mem_write(0x2000C514, bytes([1]))
    s3.mutex_waits = []; s3.busy = {0x200078C4}; load(); s3.busy = set()
    ok(s3.pak(1) == s3.eeprom_pak and s3.held == [] and 4000 in s3.mutex_waits, "card still busy after waiting 4 s at load: shared pak, locks released")
    # cartridge without a valid code (flashcart menu): shared pak
    s3.cart("SC64 bootloader", code=bytes(4), crc=9); load()
    ok(s3.pak(1) == s3.eeprom_pak and not [l for l in s3.log if l[0] == "f_open" and l[1].startswith("PAKS/") and l[1][5:9] == "\0\0\0\0"],
       "cartridge without a code: shared pak")
    # game reset path: flush to the old game's file, then reload by the new header
    s3.cart("MARIO KART 64", code=b"NKTE", crc=2); load(); s3.psram_put(0x20E00100, b"KART-LAST"); save()
    s3.cart("SUPER MARIO 64", code=b"NSME", crc=1); load()
    ok(s3.sd["PAKS/NKTE.MPK"][0x100:0x109] == b"KART-LAST" and s3.pak(1)[0x100:0x109] == b"MARIO-OWN", "save then reload switches files cleanly")
    print("ALL PASS")


if __name__ == "__main__":
    main()
