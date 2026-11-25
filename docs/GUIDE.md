# ModRetro M64 firmware RE, modify, and flash

Technical reference for reverse-engineering and modifying the menu firmware of a ModRetro M64 **that you own**. Use only the facts in this document. Do not invent offsets, CRC formulas, USB IDs, or flash commands. Do not crack or forge ModRetro's cryptographic signature. This repository does not ship firmware images or vendor key material.

Offsets, CRC formulas, and the signature *scheme* below were verified against official stock firmware **1.26.4**. Packaging, mapping, a same-length menu-string edit, and custom images on two UI screens (the boot screen and the "No Cartridge Detected" screen, via appended LVGL images + Thumb code caves) have all been verified on a real 1.26.4 unit. For image/graphics mods, see [UI image mods](#ui-image-mods-verified-on-device). A larger add-on written in C (game library, per-game profiles, cover art from the SD card) has also been seen working on a real unit: see [Code add-ons in C](#code-add-ons-in-c-verified-on-device) and [`addon/`](../addon/README.md).

## Agent protocol (build, then flash)

When an assistant or script is doing this work on a device you own:

1. **Build only first.** Do not touch any USB/DFU device (not even `dfu-util -l`) until the build is finished and verified.
2. Verify the build: only the intended bytes changed, the vector table is intact (SP `0x20020000`, Reset `0x08014F71`), and the size is ≤ 1,048,576 bytes (slot A). Render a preview PNG from the built image. Document the offsets and bytes in a `*_CHANGES.md` file next to the output.
3. Report the output's **file name, SHA-256 and byte size**. Then tell the user to enter DFU (**menu + power ~15 s on the power USB-C port, until the screen goes dark**) and **stop and wait** for them to say it is connected.
4. After they confirm: `dfu-util -l` → RDP read (`0xAA`) → full-chip backup → re-check the image's SHA-256 → flash. Do not skip the RDP read or the backup because a previous session already did them.
5. Ask the user to check the result on the device. Name the rollback `.bin` (the previous working build, then `mcu_stock.bin`).

---

## Hardware

- Handheld: **ModRetro M64**
- MCU: **STM32H7A3ZIT6** (Cortex-M7)
- Internal flash: **2 MB** at `0x08000000`, **256 sectors × 8 KB**
- Dual-bank layout:
  - Bank 1 / slot A: `0x08000000` — this is the **booted** image
  - Bank 2 / slot B: `0x08100000` — fallback copy
- FPGA: **Xilinx XCAU15P** (UltraScale+)
- **No secure boot.** `Reset_Handler` is a plain C-runtime startup. The cryptographic signature is checked only by the SD/OTA **updater**, never at boot over `0x08000000`. A raw DFU flash of a modified slot-A image therefore just runs.

Official hardware files (schematics, mechanical CAD) are published by ModRetro and are **not** redistributed here:

- https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg
- https://github.com/ModRetro/oss-m64-console

---

## M64.BIN container

Obtain the official container from ModRetro only (do not commit it):

- Web updater: https://tools.modretro.com/updater/
- SD-card builds: https://tools.modretro.com/downloads/m64-console/

Stock release **1.26.4**, file size **7,717,428 bytes** (~7.7 MB).

Stock SHA-256 (recompute and keep this as the reference; this is a fingerprint of the official file, not the file itself):

```
2bf499c33d5ebc8a0ab3393441b10962f812132bf1bfc12d4da4ce3964a69b3e
```

Layout (only the MCU section is needed for a menu-firmware flash):

- Header, then MCU section, then FPGA / other payload
- MCU section: file offset `0x118` .. `0xBE0A8` (end exclusive)
- Payload size: `0xBDF90` bytes (778,128 bytes)
- That payload maps 1:1 to virtual address `0x08000000`
- Extract those bytes (see `scripts/extract_slota.py`) to produce the raw `.bin` you flash with DFU

See [`firmware/README.md`](../firmware/README.md) for the local filenames this toolkit expects (`mcu_stock.bin`, `mcu_mod.bin`, and so on).

---

## Integrity (recompute after any edit)

Two integrity fields must be rewritten after any change to the container. `scripts/repack.py` reproduces both and **asserts** them against the stock 1.26.4 values before applying an edit.

### Section CRC32

- Algorithm: **JAMCRC** = zlib/IEEE CRC32 of the payload, then XOR `0xFFFFFFFF` (i.e. `zlib.crc32(payload) ^ 0xFFFFFFFF`)
- Input: payload bytes `0x118` .. `0xBE0A8`
- Stored little-endian at file offset `0xA5` (4 bytes)
- Stock 1.26.4 value: `0x3D847C84`

### Header CRC16

- Algorithm: **CRC-16 CCITT-FALSE** (init `0xFFFF`, poly `0x1021`, no final XOR)
- Input: header bytes `0x98` .. `0x116` (end exclusive; 0x7E bytes starting at the MFW1 header)
- Stored little-endian at file offset `0x116` (2 bytes)
- Stock 1.26.4 value: `0x7536`

If either stock assertion in `repack.py` fails, stop — the formula is wrong, or the input image is not stock 1.26.4.

---

## Signature (SD-updater path only)

**Do not crack or forge ModRetro's key. This project does not ship vendor key material.**

The official updater verifies an educational, fully described scheme:

- **ECDSA P-256** (secp256r1) over **SHA-256** of the **entire** `M64.BIN` file with **only** the 64-byte `r||s` field (file `0x58` .. `0x98`) zeroed
- 33-byte compressed P-256 public key at file offset `0x36` (TEX+6). This key **is** covered by the hash
- `r` at `0x58`, `s` at `0x78`

The on-device verifier (around VA `0x0800d118`) branches on a dev-mode getter:

- Dev-mode **OFF**: the updater requires the vendor's hard-coded key (not included in this repository)
- Dev-mode **ON**: the updater validates against the public key embedded in the image

`scripts/sigmap.py`, `scripts/sign.py`, and `scripts/verify_sig.py` implement this scheme so you can **self-sign with a key you generate**. A self-signed image:

- Verifies OK under the key you embedded
- Is rejected when checked against the vendor key
- Is accepted by the official updater **only** when dev-mode is ON (Route B)

The DFU flash path (Route A) does **not** go through this check, because there is no secure boot. That is why a raw slot-A flash of a modified image runs, without any need to touch the signature.

---

## Tools

All Python helpers live in `scripts/`. Several helpers open `M64.BIN` from the **current working directory** — copy or symlink the official container there, or run from a folder that already contains it.

Python dependencies (see `scripts/requirements.txt`):

```
python -m pip install -r scripts/requirements.txt
```

(`capstone`, `ecdsa`, and `pillow`.)

### `m64dis.py` (Capstone, THUMB)

Subcommands:

| Command | What it does |
|---|---|
| `str <text>` | Find strings and print file offset + VA |
| `xref <hexVA>` | Find little-endian literal-pool references to that VA |
| `d <hexfileoff> <nbytes>` | Disassemble `nbytes` starting at a **file** offset |

Example:

```
python scripts/m64dis.py str "M64.BIN Ready"
python scripts/m64dis.py xref 080xxxxx
python scripts/m64dis.py d 8c900 80
```

Address conversion used by the script:

- VA = `0x08000000 + (file_off - 0x118)`
- file_off = `VA - 0x08000000 + 0x118`

### `repack.py`

Applies an in-place same-length string edit and recomputes both CRC fields. As shipped, it is a worked example for stock 1.26.4: it patches file `0x08c918` (`M64.BIN Ready` → `CUSTOM READY!`) and writes `M64_mod.BIN`. For a new string mod, edit the `STR_OFF` / `OLD` / `NEW` constants (keep `len(OLD) == len(NEW)` and preserve the trailing NUL) and run it against a stock `M64.BIN`.

### `sign.py` / `verify_sig.py` / `sigmap.py`

Route B only. Generate your own P-256 key (for example `openssl ecparam -name prime256v1 -genkey -out mykey.pem`). Never commit that file.

```
python scripts/sign.py <in.BIN> <out.BIN> <privkey.pem>
python scripts/verify_sig.py <image.BIN>
```

`sigmap.py` holds the layout constants and the "hash the whole file with `r||s` zeroed" digest. `verify_sig.py` checks the image against the **embedded** public key, not against any vendor key.

### `extract_slota.py`

Slices container bytes `0x118` .. `0xBE0A8` out to a raw slot-A `.bin`.

```
python scripts/extract_slota.py firmware/M64_stock.BIN firmware/mcu_stock.bin
```

### Raw slot-A / UI image helpers (need `pillow` for the image ones)

These work on a **raw slot-A `.bin`** (VA = `0x08000000 + offset`, no `0x118` shift), not on the container.

| Script | What it does |
|---|---|
| `rawdis.py` | `M64BIN=<file.bin> python scripts/rawdis.py str\|xref\|d\|dsc\|w ...` — like `m64dis.py` but VA-based, and it annotates `ldr pc` literals with their value, any string they point at, and any `lv_image_dsc_t` (`<dsc cf=.. WxH>`) |
| `make_lvgl_image.py` | PNG → LVGL 9 `lv_image_dsc_t` (28 B) + payload. Formats: I4, I8, A8, RGB565, RGB565A8, ARGB8888. `--data-va` fills in the data pointer |
| `sprite_prep.py` | Cuts one frame out of a sprite sheet. It keys a flat light background (border flood fill), scales with premultiplied Lanczos, and can add a 1 px outline. Output is an RGBA PNG. Omit `--box` to use the whole image |
| `screen_image.py` | `add`: appends a Thumb cave + descriptor + payload and redirects one `bl` in a screen's create function, adding a new image at (x, y). `resize`: changes the size/position/pixels of an image that `add` already placed. Both print a byte diff, cave disassembly and SHA-256, and assert that nothing else changed |
| `lvfont.py` | Library: decodes LVGL `fmt_txt` fonts and image descriptors straight out of the firmware, for rendering faithful screen previews |

### Windows DFU helpers (run from the toolkit root)

These assume `dfu-util` is available as `dfu/dfu-util.exe` or `dfu/dfu-util-static.exe` relative to the toolkit root, or you can invoke `dfu-util` yourself as shown in [`FLASH_HOWTO.md`](FLASH_HOWTO.md). Install dfu-util from http://dfu-util.sourceforge.net/ (this repo does not bundle third-party binaries).

- `scripts/backup.bat` — read option bytes (RDP), then full-chip backup to `firmware/chip_backup_YYYYMMDD.bin`
- `scripts/flash.bat <file.bin>` — `dfu-util -a 0 -s 0x08000000:leave -D <file.bin>`
- `scripts/recover.bat` — reflash `firmware/mcu_stock.bin` (you must have extracted this first)

---

## UI image mods (verified on device)

Custom images have been added to the boot screen and the "No Cartridge Detected" screen on a real 1.26.4 unit, then DFU-flashed and confirmed. The technique is an appended LVGL image plus a small Thumb code cave; `screen_image.py` implements it (`add` for a new image, `resize` to change size or position later). Verified builds grew past the 778,128-byte stock extract (into the ~850–880 KB range) and stayed well under the 1 MB slot-A limit.

### Facts you can rely on (1.26.4 slot A)

- UI = **LVGL 9.x**, display **320×240**, display color format ARGB8888. Each screen is a hand-written C create function, so positions are Thumb immediates, not data.
- **Raw slot A may grow past 778,128 bytes.** Append new data after the image, 4-byte aligned. The hard limit is **1,048,576 bytes** (bank 1 ends at `0x080FFFFF`). The vector table is at the start (SP `0x20020000`, Reset `0x08014F71`) and must stay identical. Nothing checks a CRC or signature at boot. These raw images are **not** spliced back into `M64.BIN`: the larger MCU section would shift the FPGA section and the TOC.
- `lv_image_dsc_t` (28 bytes, LE): `+0 magic 0x19`, `+1 cf`, `+2 flags u16`, `+4 w u16`, `+6 h u16`, `+8 stride u16`, `+10 reserved u16`, `+12 data_size u32`, `+16 data ptr u32`, `+20/+24 reserved`. **data_size is at +12, not +16.** Getting that wrong once broke a diff check.
- Color formats: I4 `0x09` (BGRA palette, high nibble = left pixel), I8 `0x0A`, A8 `0x0E`, ARGB8888 `0x10`, RGB565 `0x12`, **RGB565A8 `0x14`**. RGB565A8 = RGB565 plane (stride = w×2) followed by an A8 plane (w per row), so data_size = w×h×3. Use RGB565A8 for full-color art: I4/I8 posterize it.
- LVGL entry points: `lv_obj_center` `0x0803758C`, `lv_obj_align(obj, align, x, y)` `0x08035FF8`, `lv_image_create(parent)` `0x08050394`, `lv_image_set_src(img, src)` `0x08050888`. `LV_ALIGN_TOP_LEFT` = 1, `TOP_MID` = 2, `CENTER` = 9.
- Thumb `BL` reaches ±16 MB, so a cave anywhere in slot A can call any of these. `screen_image.py` encodes the branch.

### Screen maps

**Scr_Boot** (olive `#47704C` bg). Create `0x0801E5D8`, setup `0x0801E040`. Objects are in `gp*` at SRAM `0x200119D8` (+0 logo, +4 shine wrapper, +8 shine, +0xC boot msg). Logo: I4 154×35 descriptor `0x080B02D0`. Its literals are at `0x0801E190` (set_src + wrapper size) and `0x0801E2C0` (shine width). Its alpha mask (A8 154×35, descriptor `0x080B0DB4`) comes right after the pixel data, so the logo **cannot grow in place**. A verified boot-screen mod appended one composite RGB565A8 image (wordmark on top + a character sprite) at `0x080BDF9C`, with both literals repointed to it. The two `bl lv_obj_center` at `0x0801E05C` / `0x0801E072` go to a cave doing `lv_obj_align(obj, TOP_MID, 0, 8)`. The boot-message y immediate at `0x0801E0E6` changes `#0x3C` → `#0x48` so the text clears the taller image. The shine keeps working over the wordmark area.

**Scr_NoCart** ("No Cartridge Detected", black bg). Create `0x0801FA54`. Module struct at `0x2001207C`: +0 label, **+4 screen obj**, +0xC4 console icon, +0xC8 LED bar, +0xD0 footer. Icon: I4 56×33 descriptor `0x080B4BA0`, centered → x 132..187, y 103..135. Label (text `0x08091B81`, font `0x080AD608`, 13 px line): x 110..210, y 148..160, aligned 12 px below the icon. Footer `MRW_Footer`: y 212..239. Nothing on this screen moves.
- Hook: `0x0801FBD4` `bl lv_obj_center(console icon)`. At that point **r4 = module struct**. The x/y immediates in the cave are at cave +26 / +28. On a build that already had a boot-screen append, a verified No-Cartridge cave landed at `0x080D05E4` (descriptor `0x080D060C`, data `0x080D0628`). On a clean stock extract the cave lands at the then-current 4-byte-aligned end; `screen_image.py add` prints the VA.
- Free area for art: left of the label/icon, x 0..109, y 0..211. One verified placement was 46×107 at (44, 66) — 20 px from the label, 39 px from the footer, centered vertically on the icon.
- On a black screen, dark art disappears. A 1 px bright outline (`sprite_prep.py --outline 0,215,75,215`, or any high-contrast color) fixed that.

### Recipe: add an image to a screen

1. Find the screen's create function: `rawdis.py str "<visible text>"` → `xref` the string VA → `d` around the literal. Note the module struct (usually in r4) and where the screen object is stored.
2. Pick a `bl` hook in the create function **after** the screen object is stored. A good choice is the final `lv_obj_center`/`lv_obj_align` of an existing widget. At the hook, r4 must still hold the struct. Check that the original call takes ≤ 4 args (the cave forwards r0–r3 untouched).
3. Work out the stock layout from the code (sizes, align calls), list every object's box, and choose a free box.
4. `sprite_prep.py` → RGBA PNG, then `screen_image.py add BASE OUT png --x X --y Y --hook <bl VA> --orig <its target> [--screen-field 4]`.
5. Render a preview from the **built** image (decode icon/fonts/sprite with `lvfont.py`, read x/y back from the cave) and assert no overlaps.
6. To change it later: `screen_image.py resize OUT OUT2 new.png --x .. --y .. --cave <cave VA>`. Only the two immediates, the descriptor and the payload change, and the file is truncated or extended after the payload.

Cave semantics: `push {r4,lr}; bl orig; ldr r0,[r4,#field]; bl lv_image_create; mov r4,r0; cbz r0,done; ldr r1,=dsc; bl lv_image_set_src; mov r0,r4; movs r1,#1; movs r2,#x; movs r3,#y; bl lv_obj_align; done: pop {r4,pc}`. If the allocation fails, the cave skips the image and the screen is stock. The new image is a child of the screen and is freed with it. x/y are limited to 0..255 (movs imm8).

### Gotchas

- Descriptor field offsets (see above): check `data_size` at +12.
- `dfu-util` prints `Error during download get_status` **after** `Submitting leave request...`. That is harmless: the MCU has already reset into the new firmware. The flash is good if `Download done.` / `File downloaded successfully` appeared before it.
- After a modded image is installed, a fresh backup's first bytes match **the currently booted custom build**, not `mcu_stock.bin`. Compare against the last flashed `.bin` (its full length).

---

## Code add-ons in C (verified on device)

For anything bigger than a cave, write C, compile it with `arm-none-eabi-gcc -mcpu=cortex-m7 -mthumb -Os -ffreestanding -fno-builtin`, link it at the first 4-aligned address after the raw image, and redirect existing `bl` instructions to it. Call firmware functions through absolute Thumb addresses (`((ret(*)(args))(addr|1))`). Allow no `.data` (assert it in the linker script). Test the compiled blob in Unicorn with Python models of the firmware calls before asking for a flash. The first add-on built this way is the game library in [`addon/`](../addon/README.md): library, per-game profiles and cover art. `addon/build.py` and `addon/emu_test.py` are the template for the build and the emulator test.

Facts found for it (1.26.4):

- **Cart header:** FPGA_Supervisor keeps the inserted cartridge's 64-byte ROM header at RAM `0x20006DCE`. It is read from FPGA PSRAM address 0 at `0x0800ADBC` while a cart is detected and zeroed on removal. The internal name is at +0x20.
- **Settings store:** TLV records in an 8 KB EEPROM partition. `Settings_Read(tag, idx, buf, &len)` is `0x0801462C` and `Settings_Write(tag, idx, buf, len)` is `0x080146B0`. Both return 1 on success, and a write appends a missing record. Stock tags are 0x01-0x16 (0x04 StretchMode, 0x05 ScalarMode, 0x09 VideoProfile, 0x0C ProfileCfg[idx], 0x0D ImageSize, 0x10 OverclockLevel, 0x12 ExpansionPak, 0x13 Region, 0x14 LowLatency, 0x15 AdvDisplayCfg[idx]). Tag numbers are not validated, so an add-on can use its own (0x60 is taken by the library).
- **Applying settings like the menu does:** the "set" callbacks take a `u32 *`: video profile `0x08011A64`, image size `0x08011C10`, stretch `0x08011BBC`. Overclock: Cpak flush `0x0801C1EC` -> apply level `0x08011DCC` -> settle check `0x0800882C(u8 *passed)` -> store `0x08013186` -> post event 0x0F (`0x08004BE4`). Getters: `0x0801315A` OC, `0x08012FD4` profile, `0x080130AC` image size, `0x08012EA4` stretch. `FPGA_IsOperational` is `0x0800AEC8`.
- **Running code every UI frame:** the overlay thread loop at `0x080142A0` does lock -> `bl lv_timer_handler` (`0x080142A8`) -> unlock -> sleep. Wrapping that `bl` gives a tick in the LVGL thread, inside the render lock. `tx_time_get` is `0x0807E264` (1 tick = 1 ms).
- **Free RAM:** AXI SRAM `0x240EF130`-`0x240FFFFF` is past the stock `.bss` and unreferenced. It is not zeroed at reset: hook `bl __libc_init_array` at `0x08014FAE` to clear what you use. The gap after the DTCM `.bss` (`0x2001C818`-`0x20020000`) is in use, so do not touch it.
- **UI key codes:** 0x81 A, 0x82 B, 0x83 Z, 0x84 L, 0x85 R, 0x86 START, 0x87-0x8A d-pad U/D/L/R, 0x8B-0x8E C U/D/L/R, 0x8F/0x90 encoder, 0x91 encoder press. A widget's key handler is at widget +0x20 and is called as `(key, widget)`.
- **Focus links:** widget +0x08 up, +0x0C down, +0x10 left, +0x14 right, +0x18 prev, +0x1C next (setter `0x080255D8`). A page records its first/last focusable widget at page-record +8/+0xC.
- **Experimental page (PgExp):** create `0x0802510C`, state `0x200167D8`. Overclocking dropdown +0x5C, "Coming Soon" label +0xB4 (`bl MRW_Label_Create` at `0x0802521C`, text inline at cfg+0x29), feature table +0x10C (`bl MRW_Table_Create` at `0x0802526C`). `MRW_Table` cfg: +0x08 B-callback, +0x0C NULL-terminated string array (max 20), +0x10 width, +0x18 columns, +0x1C colour, +0x24 selected row. PgExp is the table's only stock user and never focuses it.
- **SD card files (verified on device):** FatFs `f_open(FIL*, path, 1)` `0x08006314`, `f_read(FIL*, buf, n, &got)` `0x080064D0`, `f_close` `0x0800684A`; `FIL` is 0x228 bytes; paths are relative to the card root. FatFs has **no lock of its own** here. An add-on must hold the firmware's two file mutexes while it touches the card: FW_System `0x20008210` (M64.BIN verify/update) and FWSettings `0x200078C4` (CHANNEL.TXT), taken with `tx_mutex_get(mutex, 0)` `0x0807E6A0` (0 = got it) and released with `tx_mutex_put` `0x0807E6F4`. An unlocked read collided with the background M64.BIN check and made the console report "Corrupt M64.BIN". Only read when the mounted flag `0x2000C514` is set.
- **Plain LVGL objects on a ModRetro page work:** `lv_image_create` `0x08050394` / `lv_image_set_src` `0x08050888` with an RGB565A8 descriptor in RAM, `lv_obj_align_to` `0x080371BC`, `lv_obj_update_flag(obj, flag, en)` `0x080349F0` (HIDDEN = 1), `lv_obj_is_valid` `0x08034A78`, `lv_obj_set_style_text_color` `0x08039934`.
- **Event IDs** (name table `0x08099DFC`): 0x0B CartDetected, 0x0C CartNotDetected, 0x0F Cpak_Reload, 0x2D GameActive, 0x2E GameNotActive, 0x40 Overlay_Hide, 0x42 Overlay_ResetGame, 0x43 Overlay_ToggleMenu.

---

## Mod workflow

1. Start from official stock `M64.BIN`. Keep a reference copy and its SHA-256 (`2bf499c3…a69b3e` for 1.26.4).
2. Locate the target with `m64dis.py` (`str`, then `xref` / `d` as needed).
3. Edit in place, **keeping the original byte length**. For strings: keep the NUL terminator; do not shift any later pointers.
4. Run `repack.py` to recompute and write both CRC fields. Confirm that only the intended bytes changed (the string and the two CRC fields).
5. Extract slot-A bytes `0x118` .. `0xBE0A8` into a raw `.bin` mapped at `0x08000000`.
6. DFU-flash that raw image (Route A), after the safety steps below.

---

## DFU flash (Route A — no extra hardware)

### Enter DFU

On the **power** USB-C port: hold **menu** + press **power** for about **15 seconds**, then release menu. The device enumerates as USB VID:PID **`0483:df11`** ("DFU in FS Mode"). Use a data-capable cable.

### Windows driver

- **UsbDk does not work** with typical Windows `dfu-util` builds.
- Use **Zadig** (https://zadig.akeo.ie/) to install **WinUSB** on the "DFU in FS Mode" device.
- Linux / macOS: `dfu-util` talks to the device directly; no Zadig step.

### Confirm the device

```
dfu-util -l
```

You should see three alt settings:

- alt 0: `@Internal Flash  /0x08000000/256*08Kg`
- alt 1: `@Option Bytes    /0x5200201C`
- alt 2: `@OTP             /0x08FFF000`

### Safety: read RDP first (read-only)

```
dfu-util -a 1 -s 0x5200201C -U firmware/optbytes_read.bin
```

Decode **FLASH_OPTSR_CUR**, which is the 32-bit little-endian word at **offset +4** in that dump. The **RDP field is bits [15:8]** of that word:

| RDP byte | Level | Action |
|---|---|---|
| `0xAA` | Level 0 | Safe to flash |
| `0xCC` | Level 2 | **NEVER flash** (can permanently lock the MCU) |
| anything else | Level 1 | A write will mass-erase the flash — do not proceed unless that is explicitly intended |

Only proceed if the RDP byte is `0xAA`.

### Back up every time

```
dfu-util -a 0 -s 0x08000000 -U firmware/chip_backup.bin
```

Compare the backup against the **last flashed** raw slot-A `.bin` at that file's full length. If stock is booted, the first 778,128 bytes should equal `firmware/mcu_stock.bin`. If a previous custom build is booted (a UI-image mod can be larger than 778,128 bytes, up to 1,048,576), compare against that build, not stock. `scripts/backup.bat` wraps the RDP read and this backup.

### Flash (consequential — confirm before writing)

```
dfu-util -a 0 -s 0x08000000:leave -D firmware/mcu_mod.bin
```

- `:leave` reboots the MCU out of DFU when the write finishes
- An `Invalid DFU suffix` warning is **harmless** (raw `.bin` files have no DFU suffix)
- `Error during download get_status` right after `Submitting leave request...` is also **harmless** (the device has already reset)
- Raw images can be anything up to 1,048,576 bytes; appended UI mods make them longer than 778,128
- Verify the change on the device after the reboot / a power-cycle

The worked-example status string lives on **About → Update from SD Card** and only appears when an `M64.BIN` is present in the SD-card root.

---

## Recovery

Re-enter DFU, then:

```
dfu-util -a 0 -s 0x08000000:leave -D firmware/mcu_stock.bin
```

Or flash a full `chip_backup.bin` the same way if you need the entire 2 MB chip restored.

The STM32 **ROM bootloader cannot be erased**, so DFU recovery keeps working unless RDP is at Level 2. Slot B at `0x08100000` also keeps a fallback copy of the stock image.

`scripts/recover.bat` reflashes `firmware/mcu_stock.bin`.

---

## Route B (alternate): dev-mode self-sign via the official updater

Use this only if you specifically want the official SD/OTA updater to accept a container you signed with **your own** key. It needs a teardown and a serial adapter. It is non-destructive (it uses the firmware's own update flow).

1. Enable dev-mode with the debug-shell command `fw_devmode on` (handler writes NVS id `0x0B`; it persists across reboot).
2. Debug shell: **USART2**, 115200 8N1, on connector **J15** ("MCU DEBUG SIGNALS"), Samtec **FTSH-104-01-F-DV** (1.27 mm):
   - pin 1 = 3.3 V
   - pin 4 = RX
   - pin 5 = TX
   - pin 6 = GND
   - Designed for an **FTDI TTL-232R-3V3** cable (USART2: TX = PA2 AF7, RX = PD6 AF7)
3. Generate a throwaway P-256 key and keep it out of git. Sign the full container: `python scripts/sign.py <in.BIN> <out.BIN> <privkey.pem>`
4. Install that container via the official SD updater (dev-mode ON so the embedded key is used)

This is **not** a way to produce an image that verifies as vendor-signed. A self-signed image is accepted only with dev-mode on.

---

## Safety rules

1. Read RDP before any write. Abort if the RDP byte is not `0xAA`.
2. Always take a full-chip backup before flashing, and check it.
3. The flash write is consequential — confirm before `-D` / `flash.bat` / `recover.bat`.
4. Never crack or forge ModRetro's signature. Never include vendor key material in this tree.
5. Keep string (and other in-place) edits the same length; preserve NULs; recompute both CRC fields.
6. Do not publish firmware binaries or any `.pem` keys.

When in doubt, recover with `scripts/recover.bat` and stop. You use these tools on your own hardware, at your own risk.
