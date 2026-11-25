# M64 Firmware Toolkit — one-page cheat sheet

Owner-hardware menu-firmware tools for the ModRetro M64. **Not a signature crack.** Never publish `*.bin` / `*.pem`. Flash only after an RDP check (`0xAA`) and a full-chip backup.

## Install

```bash
python -m pip install -r scripts/requirements.txt    # capstone, ecdsa, pillow
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

## Safety and further reading

Read RDP before every write. Backup before every write. Same-length edits only. You use this on your own hardware, at your own risk.

Full guide: [`docs/GUIDE.md`](docs/GUIDE.md). Flash runbook: [`docs/FLASH_HOWTO.md`](docs/FLASH_HOWTO.md). Schematics (from ModRetro, not this repo): https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg

## Repo setup

```bash
git clone https://github.com/<you>/m64-firmware-toolkit.git
cd m64-firmware-toolkit
python -m pip install -r scripts/requirements.txt
```

First publish (only after a clean review and an explicit go): confirm `.gitignore` is excluding `*.bin`, `*.pem`, and `SECURITY_REVIEW.md`; `git status` is clean of firmware and keys; then `git init && git add . && git commit` and push to an empty public GitHub repo. Suggested name: `m64-firmware-toolkit`. Details: [`README.md`](README.md).
