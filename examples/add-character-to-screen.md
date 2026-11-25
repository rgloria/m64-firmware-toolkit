# Example: add a custom image to a firmware screen (from scratch)

This is a worked starting-point prompt for an AI coding CLI (e.g. Claude Code,
Codex) to reverse-engineer an M64 slot-A firmware image and add a custom
character/image to one of its on-screen screens. It assumes nothing is
pre-built: the CLI rediscovers the offsets, sets up its own dependencies, and
rebuilds everything, which is a truer test than handing it cached notes.

## How to use it

1. Make a fresh empty working folder.
2. Drop in exactly two files:
   - `base.bin` — a raw slot-A firmware image you extracted from your own
     device (see the main README / GUIDE for reading your chip and extracting
     slot A). **Never commit firmware binaries.**
   - `character_sprites.png` — your character art (a sprite sheet or single PNG).
3. Paste the goal below into the CLI, running inside that folder.
4. Review the generated preview and `CHANGES.md`, then flash only after you
   have a verified backup and confirmed RDP Level 0 (see GUIDE / FLASH_HOWTO).

## The goal

```
/goal You are reverse-engineering and modifying firmware for a handheld I own. Work entirely in the current folder. BUILD ONLY until the final step — do NOT flash or touch any USB/DFU device during the build. Do NOT forge or crack any cryptographic signature; DFU uses the raw unsigned path and needs none.

INPUTS in this folder:
- base.bin — a raw STM32H7A3 slot-A firmware image that maps to VA 0x08000000 (vector table at offset 0, SP then Reset vector). Treat it as the starting point; keep it unmodified and write a new output file.
- character_sprites.png — character art (a sprite sheet of poses on a plain background, or a single PNG). Pick a single clear pose.

SETUP: Create a Python venv and install whatever you need (capstone for Thumb/Cortex-M7 disassembly, pillow + numpy for image work). Don't assume any package is preinstalled.

GOAL: Add the character art to one of the firmware's screens (for example a "no cartridge"/idle screen), placed cleanly next to the existing elements without overlapping them, scaled to a reasonable size.

FIGURE OUT FROM SCRATCH (document what you find):
1. Confirm the architecture/image layout by reading the vector table; verify it disassembles as Thumb.
2. This firmware uses LVGL 9; screens are 320x240. Find the target screen: locate its text string, its screen create/setup function, an existing image (lv_image) descriptor (format/width/height/data pointer), and how elements are positioned.
3. Determine LVGL's image-descriptor struct layout and a suitable color format for full-color art on the screen's background (e.g. RGB565A8). If the art would blend into the background, add a thin bright outline so the silhouette reads.
4. Find free space (erased 0xFF / padding) after the used image to append new data, staying within slot A (1 MB).

MAKE THE CHANGE (lowest-risk technique):
- Key out the art's background, scale it, encode to your chosen LVGL format, and append: the pixel payload, a new image descriptor, and a small Thumb "code cave" that creates+positions a new image object on that screen.
- Redirect one existing instruction in the screen setup to your cave (e.g. repurpose a bl to lv_obj_center), having the cave preserve the original behavior and then add your image.
- Keep everything else byte-identical to base.bin except your intended edits.

VERIFY: diff against base.bin and confirm only intended bytes changed; confirm the vector table is intact and total size fits slot A.

OUTPUT: write mod.bin (raw slot-A image), print its SHA-256 and size, render a faithful 2x PNG preview of the final screen decoded from mod.bin itself, and write CHANGES.md documenting every offset, byte, struct field, and the cave disassembly, plus any assumptions made from static analysis.

FINAL STEP: once built and verified, tell me to put the device into DFU mode (hold menu + power ~15s on the power USB-C port until the screen goes dark) and WAIT for me to confirm it's connected before flashing anything. Do NOT flash until I confirm.
```

## Notes

- `scripts/sprite_prep.py` cuts a frame, keys the background, and can add a
  1 px outline; `scripts/make_lvgl_image.py` packs the PNG into an LVGL
  `lv_image_dsc_t` + payload; `scripts/screen_image.py` appends the cave and
  hooks it into a screen (or resizes an existing one).
- `scripts/rawdis.py` (raw slot-A, VA-based) and `scripts/m64dis.py` (container
  file offsets) are Capstone Thumb disassembler helpers for reconnaissance.
  `scripts/lvfont.py` decodes fonts and images out of a built `.bin` for previews.
- The "code cave" technique, descriptor layout, and screen maps are covered
  in `docs/GUIDE.md`.
