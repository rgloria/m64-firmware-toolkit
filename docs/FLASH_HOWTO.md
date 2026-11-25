# M64 DFU flash runbook (Route A)

Command-by-command connect, backup, flash, and recover. Run these from the toolkit root unless a full path is shown. On Windows, invoke `dfu-util` from wherever you installed it (examples below use `dfu-util` on `PATH`). On Linux and macOS, a distro or Homebrew `dfu-util` is fine.

A flash write is consequential. Confirm you want it before step 6 (flash) or the recover step.

---

## 1. Connect and enter DFU

1. Plug a data-capable USB-C cable into the M64 **power** USB-C port (not a charge-only cable, and not a data-only accessory port) and into the PC.
2. Hold the **menu** button, press **power**, and keep holding menu for about **15 seconds**.
3. Release menu. The device should enumerate as USB **`0483:df11`**, name **"DFU in FS Mode"**.
4. Leave it in DFU until you are finished. Do not power-cycle in the middle of a read or write.

## 2. Windows driver (first time, or if `-l` sees nothing)

UsbDk does **not** work with typical Windows `dfu-util` builds. Use Zadig (https://zadig.akeo.ie/):

1. Run Zadig
2. Options → List All Devices
3. Select **"DFU in FS Mode"**
4. Install **WinUSB**
5. Re-plug / re-enter DFU if needed

Linux and macOS: skip Zadig; `dfu-util` talks to the device directly.

## 3. Confirm alt interfaces

```
dfu-util -l
```

Expect three alts:

```
alt 0: @Internal Flash  /0x08000000/256*08Kg
alt 1: @Option Bytes    /0x5200201C
alt 2: @OTP             /0x08FFF000
```

If the list is empty, the WinUSB driver is missing or the unit is not in DFU. Go back to steps 1–2.

## 4. Read RDP (read-only — always do this first)

```
dfu-util -a 1 -s 0x5200201C -U firmware/optbytes_read.bin
```

Decode FLASH_OPTSR_CUR (32-bit little-endian word at offset **+4**; RDP = bits **[15:8]** of that word):

```
python -c "d=open('firmware/optbytes_read.bin','rb').read(); v=int.from_bytes(d[4:8],'little'); r=(v>>8)&0xFF; print(hex(v), hex(r))"
```

Interpretation:

- RDP `0xAA` — Level 0, safe to continue
- RDP `0xCC` — Level 2, **stop, never flash** (can permanently lock the MCU)
- Any other value — Level 1; a write mass-erases the flash. Stop unless that is explicitly intended

Only continue if RDP is `0xAA`.

## 5. Full-chip backup (every time, before a write)

```
dfu-util -a 0 -s 0x08000000 -U firmware/chip_backup_NEW.bin
```

The file should be 2,097,152 bytes (2 MB). Compare it against the **last flashed** raw slot-A `.bin` at that file's full length — not only against stock, and not only the first 778,128 bytes. After a UI-image mod the booted image can be larger than a stock extract (up to 1,048,576 bytes):

```
python -c "a=open('firmware/chip_backup_NEW.bin','rb').read(); b=open('firmware/mcu_mod.bin','rb').read(); print('MATCH' if a[:len(b)]==b else 'DIFFER'); print('backup', len(a), 'image', len(b))"
```

If stock is what is currently booted, use `firmware/mcu_stock.bin` in place of `mcu_mod.bin` (778,128 bytes). If a previous custom build is booted, compare against that build.

Or use the wrapper, which does the RDP read and a dated backup in one step:

```
scripts/backup.bat
```

That writes `firmware/optbytes_read.bin` and `firmware/chip_backup_YYYYMMDD.bin`.

## 6. Flash a raw slot-A image (confirmation required)

The file must be a raw MCU image for `0x08000000`, **not** the 7.7 MB `M64.BIN` container. A stock slot-A extract is 778,128 bytes; a UI-image mod that appends a cave and payload may be larger, up to **1,048,576 bytes** (1 MB, the size of slot A).

```
dfu-util -a 0 -s 0x08000000:leave -D firmware/mcu_mod.bin
```

Or:

```
scripts/flash.bat firmware/mcu_mod.bin
```

Notes:

- `:leave` exits DFU and resets the MCU when the write completes
- `Invalid DFU suffix` is a harmless warning on a raw `.bin`
- `Error during download get_status` right after `Submitting leave request...` is also **harmless** (the MCU has already reset into the new firmware). The flash is good if `Download done.` / `File downloaded successfully` appeared before it.
- Wait for the transfer to finish and for the tool to exit

## 7. Verify on the device

1. If it did not reboot cleanly, unplug DFU, connect the normal power cable, and power on.
2. Confirm the change. For the example same-length string patch in `scripts/repack.py`, open **About → Update from SD Card** with an `M64.BIN` in the root of the SD card. The status line should show the new string (default example: `CUSTOM READY!`). If the card is missing or has no `M64.BIN` in the root, the line stays on "SD card required" / "M64.BIN Not Found".

## 8. Recover / roll back to stock

Re-enter DFU (step 1), then:

```
dfu-util -a 0 -s 0x08000000:leave -D firmware/mcu_stock.bin
```

Or:

```
scripts/recover.bat
```

(`recover.bat` expects `firmware/mcu_stock.bin`, which you create from an official container with `extract_slota.py` — see [`firmware/README.md`](../firmware/README.md).)

To restore the entire 2 MB chip (both banks) instead of just slot A:

```
dfu-util -a 0 -s 0x08000000:leave -D firmware/chip_backup_NEW.bin
```

The ROM bootloader cannot be erased, so this DFU recover path keeps working unless RDP is Level 2. Slot B at `0x08100000` is a fallback copy as well.

---

## Extract a new slot-A image from a container

If you have a modified `M64.BIN` (after `repack.py`) and need a flashable `.bin`:

```
python scripts/extract_slota.py path/to/M64_mod.BIN firmware/mcu_new.bin
```

Then, only after RDP + backup + confirmation:

```
scripts/flash.bat firmware/mcu_new.bin
```
