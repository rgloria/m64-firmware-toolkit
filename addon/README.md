# Game Library add-on (library, per-game profiles, cover art)

A C add-on for ModRetro M64 MCU firmware **1.26.4**. It is compiled, appended to a raw slot-A image and wired in by
redirecting six instructions of the stock firmware. Seen working on a real unit. Use it on a console you own, at your own risk.

What it does on the console is described in [`../CHEATSHEET.md`](../CHEATSHEET.md). How it works and every firmware
address it relies on are in [`../docs/GUIDE.md`](../docs/GUIDE.md#code-add-ons-in-c-verified-on-device).

## Files

| File | Purpose |
|---|---|
| `src/lib.c` | The add-on. Firmware functions are called through absolute addresses listed at the top of the file |
| `src/link.ld` | Linker script: code right after the base image, state in unused RAM at `0x240F0000` |
| `build.py` | Compile, append, patch the six hooks (each checks the bytes it replaces), verify, print SHA-256 |
| `emu_test.py` | Runs the compiled ARM code in Unicorn against Python models of the firmware calls (52 checks) |
| `tools/make_cover.py` | Picture → `COVERS/<CODE>.BIN` for the SD card |
| `tools/make_title_cards.py` | Plain title-card covers (coloured card + the game's name) for a table of game codes |
| `tools/codes_from_dat.py` | Builds that table from a game DAT file you supply |

## 1. Install

1. **Python 3** and the Python packages:
   ```
   python -m pip install -r ../scripts/requirements.txt
   ```
   (`capstone`, `pillow`, `unicorn`, `ecdsa`)
2. **Arm GNU Toolchain** (`arm-none-eabi-gcc`), from https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
   (13.3.Rel1 was used). Either put its `bin` folder on `PATH`, set `M64_GCC` to that folder, or pass `--gcc-dir`.
3. **dfu-util** (and on Windows, WinUSB installed with Zadig). See [`../docs/FLASH_HOWTO.md`](../docs/FLASH_HOWTO.md).

## 2. Get a base image

The base is a **raw slot-A image of 1.26.4** (not the `M64.BIN` container):

```
python ../scripts/extract_slota.py M64.BIN ../firmware/mcu_stock.bin
```

`M64.BIN` is the official 1.26.4 file (SHA-256 `2bf499c3…a69b3e`); this repository does not include it.
The base may already carry appended image mods made with `scripts/screen_image.py`. It must **not** already
contain this add-on: always build from the image without it.

## 3. Build

```
python build.py --base ../firmware/mcu_stock.bin --out ../firmware/mcu_library.bin
```

`build.py` prints the six patched instructions, the size and the SHA-256. It stops if any hook site does not hold
the expected stock bytes, if the vector table changes, or if the result would not fit in slot A (1 MB).
It never touches USB.

## 4. Test without a console

```
python emu_test.py
```

All 52 checks should print `PASS`, ending with `ALL PASS`. This proves the add-on's own logic (library, profiles,
cover loading, SD locking). It does not prove the firmware around it.

## 5. Flash

Follow [`../docs/FLASH_HOWTO.md`](../docs/FLASH_HOWTO.md). In short, from the repository root:

1. Enter DFU: hold **menu**, press **power**, keep holding about 15 s on the **power** USB-C port until the screen goes dark.
2. `scripts\backup.bat` — reads the protection level (must be `0xAA`) and saves a full 2 MB chip backup. Do this every time.
3. `scripts\flash.bat firmware\mcu_library.bin`
4. Raw commands, if you prefer:
   ```
   dfu-util -a 1 -s 0x5200201C -U firmware/optbytes_read.bin
   dfu-util -a 0 -s 0x08000000 -U firmware/chip_backup.bin
   dfu-util -a 0 -s 0x08000000:leave -D firmware/mcu_library.bin
   ```
   `Invalid DFU suffix` and `Error during download get_status` (after the leave request) are harmless.
   Success is `File downloaded successfully`.

**Roll back:** re-enter DFU and flash the image you had before (`scripts\recover.bat` flashes `firmware\mcu_stock.bin`).
DFU works even if the firmware does not boot. Stock firmware ignores the library records left in the settings memory.

## 6. Check it on the console

1. Play a cartridge for at least 10 seconds.
2. Menu → **EXPERIMENTAL**. Under the Overclocking dropdown there is a **Game Library** list with that game.
3. Press **down** onto the row, then **A**: the row switches between its own profile and `(default)`.

## 7. Cover art (optional)

Covers are files on the console's SD card: `COVERS/<CODE>.BIN`, where `<CODE>` is the cartridge's 4-character game code.
A game without a cover shows the file name it wants in grey next to its row.

```
python tools/make_cover.py picture.png NSME --out E:\            # one picture; E: is the SD card
python tools/make_cover.py --dir my_covers --out E:\             # a folder of pictures named <CODE>.png / .jpg
python tools/make_cover.py --decode E:\COVERS\NSME.BIN check.png # look at a converted file
```

Plain title cards for every game code in a table (no artwork needed):

```
python tools/codes_from_dat.py "Nintendo - Nintendo 64.dat" tools/n64_codes.json
python tools/make_title_cards.py tools/n64_codes.json --out E:\ --skip-existing
```

No cover images or game database are included in this repository. Use pictures you have the right to use.

File format: `"M64C"`, u16 80, u16 80, then an 80×80 RGB565 plane (little-endian) and an 80×80 alpha plane (19,208 bytes).

## Changing the add-on

- State must be zero-initialised (`link.ld` rejects initialised data). Constants are fine.
- Any code that reads the SD card must hold the firmware's two file mutexes (`0x20008210` and `0x200078C4`, taken with
  wait 0). FatFs in this firmware has no lock of its own; an unlocked read once made the console report "Corrupt M64.BIN".
- New firmware calls: add the address at the top of `lib.c`, add a model for it in `emu_test.py`, and add a check.
- All addresses are for 1.26.4 only.
