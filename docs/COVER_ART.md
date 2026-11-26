# Adding cover art to the Game Library profiles

The Game Library add-on ([`addon/`](../addon/README.md)) shows an 80×80 cover next to the selected game in
Menu → **EXPERIMENTAL** → **Game Library**. Covers are plain files on the console's SD card. Adding or changing one
needs no reflash: copy files to the card, put it back in the M64, and open the Game Library.

No cover images, box scans or game database ship with this repository. Use pictures you made or have the right to
use, keep them on your own card, and do not commit them (or the converted `.BIN` files) to a repository.

## What the console looks for

| | |
|---|---|
| File | `COVERS/<CODE>.BIN` on the SD card root, e.g. `E:\COVERS\NSME.BIN` |
| `<CODE>` | The cartridge's 4-character game code: `N` + 2-letter game ID + region letter (`E` USA, `P` Europe, `J` Japan, `D` Germany, `F` France, `U` Australia …). Super Mario 64 (USA) is `NSME`; Zelda: Ocarina of Time (USA) is `CZLE` |
| Format | `"M64C"`, u16 80, u16 80, an 80×80 RGB565 plane (little-endian), an 80×80 alpha plane: 19,208 bytes. The tools below write it; any picture size works, it is scaled to fit and centred |
| No file | The row shows the file name it wants (`COVERS/NSME.BIN`) in grey at its right. This is the easiest way to learn a cartridge's code |
| No card | Nothing is shown; the console retries every 10 s |

Flashcart menus (such as the SC64 bootloader) and some homebrew have no valid game code, so they get no cover.

## Install the tools once

```
python -m pip install -r scripts/requirements.txt      # Pillow is the one the cover tools need
```

All commands below run from the toolkit root. `E:\` stands for the SD card in your PC; use your drive letter.

## Option A: one game from any picture

1. Put the cartridge in the M64, play it once so it appears in the Game Library, and read its code from the grey hint.
2. Convert a picture (PNG/JPG/WebP, any size; transparency is kept):
   ```
   python addon/tools/make_cover.py mario.png NSME --out E:\
   ```
3. Check it on the PC if you like: `python addon/tools/make_cover.py --decode E:\COVERS\NSME.BIN check.png`
4. Eject the card, put it in the M64, open Menu → EXPERIMENTAL → Game Library and move onto the row.

## Option B: a folder of your own pictures

Name each picture by its code (`NSME.png`, `NKTE.jpg`, `CZLE.webp`) and convert them all:

```
python addon/tools/make_cover.py --dir my_covers --out E:\
```

## Option C: a whole box-art collection you already have

These tools match titles to game codes, so they need a `{code: title}` table first. Make it once from a
No-Intro-style "Nintendo - Nintendo 64" DAT with `serial` fields (for example from the libretro-database project):

```
python addon/tools/codes_from_dat.py "Nintendo - Nintendo 64.dat" addon/tools/n64_codes.json
```

`n64_codes.json` stays on your PC; it is not part of the repository.

**Scans packed in a zip, named `<Title> (<Region>) [extra] Front.jpg`** (with `Back`, `Cart` and `Spine` images
beside them, as in common N64 scan collections):

```
python addon/tools/cartart_to_covers.py images.zip --out covers_out --sheet covers_out/sheet.png --report covers_out/matches.json
```

- Each code gets the box from its own region: an `…E` code prefers the `(U)` box, `…P` the `(E)`/`(UK)` box,
  `…J` the `(J)` box, `…D` the German one, and so on; it falls back to another region's box of the same game.
- Plain releases are preferred over "Player's Choice" and box-set variants.
- `--kind Cart` uses the cartridge-label scans instead of the box fronts.
- Codes with no matching image are left alone, so covers you made earlier stay. `matches.json` lists which image
  each code got and which codes had none.

**A folder of box fronts named with No-Intro titles** (`Super Mario 64 (USA).png`):

```
python addon/tools/boxfronts_to_covers.py box_fronts --out covers_out --sheet covers_out/sheet.png
```

That one gives the same box to every region's code of a title (a USA box for the PAL code beats no cover).

Then:

1. Open `covers_out/sheet.png` and look over the thumbnails.
2. Copy `covers_out/COVERS` to the SD card root (merge with any `COVERS` folder already there).

## Option D: title cards for everything else

A title card is a coloured card with the game's name on it, generated from the code table alone, with no artwork. Run it
**after** A–C so it only fills the gaps:

```
python addon/tools/make_title_cards.py addon/tools/n64_codes.json --out E:\ --skip-existing
```

`--skip-existing` keeps every cover already on the card.

## Replacing or removing a cover

- To replace one, run any option again for that code; the file is overwritten. To fix a wrong match from option C,
  convert the right picture with option A.
- To remove one, delete `COVERS/<CODE>.BIN`; the grey hint comes back.
- Before overwriting a whole folder of covers, copy the old `COVERS` folder somewhere on the PC so you can go back.

## Troubleshooting

| What you see | Cause / fix |
|---|---|
| Grey `COVERS/XXXX.BIN` hint | No file with that exact name. Check the code and the folder name (`COVERS`, at the card root) |
| No cover and no hint | The card is out or not readable yet (wait 10 s), or the cartridge has no game code |
| Wrong game's cover | Option C matched the title wrongly or the code table is wrong; replace that one file with option A |
| A garbled image | The file is not a 19,208-byte `M64C` file. Re-make it with the tools; `--decode` shows what the console will draw |
