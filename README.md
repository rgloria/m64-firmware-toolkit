# M64 Firmware Toolkit

Tools and documentation for reverse-engineering and modifying the **menu firmware** of a [ModRetro M64](https://modretro.com/products/m64) handheld **that you own**.

This is legitimate RE of owner hardware. It is **not** a crack of ModRetro's cryptographic signature, and this repository **does not ship firmware images or vendor key material**.

Two supported install paths are documented:

- **Route A (recommended):** raw USB-DFU flash of the MCU's internal flash. This works because the device has **no secure boot** — the signature is checked only by the SD/OTA updater, never at reset over `0x08000000`.
- **Route B (optional):** generate your own P-256 key, self-sign a container, enable the firmware's **dev-mode**, and install it with the official updater.

Never attempt to forge a signature under ModRetro's key.

## Quick start

A one-page cheat sheet is in [`CHEATSHEET.md`](CHEATSHEET.md). Full technical reference: [`docs/GUIDE.md`](docs/GUIDE.md). Command-by-command flash runbook: [`docs/FLASH_HOWTO.md`](docs/FLASH_HOWTO.md).

### 1. Install Python deps

```bash
python -m pip install -r scripts/requirements.txt
```

(`capstone`, `ecdsa`, and `pillow`.) You also need [dfu-util](http://dfu-util.sourceforge.net/) and, on Windows, [Zadig](https://zadig.akeo.ie/) to install the **WinUSB** driver on "DFU in FS Mode". UsbDk does **not** work with the usual Windows `dfu-util` builds.

### 2. Get official firmware (do not commit it)

Download `M64.BIN` from ModRetro:

- Web updater: https://tools.modretro.com/updater/
- SD-card builds: https://tools.modretro.com/downloads/m64-console/

Place a copy in your working directory as `M64.BIN` (and optionally a reference copy at `firmware/M64_stock.BIN`). See [`firmware/README.md`](firmware/README.md). Offsets and CRC assertions in this repo were verified against stock **1.26.4**.

### 3. Edit, repack, extract

```bash
# find a menu string (needs M64.BIN in the current directory)
python scripts/m64dis.py str "M64.BIN Ready"

# same-length patch + recompute CRCs (edit STR_OFF / OLD / NEW in scripts/repack.py)
python scripts/repack.py

# slice out the flashable slot-A image (778,128 bytes)
python scripts/extract_slota.py M64_mod.BIN firmware/mcu_mod.bin

# also keep a stock extract for rollback
python scripts/extract_slota.py M64.BIN firmware/mcu_stock.bin
```

### 4. Enter DFU, back up, flash

On the M64 **power** USB-C port: hold **menu**, press **power** for about 15 seconds, then release menu. The device enumerates as USB `0483:df11` ("DFU in FS Mode").

```bat
scripts\backup.bat
scripts\flash.bat firmware\mcu_mod.bin
```

`backup.bat` is read-only: it reads the RDP (readout-protection) level and dumps a full 2 MB chip backup. **Only flash if RDP is Level 0 (`0xAA`)**. A flash write is consequential — confirm you want it before running `flash.bat` or `recover.bat`. Rollback:

```bat
scripts\recover.bat
```

## Repository layout

| Path | Contents |
|---|---|
| `scripts/` | Python helpers and Windows DFU wrappers (see below) |
| `docs/GUIDE.md` | Hardware, container layout, CRCs, signature scheme, UI-image recipe, DFU, recovery, Route B |
| `docs/FLASH_HOWTO.md` | Connect / backup / flash / recover, command by command |
| `addon/` | Source of the **Game Library add-on** (library, per-game profiles, cover art, virtual Controller Paks), its build and emulator-test scripts, cover tools, and [install + flash instructions](addon/README.md) |
| `skills/m64-firmware/` | Claude Code skill: when to trigger, and the build-verify-flash protocol |
| `firmware/` | Local images only. Binaries are gitignored. |
| `examples/` | Worked starting-point prompts for AI-assisted mods |
| `CHEATSHEET.md` | What is supported, how to use it on the console, and the get-started commands |
| `LICENSE` | GPL-3.0 |

### Scripts

| Script | Purpose |
|---|---|
| `m64dis.py` | Find strings, literal-pool xrefs, and disassemble THUMB (container file offsets) |
| `rawdis.py` | Same idea for a raw slot-A `.bin` (`M64BIN=<file.bin>`); VA-based, annotates image descriptors; also lists a function's callers, the debug-shell command table, event names, and RAM references |
| `make_lvgl_image.py` | Pack a PNG into an LVGL 9 `lv_image_dsc_t` + payload (for image/screen mods) |
| `sprite_prep.py` | Cut a frame from a sprite sheet, key the background, scale, optional 1 px outline |
| `screen_image.py` | Add (`add`) or move/resize (`resize`) an LVGL image on a screen in a raw slot-A `.bin` |
| `lvfont.py` | Library: decode LVGL `fmt_txt` fonts and image descriptors from a firmware image (for previews) |
| `repack.py` | Same-length string edit + section CRC32 + header CRC16 |
| `extract_slota.py` | Slice container bytes `0x118..0xBE0A8` to a raw slot-A `.bin` |
| `sigmap.py` / `sign.py` / `verify_sig.py` | Route B: hash scheme, self-sign with **your** P-256 key, verify |
| `backup.bat` | Read option bytes (RDP), then full-chip DFU backup |
| `flash.bat` | `dfu-util -a 0 -s 0x08000000:leave -D <raw-mcu.bin>` |
| `recover.bat` | Reflash `firmware/mcu_stock.bin` |


## Game Library add-on

[`addon/`](addon/README.md) adds three things to the console's EXPERIMENTAL menu tab on firmware 1.26.4:

- a **library** of the cartridges you have played (name, play count, most recent first, up to 20);
- **per-game profiles**: Overclocking, video Profile, Image Size and Stretch are remembered per cartridge and re-applied when it starts;
- **cover art** next to the selected game, read from `COVERS/<CODE>.BIN` on the SD card;
- **virtual Controller Paks**: one 32 KB pak per game, `PAKS/<CODE>.MPK` on the SD card, instead of the one pak the console shares between all games.

It is C source compiled with the Arm GNU toolchain and appended to a raw slot-A image. Build, test, flash and cover
instructions are in [`addon/README.md`](addon/README.md). What is and is not supported is in [`CHEATSHEET.md`](CHEATSHEET.md).

## Claude Code skill

A ready-to-use Claude Code skill lives at [`skills/m64-firmware/SKILL.md`](skills/m64-firmware/SKILL.md). Copy that folder to `~/.claude/skills/m64-firmware/` (or your Claude Code skills directory). It triggers when you mention the M64, ModRetro, these `.bin` files, the boot or No-Cartridge screens, the game library, per-game profiles, cover art, or flashing, and it tells the agent to follow the build-verify-then-flash protocol:

1. Build and verify only, with no USB access.
2. Report the file's SHA-256 and size.
3. Give DFU instructions and wait for confirmation.
4. Only then: check the device is connected, read RDP, take a full-chip backup, re-check the hash, and flash. Do not skip the RDP read or backup, even if an earlier session already did them.
5. Ask you to check the device, and name the rollback file.

The same protocol, plus the UI-image recipe and screen maps, is in [`docs/GUIDE.md`](docs/GUIDE.md), so any agent or human can follow it without Claude Code.

## Safety (non-negotiable)

1. Read the RDP level **before any flash write**. Abort if it is not `0xAA` (Level 0). Never flash at Level 2 (`0xCC`) — that can permanently lock the MCU. Level 1 mass-erases on write.
2. Take a full-chip backup before every flash, and confirm the backup looks right (compare against the last flashed `.bin` at its full length, not only the 778,128-byte stock extract).
3. Keep in-place edits the same length; leave string NUL terminators alone; recompute both CRC fields.
4. Do **not** crack or forge ModRetro's signature. Do **not** publish firmware binaries or any `.pem` keys.
5. This can brick a unit if RDP / image / command is wrong. You use these tools on your own hardware, at your own risk.

## What this repo will never contain

- Official or modified `M64.BIN` / slot-A images / chip backups / option-byte dumps
- Private keys (`*.pem`)
- ModRetro's signing key material
- Redistributed schematic PDFs (get them from ModRetro; see below)

Hardware schematics and mechanical files are published by ModRetro:

- Open-source files: https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg
- Console hardware repo: https://github.com/ModRetro/oss-m64-console

## Creating / using the public Git repository

This tree is meant to be published as a **public** GitHub repository after a clean security/privacy review and the owner's final go-ahead. Suggested name: `m64-firmware-toolkit`.

### Clone and use

```bash
git clone https://github.com/<you>/m64-firmware-toolkit.git
cd m64-firmware-toolkit
python -m pip install -r scripts/requirements.txt
```

Then follow the Quick start above. Put official firmware only in `firmware/` or your working directory — it will not be committed (see `.gitignore`).

### First-time publish checklist

Do this only after review and an explicit publish decision:

1. Confirm `SECURITY_REVIEW.md` is **not** in the commit (it is gitignored).
2. `git status` shows **no** `*.bin`, `*.BIN`, `*.pem`, schematic PDFs, or personal notes.
3. Search the tree for personal paths, emails, device serials, and machine identifiers — there should be none.
4. Create an empty public GitHub repository (no README/license, so this tree is the first commit).
5. From this directory:

```bash
git init
git add .
git status   # review every path
git commit -m "Initial public release of the M64 firmware toolkit"
git branch -M main
git remote add origin https://github.com/<you>/m64-firmware-toolkit.git
git push -u origin main
```

Do not force-push, and do not add firmware or keys "just for convenience" later.

## License

GPL-3.0 — see [`LICENSE`](LICENSE). This matches the license of ModRetro's own [open-source console repo](https://github.com/ModRetro/oss-m64-console); it is copyleft, so anything you redistribute that is built on this must also stay open under GPL-3.0. Official M64 firmware, trademarks, and schematics remain ModRetro's; dfu-util and Zadig are third-party tools with their own licenses, obtained from their upstream sites.
