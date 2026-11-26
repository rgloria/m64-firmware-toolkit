---
name: m64-firmware
description: Modify and DFU-flash the menu/overlay firmware of a ModRetro M64 handheld that the user owns (STM32H7, LVGL 9 UI, firmware 1.26.4) - string edits, custom images/characters on UI screens (boot screen, "No Cartridge Detected" screen), Thumb code caves, C add-ons appended to the image (the Game Library add-on - played-cartridge library, per-game overclock/video profiles, cover art and per-game virtual Controller Paks on the SD card), building a raw slot-A .bin, emulator-testing it, and flashing over USB DFU with dfu-util with RDP check, backup and rollback. Use when the user mentions the M64, ModRetro, M64.BIN, mcu_mod*.bin, the no-cartridge or boot screen, the game library, per-game profiles, cover art, Controller Paks / memory paks / save files, save states, putting a sprite/character on the M64, or flashing/recovering it.
---

# M64 firmware mods

This skill applies to a ModRetro M64 **that the user owns**. Everything verified so far lives in this toolkit.
**Read `docs/GUIDE.md` before doing anything.** It has the agent protocol, container/CRC layout, the screen maps with every VA, the UI-image recipe, the C add-on method and firmware facts, DFU steps and recovery.
`docs/FLASH_HOWTO.md` is the command-by-command flash runbook. `CHEATSHEET.md` says what is supported and how it is used on the console. `addon/README.md` covers the Game Library add-on end to end.

## How the work should be run (non-negotiable)

1. **Build only** until the build is verified. Do not run any dfu-util command, not even `-l`, during the build.
2. Verify: only the intended bytes changed vs the base `.bin`, the vector table is identical (SP `0x20020000`, Reset `0x08014F71`), size ≤ 1,048,576, and every patched instruction disassembles correctly from the output file. For image mods, render a preview PNG from the built bytes and look at it. For code add-ons, run the emulator test.
3. Write or extend a `*_CHANGES.md` next to the output (offsets, old→new bytes, sizes, SHA-256, what was and was not tested).
4. Report file name + SHA-256 + byte size. Then tell the user: *put the M64 into DFU: hold menu + power ~15 s on the **power** USB-C port until the screen goes dark*. **Stop and wait** until they say it is connected.
5. After they confirm, in this order: `dfu-util -l` (expect `0483:df11`, alt 0 `@Internal Flash /0x08000000/256*08Kg`) → RDP read (`-a 1 -s 0x5200201C -U`, RDP byte must be `0xAA`) → full-chip backup (`-a 0 -s 0x08000000 -U`) and check its start equals the image you believe is installed → re-check SHA-256 → `dfu-util -a 0 -s 0x08000000:leave -D <file.bin>`. Do not skip the RDP read or the backup, even if an earlier session already did them.
6. Ask the user to check the device, with specific things to look at. Name the rollback `.bin` (the previous working build, then `mcu_stock.bin`). Record what they report; do not record more than they said.

`Invalid DFU suffix` and `Error during download get_status` (after `Submitting leave request...`) are both harmless. Success = `File downloaded successfully`.
dfu-util: use `dfu-util` on `PATH`, or `<toolkit>/dfu/dfu-util.exe` on Windows (install WinUSB via Zadig first).

## Fast path for image/character mods

Work on **raw slot-A images** (VA = 0x08000000 + file offset). Append new data after the current end. Never splice into M64.BIN.

```
cd <toolkit>/scripts
python sprite_prep.py sheet.png sprite.png HEIGHT --box x0,y0,x1,y1 [--outline 0,215,75,215 | --outline none]
python screen_image.py add    BASE.bin OUT.bin sprite.png --x X --y Y --hook <bl VA> --orig <bl target>
python screen_image.py resize BASE.bin OUT.bin sprite.png --x X --y Y --cave <cave VA>   # move/resize an existing one
# Windows:  set M64BIN=OUT.bin & python rawdis.py d <VA> <n>
# POSIX:    M64BIN=OUT.bin python rawdis.py d <VA> <n>
# also: str / xref / dsc / w / callers <VA> / cli [filter] / events / ramrefs <lo> <hi>
```

- No-Cartridge screen: hook `0x0801FBD4`, orig `0x0803758C`, screen field +4. Free box x 0..109 / y 0..211. The icon is at y 103..135, the label at x 110..210 / y 148..160, the footer starts at y 212.
- Use `add` on a base without a No-Cartridge cave for a fresh character sprite. `resize` only works while that sprite is the **last thing in the file**. The cave VA is printed by `add`.
- Render a preview from the built image (decode the icon, fonts, footer and sprite with `lvfont.py`) and assert no overlap.
- RGB565A8 (cf 0x14) for full-color art. Descriptor `data_size` is at **+12** (w +4, h +6, stride +8, data ptr +16).
- Dark art on the black No-Cartridge screen needs the 1 px outline or it vanishes.

## Fast path for the Game Library add-on (C code)

```
python addon/build.py --base BASE.bin --out OUT.bin     # arm-none-eabi-gcc via PATH, M64_GCC or --gcc-dir
python addon/emu_test.py                                # 91 checks, must end with ALL PASS
python addon/tools/make_cover.py picture.png NSME --out <SD root>
```

- `BASE.bin` = stock 1.26.4 slot A, or stock + image mods. **Never** an image that already has the add-on: the build order is stock → image mods → add-on last. To change an image mod later, rebuild it and rerun `addon/build.py` on the result.
- Eight hooks, each asserted before patching: reset init `0x08014FAE`, overlay loop `0x080142A8`, `Settings_Write` `0x080146B0`, three on the Experimental page (`0x0802521C`, `0x0802526C`, `0x0802501C`), and the entries of `Cpak_Load` `0x0801BF54` / `Cpak_Save` `0x0801C02C` for virtual paks.
- State lives in unused AXI SRAM at `0x240F0000` (not zeroed at reset: the reset hook clears it). Do not use the gap after the DTCM `.bss`; the firmware uses it.
- Game records are in the settings EEPROM under tag `0x60`. Stock tags are `0x01`–`0x16`.
- The cartridge's 64-byte ROM header is kept by the firmware at RAM `0x20006DCE` (name +0x20, game code +0x3B). It is already valid when the firmware loads the Controller Pak at power-on (seen on a real unit).
- Virtual paks: `PAKS/<CODE>.MPK` (32 KB raw .mpk) replaces port 1's shared built-in pak, opt-in by the `PAKS` folder. Load and save are confirmed on a real unit. To test the save without a Controller Pak game: **Z** on the library row posts event 0x0E (the Game Reset flush); the row goes `[pak]` → `[pak ok]` and the file appears. Flashcart games keep the bootloader header and always use the shared pak.
- **Save states cannot be done from the MCU** (CPU/RCP state is inside the FPGA core; no pause or state readout is exposed). Say so instead of building a partial version.
- UI key codes: `0x81` A, `0x82` B, `0x87`–`0x8A` d-pad, `0x8F`/`0x90` encoder, `0x91` encoder press.

### Lessons that cost a flash each

- **SD card access must hold the firmware's file mutexes** `0x20008210` and `0x200078C4`, taken with wait 0 (never block), and only when the mounted flag `0x2000C514` is set. FatFs here has no lock. An unlocked read collided with the firmware's background `M64.BIN` check: no cover showed and About reported "Corrupt M64.BIN" until the fix.
- When something does not show on the console and the cause is not provable from the code, **add a status readout to the build** (the add-on writes one into the "Game Library" heading) instead of guessing. One flash then answers the question.
- A widget's built-in callback may be bound to a different key than expected (the stock table's is **B**, not A). Decode the hint-icon table (`0x080AA8E4`, index = key − 0x81) to confirm key codes before using them.
- The emulator test proves the add-on's logic, not the firmware around it. Say so when reporting.
- **Device state the emulator assumes may not exist.** The first on-device pak save failed because the owner's built-in pak had never been formatted (no game ever used it), so the save was refused by the stock ID-block rule; the emulator's model pak was always formatted. Model the blank/default state of anything the feature reads (paks, settings, card folders), and make every failure path report *which* step failed (the add-on's heading shows `pak blank`, `pak open N`, ...). One status word saved a guessing flash.

- **Backup check: compare slot A only up to the length of the image you think is installed.** DFU erases only the 8 KB sectors it writes, so bytes past the end of the current image can be leftovers of an older, longer build. That is harmless when they are unchanged since the previous backup and lie past the new image's end; check both, then flash.
- **To test a path the firmware runs only on some event** (a pak save, a reload), bind a key on the add-on's own page to `Event_Post` of that stock event (`rawdis.py events` lists them) instead of waiting for a game to trigger it. Z → 0x0E `Cpak_FlushBuiltIn` proved the pak save on a console without a Controller Pak game.
- **Check a saved `.MPK` on the PC:** 32,768 bytes; ID blocks at 0x20 / 0x60 / 0x80 / 0xC0, each with the checksum pair at +0x1C (sum of the first 14 big-endian halfwords, and 0xFFF2 − sum); inode table at 0x100 with an identical backup at 0x200 (pages 5–127 = `0x0003` when free); note table at 0x300. The stock format writes the label "The Future is Retro".
- On Windows, PowerShell `Set-Content` rewrites a file with a BOM and CRLF, so `diff`/`patch` against the repo then fail. Edit with the Edit tool or a Python script that keeps the line endings, or normalise both sides before diffing. The repo uses `core.autocrlf`.

### How to approach a new feature request

1. **Feasibility first.** If it needs the running N64's CPU/graphics state (save states, rewind, live RAM cheats), it lives in the FPGA core and is out of reach: say so with the evidence instead of building a partial version. The stock "Coming Soon" list (`0x20000508`) shows what ModRetro still plans.
2. **Map it** with `rawdis.py cli <keyword>` → handler → `callers` → `events`. Follow the method in the guide's "Developing a new feature" section.
3. **Agree the device test before building.** Ask whether the owner has what exercises the path (a game that saves to a Controller Pak, a card in the PC, a UART adapter). Flashcart games keep the flashcart's header.
4. **Prefer function-entry hooks** for "replace this stock behaviour everywhere", with an opt-in switch (e.g. a folder on the SD card), and fall back to the stock code in every other case.
5. **Report what was seen on the device and what is emulator-only, separately**, in the `*_CHANGES.md`, the PR and the reply.

### Working with the owner during device tests

- The owner can watch from a phone and send photos of the screen. Read them closely (heading text, row markers, status lines): they are the test result.
- When the next step can only be done by the owner (enter DFU, play a game, move the SD card), say so once, plainly, and stop. Do not repeat the request each time you are prompted.
- To pick up the SD card as soon as it is plugged in, run a background loop that waits for the drive letter, and require it to stay present for a few seconds, because ejecting makes the drive flicker. Keep the console's card contents unchanged apart from the folders the feature uses (`COVERS`, `PAKS`).
- Write patch scripts to files and run them, instead of inlining code with backslashes into shell heredocs; some shells mangle `\\` and `\0`.
- Before starting a card watcher, check whether the card is **already** in the PC. A loop that only waits for the drive fires at once and reports the old contents. If it is in the PC, wait for it to be removed and then come back.
- When the owner reports only a row marker (`[pak err]`), ask for the heading text too: the add-on puts the reason there. Owners often press a key several times and report only the end state, so record what they said, not the steps in between.

## Rules

- The user owns the device. Never crack or forge ModRetro's signature (the DFU route doesn't need it).
- Keep scripts and docs generic. Never put firmware binaries, `.pem` keys, device serials, game databases, cover art or personal art in this repository.
- Cover art: convert pictures the user supplies, or generate plain title cards from game names. Do not download and redistribute commercial box art.
- When something new is learned (a screen map, a gotcha, a verified technique), add it to `docs/GUIDE.md`, to `CHEATSHEET.md` if it changes what is supported, and to this file's fast paths.
