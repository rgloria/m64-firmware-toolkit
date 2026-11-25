# M64 Firmware Toolkit — one-page cheat sheet

Owner-hardware menu-firmware tools for the ModRetro M64. **Not a signature crack.** Never publish `*.bin` / `*.pem`. Flash only after an RDP check (`0xAA`) and a full-chip backup.

## What is supported (firmware 1.26.4)

Everything marked Works has been seen running on a real unit.

| Feature | Where you see it | Status |
|---|---|---|
| Custom text in a menu string (same length) | wherever the string is shown | Works |
| Custom character on the **boot screen** (with the M64 wordmark kept) | power-on | Works |
| Custom character on the **No Cartridge Detected** screen | no cartridge inserted | Works |
| **Game Library**: list of played cartridges, play counts, most recent first | Menu → EXPERIMENTAL | Works |
| **Per-game profiles**: Overclocking, video Profile, Image Size, Stretch remembered per cartridge | applied ~2 s after the game is detected | Works (toggle confirmed; restore on cartridge swap not separately reported) |
| Per-game profile on/off | press **A** on a library row | Works |
| **Cover art** next to the selected library row | Menu → EXPERIMENTAL | Works |
| Grey file-name hint when a game has no cover file | right of the row | Built and emulator-tested; not yet reported from a device |

## Using the Game Library

- Open the menu → **EXPERIMENTAL**. Press **down** from the Overclocking dropdown to move onto the list.
- A row looks like `> SUPER MARIO 64  x4  OC Ultra  P2`:
  `>` = the cartridge running now, `x4` = times played, `OC …` = its saved overclock, `P1`–`P4` = its saved video profile.
  `(default)` instead of the last two = this game's own profile is switched off.
- **A** on a row: switch that game's profile on/off. **B**, d-pad and the encoder work as in the rest of the menu.
- To give a game its own settings: play it, change Overclocking / Profile / Image Size / Stretch in the normal menus. They are saved for that game automatically.
- A cartridge seen for the first time starts from the **default profile** = whatever you set with no cartridge running (or while a game with its profile off is running).
- Up to **20 games**. The 21st replaces the one played longest ago. "Erase Console Data" clears the library.

## Cover art

- Covers live on the SD card: **`COVERS/<CODE>.BIN`**. `<CODE>` is the cartridge's 4-character game code, e.g. `NSME`.
- A game with no cover file shows the file name it wants in grey at the right of its row. That is how you learn its code.
- Make one from any picture (PNG/JPG, any size):
  `python addon/tools/make_cover.py picture.png NSME --out E:\` (E: = the SD card)
- Make a whole folder: name the pictures by code (`NSME.png`, `NKTE.jpg`) and run
  `python addon/tools/make_cover.py --dir my_covers --out E:\`
- Fill the card with plain title cards (coloured card + the game's name) for every known game code:
  `python addon/tools/codes_from_dat.py "Nintendo - Nintendo 64.dat" addon/tools/n64_codes.json` (once, from a game DAT you supply), then
  `python addon/tools/make_title_cards.py addon/tools/n64_codes.json --out E:\ --skip-existing`
  (`--skip-existing` keeps any real cover you already made.)
- Check a file: `python addon/tools/make_cover.py --decode E:\COVERS\NSME.BIN check.png`
- No cover images or game database ship with this repository. Title cards are generated from the game's name only. Use pictures you have the right to use.

## What is NOT supported

| Not supported | Why / what happens instead |
|---|---|
| Covers for cartridges with no valid game code (flashcart menus such as the SC64 bootloader, some homebrew) | the file name is built from the code; the row just has no cover |
| Telling flashcart games apart | the console only sees the flashcart's own header, so every game launched from it is one library entry |
| More than 20 games, or deleting a single entry | fixed-size list in the settings memory |
| Per-game Resolution, Low Latency, scaler mode, region, Expansion Pak | they can need a video-mode change or a game reset; they stay global |
| Cover sizes other than 80×80 (pictures are scaled to fit inside it) | fixed buffer in the add-on |
| Covers without an SD card | nothing is shown; the console retries every 10 s |
| Installing these mods through the official SD/OTA updater | the appended code does not fit in the `M64.BIN` container; DFU only |
| Any firmware version other than 1.26.4 | every address is version-specific |

Known cosmetic issue: a small `|` after the "Game Library" heading (the start of a status text that does not fit in the heading).

---

## Install

```bash
python -m pip install -r scripts/requirements.txt    # capstone, ecdsa, pillow, unicorn
```

Get **dfu-util** from http://dfu-util.sourceforge.net/ and, on Windows, **Zadig** from https://zadig.akeo.ie/ (install **WinUSB** on "DFU in FS Mode"; do not use UsbDk). Official firmware (not in this repo): https://tools.modretro.com/updater/ or https://tools.modretro.com/downloads/m64-console/ . Copy official `M64.BIN` into your working directory. Stock **1.26.4** SHA-256:

`2bf499c33d5ebc8a0ab3393441b10962f812132bf1bfc12d4da4ce3964a69b3e`

## Edit a menu string (example: "M64.BIN Ready" → "CUSTOM READY!")

```bash
python scripts/m64dis.py str "M64.BIN Ready"          # file offset + VA
# edit STR_OFF / OLD / NEW in scripts/repack.py (same length, keep the NUL)
python scripts/repack.py                              # writes M64_mod.BIN + CRCs
python scripts/extract_slota.py M64_mod.BIN firmware/mcu_mod.bin
python scripts/extract_slota.py M64.BIN firmware/mcu_stock.bin   # keep for rollback
```

`m64dis.py xref <hexVA>` finds literal-pool refs; `m64dis.py d <hex_file_off> <nbytes>` disassembles THUMB. Address map: VA = `0x08000000 + (file_off - 0x118)`.

## DFU: enter, backup, flash, recover

Enter DFU on the **power** USB-C port: hold **menu**, press **power** ~15 s, release menu. USB id `0483:df11`. Then, from the toolkit root:

```bat
dfu-util -l                                           # alts 0 flash / 1 option bytes / 2 OTP
scripts\backup.bat                                   # RDP must be 0xAA; writes a 2 MB backup
scripts\flash.bat firmware\mcu_mod.bin              # WRITES flash; confirm first
scripts\recover.bat                                  # restores firmware\mcu_stock.bin
```

Equivalent raw commands: `dfu-util -a 1 -s 0x5200201C -U firmware/optbytes_read.bin`, then `-a 0 -s 0x08000000 -U firmware/chip_backup.bin`, then `-a 0 -s 0x08000000:leave -D firmware/mcu_mod.bin`. An "Invalid DFU suffix" warning is harmless, as is `Error during download get_status` after `Submitting leave request...`. Raw images may be up to 1 MB; after a UI-image mod, compare a new backup against the last flashed `.bin` (full length), not only stock. After flash, power-cycle. The example status string lives on **About → Update from SD Card** and only appears when an `M64.BIN` is in the SD-card root.

**RDP:** `0xAA` = Level 0 (safe). `0xCC` = Level 2 (**never flash**). Anything else = Level 1 (write mass-erases).

## Route B (optional, official updater)

Teardown + serial adapter to J15 ("MCU DEBUG SIGNALS", Samtec FTSH-104-01-F-DV): pin 1 = 3.3 V, pin 4 = RX, pin 5 = TX, pin 6 = GND, 115200 8N1 (FTDI TTL-232R-3V3). Shell command `fw_devmode on`, then `python scripts/sign.py in.BIN out.BIN your.pem` and install via the official SD updater. Sign only with a key you generated. Never forge the vendor signature.

## Image mods and the Claude Code skill

`scripts/sprite_prep.py` prepares a sprite; `scripts/screen_image.py` adds or resizes it on a screen in a raw slot-A `.bin`; `scripts/rawdis.py` / `scripts/lvfont.py` inspect and preview. Recipe and screen maps: [`docs/GUIDE.md`](docs/GUIDE.md). A Claude Code skill that enforces the build-verify-then-flash protocol is in [`skills/m64-firmware/SKILL.md`](skills/m64-firmware/SKILL.md).

## Game Library add-on (build, test, flash)

```bash
python scripts/extract_slota.py M64.BIN firmware/mcu_stock.bin                     # raw 1.26.4 base
python addon/build.py --base firmware/mcu_stock.bin --out firmware/mcu_library.bin  # needs arm-none-eabi-gcc (PATH, M64_GCC or --gcc-dir)
python addon/emu_test.py                                                           # 52 checks, must end with ALL PASS
scripts\backup.bat                                                                 # RDP 0xAA + full backup
scripts\flash.bat firmware\mcu_library.bin
```

Build the add-on **last**, on an image that does not already contain it (stock, or stock + image mods). To change an image mod later, rebuild that image and run `addon/build.py` on the result. Full steps: [`addon/README.md`](addon/README.md).

## Safety and further reading

Read RDP before every write. Backup before every write. In-place edits must keep their length. Add-on code that reads the SD card must hold the firmware's two file locks (`0x20008210`, `0x200078C4`). You use this on your own hardware, at your own risk.

Full guide: [`docs/GUIDE.md`](docs/GUIDE.md). Flash runbook: [`docs/FLASH_HOWTO.md`](docs/FLASH_HOWTO.md). Schematics (from ModRetro, not this repo): https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg

## Repo setup

```bash
git clone https://github.com/<you>/m64-firmware-toolkit.git
cd m64-firmware-toolkit
python -m pip install -r scripts/requirements.txt
```

First publish (only after a clean review and an explicit go): confirm `.gitignore` is excluding `*.bin`, `*.pem`, and `SECURITY_REVIEW.md`; `git status` is clean of firmware and keys; then `git init && git add . && git commit` and push to an empty public GitHub repo. Suggested name: `m64-firmware-toolkit`. Details: [`README.md`](README.md).
