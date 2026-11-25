# firmware/ (local only — not in this repository)

Put official and working images here on your machine. **Do not commit them.**
The root `.gitignore` blocks `*.bin` / `*.BIN`. ModRetro's firmware is
copyrighted; this project never redistributes it.

## Get an official container

1. Download the official `M64.BIN` from ModRetro (not from a random mirror):
   - Web updater: https://tools.modretro.com/updater/
   - SD-card downloads: https://tools.modretro.com/downloads/m64-console/
2. Copy it here as `M64.BIN`, or keep a reference copy named `M64_stock.BIN`.

The tools and CRC assertions in this repo were verified against stock
**1.26.4**. SHA-256 of that official container (recompute and compare):

```
2bf499c33d5ebc8a0ab3393441b10962f812132bf1bfc12d4da4ce3964a69b3e
```

A different version will still follow the same container layout, but the
stock CRC assertions in `scripts/repack.py` are specific to 1.26.4.

## Images you will create

| File | How to make it | Used by |
|---|---|---|
| `mcu_stock.bin` | `python scripts/extract_slota.py firmware/M64_stock.BIN firmware/mcu_stock.bin` | `scripts/recover.bat` |
| `mcu_mod.bin` | extract slot A from a container you rebuilt with `repack.py` | `scripts/flash.bat` |
| `chip_backup_YYYYMMDD.bin` | `scripts/backup.bat` (full 2 MB chip read) | rollback of both banks |
| `optbytes_read.bin` | written by `scripts/backup.bat` | RDP check (read-only) |

`recover.bat` expects `firmware/mcu_stock.bin` to already exist. Create it
from an official container before you flash anything.
