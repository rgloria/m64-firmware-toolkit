---
name: m64-firmware
description: Modify and DFU-flash the menu/overlay firmware of a ModRetro M64 handheld that the user owns (STM32H7, LVGL 9 UI) - string edits, adding or resizing custom images/characters on UI screens (boot screen, "No Cartridge Detected" screen), Thumb code caves, building a raw slot-A .bin, previewing the screen, and flashing over USB DFU with dfu-util with RDP check, backup and rollback. Use when the user mentions the M64, ModRetro, M64.BIN, mcu_mod*.bin, the no-cartridge or boot screen, putting a sprite/character on the M64, or flashing/recovering it.
---

# M64 firmware mods

This skill applies to a ModRetro M64 **that the user owns**. Everything verified so far lives in this toolkit. **Read `docs/GUIDE.md` before doing anything.** It has the agent protocol, container/CRC layout, the screen maps with every VA, the UI-image recipe, DFU steps and recovery. `docs/FLASH_HOWTO.md` is the command-by-command runbook.

## How the work should be run (non-negotiable)

1. **Build only** until the build is verified. Do not run any dfu-util command, not even `-l`, during the build.
2. Verify: only the intended bytes changed vs the base `.bin`, the vector table is identical (SP `0x20020000`, Reset `0x08014F71`), size ≤ 1,048,576, and the cave disassembles correctly from the output file. Render a preview PNG from the built bytes and check it visually (Read the PNG).
3. Write or extend a `*_CHANGES.md` next to the output (offsets, old→new bytes, sizes, SHA-256).
4. Report file name + SHA-256 + byte size. Then tell the user: *put the M64 into DFU: hold menu + power ~15 s on the **power** USB-C port until the screen goes dark*. **Stop and wait** until they say it is connected.
5. After they confirm, in this order: `dfu-util -l` (expect `0483:df11`, alt 0 `@Internal Flash /0x08000000/256*08Kg`) → RDP read (`-a 1 -s 0x5200201C -U`, RDP byte must be `0xAA`) → full-chip backup (`-a 0 -s 0x08000000 -U`) → re-check SHA-256 → `dfu-util -a 0 -s 0x08000000:leave -D <file.bin>`. Do not skip the RDP read or the backup, even if an earlier session already did them.
6. Ask the user to check the device. Name the rollback `.bin` (the previous build, then `mcu_stock.bin`).

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
# also: str / xref / dsc / w
```

- No-Cartridge screen: hook `0x0801FBD4`, orig `0x0803758C`, screen field +4. Free box x 0..109 / y 0..211. The icon is at y 103..135, the label at x 110..210 / y 148..160, the footer starts at y 212.
- Use `add` on a base without a No-Cartridge cave for a fresh character sprite. Use `resize` on a custom build that already has one to tweak its size or position. The cave VA is printed by `add` (it is the start of the appended block).
- Render a preview from the built image (decode the icon, fonts, footer and sprite with `lvfont.py`) and assert no overlap.
- RGB565A8 (cf 0x14) for full-color art. Descriptor `data_size` is at **+12** (w +4, h +6, stride +8, data ptr +16).
- Dark art on the black No-Cartridge screen needs the 1 px outline or it vanishes.

## Rules

- The user owns the device. Never crack or forge ModRetro's signature (the DFU route doesn't need it).
- Keep scripts and docs generic. Never put firmware binaries, `.pem` keys, device serials, or personal art in this repository.
- When something new is learned (a screen map, a gotcha, a verified technique), add it to `docs/GUIDE.md` and to this file's fast path.
