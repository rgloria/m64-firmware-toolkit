/* M64 Game Library + Per-Game Profiles  (add-on for MCU firmware 1.26.4, raw slot-A image)
 *
 * Everything here runs in the overlay (LVGL) thread, inside the render lock, except
 * lib_early_init (reset, before the kernel) and lib_on_settings_write (any thread, sets one byte).
 *
 * Firmware entry points are called through absolute Thumb addresses (FN macro).
 * No .data is allowed (link.ld asserts it); all state is in .bss at 0x240F0000,
 * which the stock reset handler does not touch, so lib_early_init zeroes it.
 */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef unsigned int u32;

#define FN(addr, ret, ...) ((ret (*)(__VA_ARGS__))((addr) | 1u))

/* ---- firmware functions (VAs found by disassembly, see LIBRARY_CHANGES.md) ---- */
#define fw_reset_init       FN(0x08000ab0, void, void)
#define lv_timer_handler    FN(0x080464b0, u32, void)
#define tx_time_get         FN(0x0807e264, u32, void)                 /* 1 tick = 1 ms */
#define Settings_Read       FN(0x0801462c, int, u32 tag, u32 idx, void *buf, u32 *len)
#define Settings_Write      FN(0x080146b0, int, u32 tag, u32 idx, const void *buf, u32 len)
#define FPGA_IsOperational  FN(0x0800aec8, int, void)
#define OS_GetOverclock     FN(0x0801315a, u32, void)                 /* tag 0x10, 0..6 */
#define OS_SetOverclock     FN(0x08013186, void, u32)
#define OS_GetVideoProfile  FN(0x08012fd4, u32, void)                 /* tag 0x09, 0..3 */
#define OS_GetImageSize     FN(0x080130ac, u32, void)                 /* tag 0x0d, 0..1 */
#define OS_GetStretch       FN(0x08012ea4, u32, void)                 /* tag 0x04, 0..1 */
#define UI_SetVideoProfile  FN(0x08011a64, void, u32 *v)              /* the menu's own "set" callbacks: */
#define UI_SetImageSize     FN(0x08011c10, void, u32 *v)              /*   apply to FPGA, then store      */
#define UI_SetStretch       FN(0x08011bbc, void, u32 *v)
#define FPGA_ApplyOcLevel   FN(0x08011dcc, void, u32 level)           /* level -> multiply -> FPGA */
#define FPGA_OcSettled      FN(0x0800882c, int, u8 *passed)           /* waits <=5 s for PSRAM retrain */
#define Cpak_Flush          FN(0x0801c1ec, void, void)
#define Event_Post          FN(0x08004be4, void, u32 ev)
#define MRW_Label_Create    FN(0x0802c15c, int, void *ctx, void *cfg)
#define MRW_Table_Create    FN(0x0802f328, int, void *ctx, void *cfg)
#define MRW_Table_Key       FN(0x0802f264, void *, u32 key, void *ctx)
#define lv_obj_invalidate   FN(0x0803664c, void, void *obj)
#define lv_obj_is_valid     FN(0x08034a78, int, const void *obj)
#define lv_obj_get_parent   FN(0x08039b10, void *, void *obj)
#define lv_obj_set_flag     FN(0x080349f0, void, void *obj, u32 flag, u32 en)   /* add or remove */
#define lv_obj_align_to     FN(0x080371bc, void, void *obj, void *base, u32 align, int x, int y)
#define lv_image_create     FN(0x08050394, void *, void *parent)
#define lv_image_set_src    FN(0x08050888, void, void *img, const void *src)
#define lv_label_create     FN(0x08051538, void *, void *parent)
#define lv_label_set_text   FN(0x08051dfc, void, void *lbl, const char *txt)    /* copies the text */
#define lv_obj_set_style_text_color FN(0x08039934, void, void *obj, u32 rgb, u32 selector)
#define f_open              FN(0x08006314, int, void *fil, const char *path, u32 mode)  /* FatFs, 0 = FR_OK */
#define f_read              FN(0x080064d0, int, void *fil, void *buf, u32 n, u32 *got)
#define f_close             FN(0x0800684a, int, void *fil)
#define tx_mutex_get        FN(0x0807e6a0, u32, void *mutex, u32 wait)   /* 0 = got it; wait 0 = do not block */
#define tx_mutex_put        FN(0x0807e6f4, u32, void *mutex)
/* FatFs has no lock of its own in this firmware. Its stock users serialise with these two mutexes:
 * the M64.BIN verifier / updater (FW_System) and the CHANNEL.TXT reader (FWSettings). A cover read that
 * overlaps the verifier garbles both (seen on the device: no cover + "Corrupt M64.BIN"). */
#define MTX_FW_SYSTEM ((void *)0x20008210)
#define MTX_CFG_FILE ((void *)0x200078c4)

#define LV_FLAG_HIDDEN 1
#define LV_ALIGN_TOP_RIGHT 3
#define ROW_H 16              /* MRW_Table row: 13 px font + 3 px pad */
#define CV_W 80               /* cover canvas, always this size (RGB565A8) */
#define CV_H 80
#define CV_BYTES (CV_W * CV_H * 3)
#define CV_MAGIC 0x4334364du  /* "M64C" */

#define EV_CPAK_RELOAD 0x0f
#define SD_MOUNTED (*(const volatile u8 *)0x2000c514)   /* set by the firmware's SD_Mount (0x08014e14) */
#define CART_HEADER ((const volatile u8 *)0x20006dce)  /* 64-byte N64 ROM header kept by FPGA_Supervisor */

/* settings-store tags (stock uses 0x01..0x16) */
#define TAG_STRETCH 0x04
#define TAG_VPROFILE 0x09
#define TAG_IMGSIZE 0x0d
#define TAG_OC 0x10
#define TAG_LIB 0x60          /* index 0..MAXG-1 = game records, IDX_DEF = default profile */
#define IDX_DEF 0x80

#define MAXG 20               /* MRW_Table shows at most 20 strings */
#define ROWLEN 56
#define F_ON 1                /* per-game profile enabled for this game */

struct prof { u8 oc, vp, img, str; };

struct rec {                  /* 40 bytes, stored as-is in the settings EEPROM */
    u32 id;                   /* FNV-1a of the 64-byte header; 0 = empty */
    char name[20];
    u16 plays;
    u16 seq;                  /* recency stamp */
    u8 flags;
    struct prof p;
    char code[4];             /* game code, header 0x3b..0x3e (0 = unknown); names the cover file */
    u8 rsv[3];
};

struct defrec { u32 magic; struct prof p; };
_Static_assert(sizeof(struct rec) == 40 && sizeof(struct defrec) == 8, "record layout");
#define DEF_MAGIC 0x3146444du /* "MDF1" */

enum { PH_BOOT, PH_WAIT, PH_LOAD, PH_RUN };
enum { AP_NONE, AP_GAME, AP_DEF };

static struct {
    u8 phase, load_idx, dirty, suppress;
    u8 stable, pending, pending_was, rows_n;
    u8 fpga_up, def_valid;
    s8 cur;                   /* slot of the running game, -1 = none */
    u16 seq;
    u32 t0, t_poll, t_dirty, t_game, t_down;
    u32 last_hash, cur_id;
    struct prof live;         /* shadow of the 4 global settings */
    struct prof def;          /* default profile (games with profile off, new games) */
    struct rec recs[MAXG];
    void *tbl_cfg;
    /* cover art */
    void *cv_img, *cv_lbl, *cv_tbl;
    u8 *hd_cfg;               /* "Game Library" heading: MRW_Label cfg (text inline at +0x29, 35 bytes) */
    void **hd_ctx;            /* and its widget (ctx[0] = lv_obj) */
    u32 cv_retry;             /* no SD access before this time (after an SD error) */
    u8 cv_shown, cv_last, cv_stable, cv_pad;
    u32 cv_dsc[7];            /* lv_image_dsc_t */
    char cv_path[20];
    u8 cv_fil[0x240];         /* FatFs FIL (0x228 in this build) */
    /* whole file: 8-byte header + pixels. 32-byte aligned so FatFs' direct multi-sector read lands on a
     * cache-line aligned address (the SD driver's requirements were not reverse-engineered). */
    u8 cv_raw[CV_BYTES + 8 + 24] __attribute__((aligned(32)));
    const char *row_ptr[MAXG + 1];
    s8 row_map[MAXG];
    char rows[MAXG][ROWLEN];
} S;

extern u32 __bss_start__[], __bss_end__[];

static const char OCN[5][8] = { "Off", "Super", "Ultra", "Extreme", "Insane" };

/* ------------------------------------------------------------------ helpers */
/* GCC may emit calls to these for struct copies / zeroing even with -ffreestanding. */
void *memcpy(void *d, const void *s, u32 n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }
void *memset(void *d, int c, u32 n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
#define zmem(d, n) memset((d), 0, (n))
#define cmem(d, s, n) memcpy((d), (s), (n))
static int peq(struct prof a, struct prof b) { return a.oc == b.oc && a.vp == b.vp && a.img == b.img && a.str == b.str; }

static char *put_s(char *o, char *end, const char *s) { while (*s && o < end) *o++ = *s++; return o; }
static char *put_n(char *o, char *end, const char *s, int n) { while (n-- && *s && o < end) *o++ = *s++; return o; }
static char *put_u(char *o, char *end, u32 v)
{
    char t[10]; int n = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n && o < end) *o++ = t[--n];
    return o;
}

static struct prof snapshot(void)
{
    struct prof p;
    p.oc = (u8)OS_GetOverclock();
    p.vp = (u8)OS_GetVideoProfile();
    p.img = (u8)OS_GetImageSize();
    p.str = (u8)OS_GetStretch();
    return p;
}

static void save_rec(int i) { Settings_Write(TAG_LIB, (u32)i, &S.recs[i], sizeof(struct rec)); }
static void save_def(void)
{
    struct defrec d; d.magic = DEF_MAGIC; d.p = S.def;
    Settings_Write(TAG_LIB, IDX_DEF, &d, sizeof d);
}

/* ------------------------------------------------------------------ hooks: reset + settings write */
/* H1: replaces `bl 0x08000ab0` in Reset_Handler. */
void lib_early_init(void)
{
    u32 *p = __bss_start__;
    while (p < __bss_end__) *p++ = 0;
    fw_reset_init();
}

/* H3: called from the Settings_Write trampoline (any thread). */
void lib_on_settings_write(u32 tag)
{
    if (S.suppress || S.phase != PH_RUN) return;
    if (tag == TAG_STRETCH || tag == TAG_VPROFILE || tag == TAG_IMGSIZE || tag == TAG_OC) {
        S.t_dirty = tx_time_get();
        S.dirty = 1;
    }
}

__attribute__((naked)) void lib_settings_write_tramp(void)
{
    __asm__(
        "push {r0, r1, r2, r3, r4, lr}\n"       /* r4 only keeps sp 8-aligned */
        "bl lib_on_settings_write\n"
        "pop {r0, r1, r2, r3, r4, lr}\n"
        "push.w {r4, r5, r6, r7, r8, r9, r10, lr}\n"   /* the instruction displaced at 0x080146b0 */
        "ldr r12, =0x080146b5\n"
        "bx r12\n"
        ".ltorg\n");
}

/* ------------------------------------------------------------------ applying a profile */
static void set_oc(u32 level)
{
    u8 pass = 0;
    Cpak_Flush();                               /* same sequence as the menu's Overclocking handler */
    FPGA_ApplyOcLevel(level);
    if (FPGA_OcSettled(&pass) == 1 && pass) {
        OS_SetOverclock(level);
    } else {
        FPGA_ApplyOcLevel(0);
        OS_SetOverclock(0);
    }
    Event_Post(EV_CPAK_RELOAD);
}

static void apply(struct prof want)
{
    struct prof cur = snapshot();
    u32 v;
    S.suppress = 1;
    if (want.vp != cur.vp && want.vp <= 3) { v = want.vp; UI_SetVideoProfile(&v); }
    if (want.img != cur.img && want.img <= 1) { v = want.img; UI_SetImageSize(&v); }
    if (want.str != cur.str && want.str <= 1) { v = want.str; UI_SetStretch(&v); }
    if (want.oc != cur.oc && want.oc <= 4) set_oc(want.oc);
    S.live = snapshot();
    S.suppress = 0;
    S.dirty = 0;
}

/* ------------------------------------------------------------------ library */
static u32 fnv(const u8 *p, u32 n)
{
    u32 h = 0x811c9dc5u;
    while (n--) { h ^= *p++; h *= 0x01000193u; }
    return h ? h : 1;
}

static int find(u32 id)
{
    for (int i = 0; i < MAXG; i++) if (S.recs[i].id == id) return i;
    return -1;
}

static int alloc_slot(void)
{
    int best = 0;
    for (int i = 0; i < MAXG; i++) {
        if (S.recs[i].id == 0) return i;
        if (S.recs[i].seq < S.recs[best].seq) best = i;
    }
    return best;                                /* least recently played */
}

static void game_start(const u8 *h, u32 id, u32 now)
{
    int i = find(id);
    struct rec *r;
    if (i < 0) {
        int n = 0, last = -1;
        i = alloc_slot();
        r = &S.recs[i];
        zmem(r, sizeof *r);
        r->id = id;
        for (int k = 0; k < 20; k++) {          /* internal name: header 0x20..0x33 */
            u8 c = h[0x20 + k];
            if (c < 0x20 || c > 0x7e) c = ' ';
            if (c != ' ') last = n;
            if (c != ' ' || n) r->name[n++] = (char)c;   /* skip leading spaces */
        }
        for (int k = last + 1; k < 20; k++) r->name[k] = 0;
        if (last < 0) {                          /* no usable name: game code, header 0x3b..0x3e */
            for (int k = 0; k < 4; k++) { u8 c = h[0x3b + k]; r->name[k] = (c >= 0x21 && c <= 0x7e) ? (char)c : '?'; }
        }
        r->flags = F_ON;
        r->p = S.def;                            /* new games start from the default profile */
    } else {
        r = &S.recs[i];
    }
    if (!r->code[0]) {                           /* also fills in records made before cover art existed */
        int okc = 1;
        for (int k = 0; k < 4; k++) {
            u8 c = h[0x3b + k];
            if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z'))) okc = 0;
        }
        if (okc) for (int k = 0; k < 4; k++) r->code[k] = (char)h[0x3b + k];
    }
    if (r->plays < 0xffff) r->plays++;
    r->seq = ++S.seq;
    S.cur = (s8)i;
    S.cur_id = id;
    S.t_game = now;
    S.pending = (r->flags & F_ON) ? AP_GAME : AP_DEF;
    save_rec(i);
}

static void poll_cart(u32 now)
{
    u8 h[64];
    u32 id;
    int same = 1;
    for (int i = 0; i < 64; i++) { h[i] = CART_HEADER[i]; if (h[i] != h[0]) same = 0; }
    /* the supervisor zeroes the buffer when the cart is removed; require a z64 header otherwise */
    if (same || h[0] != 0x80 || h[3] != 0x40) {
        S.stable = 0; S.last_hash = 0;
        if (same && h[0] == 0 && S.cur_id) { S.cur = -1; S.cur_id = 0; S.pending = AP_NONE; }
        return;
    }
    id = fnv(h, 64);
    if (id != S.last_hash) { S.last_hash = id; S.stable = 0; return; }
    if (S.stable < 3 && ++S.stable == 3 && id != S.cur_id) {
        static const char TEST[8] = "M64 Test";  /* factory test cart: not a game */
        int t = 1;
        for (int i = 0; i < 8; i++) if (h[0x20 + i] != (u8)TEST[i]) t = 0;
        if (t) { S.cur = -1; S.cur_id = id; S.pending = AP_NONE; return; }
        game_start(h, id, now);
    }
}

static void on_dirty(void)
{
    struct prof n = snapshot();
    struct prof *t = (S.cur >= 0 && (S.recs[S.cur].flags & F_ON)) ? &S.recs[S.cur].p : &S.def;
    int ch = 0;
    /* only the fields the user actually changed go into the target profile */
    if (n.oc != S.live.oc) { t->oc = n.oc; ch = 1; }
    if (n.vp != S.live.vp) { t->vp = n.vp; ch = 1; }
    if (n.img != S.live.img) { t->img = n.img; ch = 1; }
    if (n.str != S.live.str) { t->str = n.str; ch = 1; }
    S.live = n;
    if (!ch) return;
    if (t == &S.def) save_def(); else save_rec(S.cur);
}

static void cover_tick(u32 now);

static void lib_tick(void)
{
    u32 now = tx_time_get();
    switch (S.phase) {
    case PH_BOOT:
        S.t0 = now; S.cur = -1; S.phase = PH_WAIT;
        return;
    case PH_WAIT:
        if (now - S.t0 < 3000) return;
        S.phase = PH_LOAD;
        return;
    case PH_LOAD:                               /* one EEPROM record per tick, to keep the UI smooth */
        if (S.load_idx < MAXG) {
            struct rec t; u32 len = sizeof t;
            if (Settings_Read(TAG_LIB, S.load_idx, &t, &len) == 1 && len == sizeof t && t.id) {
                S.recs[S.load_idx] = t;
                if (t.seq > S.seq) S.seq = t.seq;
            }
            S.load_idx++;
            return;
        } else {
            struct defrec d; u32 len = sizeof d;
            S.live = snapshot();
            if (Settings_Read(TAG_LIB, IDX_DEF, &d, &len) == 1 && len == sizeof d && d.magic == DEF_MAGIC) S.def = d.p;
            else { S.def = S.live; save_def(); }
            S.def_valid = 1;
            S.phase = PH_RUN;
        }
        return;
    default:
        break;
    }
    if (now - S.t_poll < 200) return;
    S.t_poll = now;

    if (FPGA_IsOperational()) {
        if (!S.fpga_up) {
            S.fpga_up = 1;
            if (now - S.t_down > 3000) { S.cur = -1; S.cur_id = 0; S.stable = 0; S.last_hash = 0; }
        }
    } else if (S.fpga_up) {
        S.fpga_up = 0; S.t_down = now;
    }
    if (!S.fpga_up) return;                      /* header buffer is only refreshed while the FPGA runs */

    poll_cart(now);
    cover_tick(now);

    if (S.pending && now - S.t_game > 1500 && FPGA_IsOperational()) {
        struct prof want = (S.pending == AP_GAME && S.cur >= 0) ? S.recs[S.cur].p : S.def;
        S.pending_was = S.pending;
        S.pending = AP_NONE;
        if (!peq(want, snapshot())) {
            int game = (S.pending_was == AP_GAME && S.cur >= 0);
            apply(want);
            if (S.live.oc != want.oc) {          /* overclock was reverted by the settle check */
                if (game) { S.recs[S.cur].p.oc = S.live.oc; save_rec(S.cur); }
                else { S.def.oc = S.live.oc; save_def(); }
            }
        } else { S.live = want; S.dirty = 0; }
        return;
    }
    if (S.dirty && !S.pending && now - S.t_dirty > 1000) {
        S.dirty = 0;
        on_dirty();
    }
}

/* H2: replaces `bl lv_timer_handler` in the overlay thread loop. */
u32 lib_timer_wrap(void)
{
    u32 r = lv_timer_handler();
    lib_tick();
    return r;
}

/* ------------------------------------------------------------------ UI: Experimental page */
static void build_rows(void)
{
    u8 order[MAXG]; int n = 0;
    for (int i = 0; i < MAXG; i++) if (S.recs[i].id) order[n++] = (u8)i;
    for (int a = 1; a < n; a++) {               /* most recently played first */
        u8 k = order[a]; int b = a - 1;
        while (b >= 0 && S.recs[order[b]].seq < S.recs[k].seq) { order[b + 1] = order[b]; b--; }
        order[b + 1] = k;
    }
    for (int r = 0; r < n; r++) {
        const struct rec *g = &S.recs[order[r]];
        char *o = S.rows[r], *end = o + ROWLEN - 1;
        if (order[r] == S.cur) o = put_s(o, end, "> ");
        o = put_n(o, end, g->name, 20);
        o = put_s(o, end, "  x");
        o = put_u(o, end, g->plays);
        if (g->flags & F_ON) {
            o = put_s(o, end, "  OC ");
            if (g->p.oc < 5) o = put_s(o, end, OCN[g->p.oc]); else o = put_u(o, end, g->p.oc);
            o = put_s(o, end, "  P");
            o = put_u(o, end, (u32)g->p.vp + 1);
        } else {
            o = put_s(o, end, "  (default)");
        }
        *o = 0;
        S.row_ptr[r] = S.rows[r];
        S.row_map[r] = (s8)order[r];
    }
    if (n == 0) {
        char *o = put_s(S.rows[0], S.rows[0] + ROWLEN - 1, "No cartridges played yet");
        *o = 0;
        S.row_ptr[0] = S.rows[0];
        S.row_map[0] = -1;
        n = 1;
    }
    S.rows_n = (u8)n;
    S.row_ptr[n] = 0;
    S.cv_shown = 0xff;                           /* row order may have changed: reload the cover */
}

/* ------------------------------------------------------------------ cover art
 * COVERS/<code>.BIN on the SD card: "M64C", u16 w, u16 h (both 80), then an 80x80 RGB565 plane and an
 * 80x80 A8 plane (LVGL RGB565A8). Made on a PC with tools/make_cover.py. Shown right of the selected row. */
/* Status readout in the heading, e.g. "Game Library [NSME ok]". Shows which step of the cover path ran. */
static void set_status(const char *code, const char *word, int num)
{
    char *o, *end;
    if (!S.hd_cfg || !S.hd_ctx) return;
    o = (char *)S.hd_cfg + 0x29; end = o + 34;
    o = put_s(o, end, "Game Library");
    if (word) {
        o = put_s(o, end, " [");
        if (code) { o = put_n(o, end, code, 4); o = put_s(o, end, " "); }
        o = put_s(o, end, word);
        if (num >= 0) o = put_u(o, end, (u32)num);
        o = put_s(o, end, "]");
    }
    *o = 0;
    if (lv_obj_is_valid(S.hd_ctx[0])) lv_obj_invalidate(S.hd_ctx[0]);
}

static int cover_load(const char *path)
{
    const u32 *hdr = (const u32 *)S.cv_raw;
    u32 got = 0;
    int ok = 0, e = f_open(S.cv_fil, path, 1);
    if (e) return (e == 4 || e == 5) ? 0 : -e;   /* FR_NO_FILE / FR_NO_PATH: just no cover; else -FRESULT */
    if (f_read(S.cv_fil, S.cv_raw, CV_BYTES + 8, &got) == 0 && got == CV_BYTES + 8
        && hdr[0] == CV_MAGIC && hdr[1] == (CV_W | (CV_H << 16))) ok = 1;
    f_close(S.cv_fil);
    return ok;
}

static void cover_tick(u32 now)
{
    u32 *cfg = S.tbl_cfg;
    u32 sel;
    int slot, y, have = 0, r = 0;
    if (!S.cv_img) return;
    if (!lv_obj_is_valid(S.cv_img)) { S.cv_img = 0; S.cv_lbl = 0; S.tbl_cfg = 0; S.hd_cfg = 0; return; }   /* page was closed */
    sel = cfg[9];
    if (sel >= S.rows_n) sel = 0;
    if (sel != S.cv_last) { S.cv_last = (u8)sel; S.cv_stable = 0; return; }
    if (S.cv_stable < 1) { S.cv_stable++; return; }                 /* selection must rest for ~0.4 s */
    if (sel == S.cv_shown || now < S.cv_retry) return;
    S.cv_shown = (u8)sel;
    slot = S.row_map[sel];
    if (slot >= 0 && S.recs[slot].code[0]) {
        char *o = put_s(S.cv_path, S.cv_path + sizeof S.cv_path - 1, "COVERS/");
        o = put_n(o, S.cv_path + sizeof S.cv_path - 1, S.recs[slot].code, 4);
        o = put_s(o, S.cv_path + sizeof S.cv_path - 1, ".BIN");
        *o = 0;
        have = 1;
        if (!SD_MOUNTED) r = -100;
        else if (tx_mutex_get(MTX_FW_SYSTEM, 0)) r = -101;              /* firmware is using the card: wait */
        else {
            if (tx_mutex_get(MTX_CFG_FILE, 0)) r = -101;
            else { r = cover_load(S.cv_path); tx_mutex_put(MTX_CFG_FILE); }
            tx_mutex_put(MTX_FW_SYSTEM);
        }
        if (r < 0) {                                                    /* SD not ready: back off */
            S.cv_retry = now + (r == -101 ? 1000 : 10000); S.cv_shown = 0xff; have = 0;
            if (r == -100) set_status(S.recs[slot].code, "no SD", -1);
            else if (r == -101) set_status(S.recs[slot].code, "SD busy", -1);
            else set_status(S.recs[slot].code, "SD err ", -r);
        } else {
            set_status(S.recs[slot].code, r ? "ok" : "no file", -1);
        }
    } else if (slot >= 0) {
        set_status(0, "no code", -1);
    } else {
        set_status(0, 0, -1);
    }
    if (r == 1) {
        y = (int)sel * ROW_H - (CV_H - ROW_H) / 2;                  /* centred on the row, kept inside the table */
        if (y > (int)S.rows_n * ROW_H - CV_H) y = (int)S.rows_n * ROW_H - CV_H;
        if (y < 0) y = 0;
        lv_image_set_src(S.cv_img, S.cv_dsc);
        lv_obj_align_to(S.cv_img, S.cv_tbl, LV_ALIGN_TOP_RIGHT, 0, y);
        lv_obj_invalidate(S.cv_img);
    } else if (have) {                                              /* tell the user which file would be used */
        lv_label_set_text(S.cv_lbl, S.cv_path);
        lv_obj_align_to(S.cv_lbl, S.cv_tbl, LV_ALIGN_TOP_RIGHT, 0, (int)sel * ROW_H + 2);
    }
    lv_obj_set_flag(S.cv_img, LV_FLAG_HIDDEN, r != 1);
    lv_obj_set_flag(S.cv_lbl, LV_FLAG_HIDDEN, !(have && r != 1));
}

/* Key handler installed on the library table (widget +0x20). Key codes: 0x81 A, 0x82 B, 0x83 Z,
 * 0x84 L, 0x85 R, 0x86 START, 0x87..0x8a d-pad U/D/L/R, 0x8b..0x8e C, 0x8f/0x90 encoder, 0x91 encoder press.
 * A (or encoder press) toggles the selected game's per-game profile; everything else is the stock table. */
static void toggle_row(void **ctx);
void *lib_table_key(u32 key, void **ctx)
{
    if (key == 0x81 || key == 0x91) { toggle_row(ctx); return ctx; }
    return MRW_Table_Key(key, ctx);
}

static void toggle_row(void **ctx)
{
    u32 *cfg = S.tbl_cfg;
    u32 sel;
    int slot;
    if (!cfg || S.phase != PH_RUN) return;
    sel = cfg[9];                               /* cfg+0x24: selected row */
    if (sel >= S.rows_n) return;
    slot = S.row_map[sel];
    if (slot < 0) return;
    S.recs[slot].flags ^= F_ON;
    save_rec(slot);
    if (slot == S.cur) { S.pending = (S.recs[slot].flags & F_ON) ? AP_GAME : AP_DEF; S.t_game = tx_time_get() - 1500; }
    build_rows();                               /* same row count: only texts change */
    if (ctx && ctx[0]) lv_obj_invalidate(ctx[0]);
}

/* H4: replaces `bl MRW_Label_Create` for PgExp's "Coming Soon" label. Text is inline at cfg+0x29. */
int lib_label_create(void **ctx, u8 *cfg)
{
    static const char T[] = "Game Library";
    int r;
    cmem(cfg + 0x29, T, sizeof T);
    r = MRW_Label_Create(ctx, cfg);
    S.hd_cfg = (r == 1) ? cfg : 0;
    S.hd_ctx = ctx;
    return r;
}

/* H5: replaces `bl MRW_Table_Create` for PgExp's "coming soon" feature table. */
int lib_table_create(void **ctx, u32 *cfg)
{
    int r;
    build_rows();
    /* +0x08 = callback for B. Use the page's "back" callback, which PgExp stored in the
     * Overclocking dropdown cfg (+0x14); that cfg sits 0xb8 bytes before this one. */
    cfg[2] = *(u32 *)((u8 *)cfg - 0xa4);
    cfg[3] = (u32)S.row_ptr;                    /* +0x0c NULL-terminated string array */
    cfg[6] = 1;                                 /* +0x18 one column */
    cfg[7] = 0x00ffffff;                        /* +0x1c text colour (was grey 0x737373) */
    S.tbl_cfg = cfg;
    r = MRW_Table_Create(ctx, cfg);
    if (r == 1) {
        void *page = lv_obj_get_parent(ctx[0]);
        ctx[8] = (void *)((u32)lib_table_key | 1u);   /* widget +0x20: key handler (was 0x0802f265) */
        S.cv_img = 0; S.cv_lbl = 0;
        if (page) {
            void *img = lv_image_create(page), *lbl = img ? lv_label_create(page) : 0;
            if (img && lbl) {
                S.cv_dsc[0] = 0x19 | (0x14 << 8);              /* magic, cf = RGB565A8 */
                S.cv_dsc[1] = CV_W | (CV_H << 16);
                S.cv_dsc[2] = CV_W * 2;                        /* stride */
                S.cv_dsc[3] = CV_BYTES;
                S.cv_dsc[4] = (u32)S.cv_raw + 8;
                lv_obj_set_flag(img, LV_FLAG_HIDDEN, 1);
                lv_obj_set_flag(lbl, LV_FLAG_HIDDEN, 1);
                lv_obj_set_style_text_color(lbl, 0x00a0a0a0, 0);
                S.cv_tbl = ctx[0];
                S.cv_lbl = lbl;
                S.cv_shown = 0xff; S.cv_last = 0xff;
                S.cv_img = img;
            }
        }
        if (!S.cv_img) set_status(0, "no obj", -1);
    }
    return r;
}

/* H6: replaces `strd r4, r4, [r5, #8]` at the end of PgExp's focus setup.
 * r4 = Overclocking dropdown widget, r5 = page focus record {+8 first, +0xc last}.
 * Widget neighbours: +0x08 up, +0x0c down, +0x18 prev, +0x1c next. Table widget = r4 + 0xb0. */
__attribute__((naked)) void lib_nav_tail(void)
{
    __asm__(
        "add.w r0, r4, #0xb0\n"
        "str r4, [r5, #8]\n"
        "str r0, [r5, #12]\n"
        "str r0, [r4, #0x0c]\n"                 /* dropdown.down = table */
        "str r0, [r4, #0x1c]\n"                 /* dropdown.next = table */
        "str r4, [r0, #0x08]\n"                 /* table.up   = dropdown */
        "str r4, [r0, #0x18]\n"                 /* table.prev = dropdown */
        "bx lr\n");
}
