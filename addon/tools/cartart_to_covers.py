#!/usr/bin/env python3
"""Make M64 covers (COVERS/<CODE>.BIN) from the archive.org "N64 Cartridge Art Collection" images zip
(files named "<Title> (<Region>) [(extra)] Front|Back|Cart|Spine.jpg").

  python cartart_to_covers.py <images.zip> --out E:/ [--kind Front|Cart] [--sheet preview.png] [--report matches.json]

Writes <out>/COVERS/<CODE>.BIN. Run it with --out pointing at a PC folder first, look at the --sheet, then copy
the COVERS folder to the SD card (or point --out straight at the card).

For every game code in n64_codes.json, picks the <kind> image whose title matches, preferring the code's own
region (code letter E = USA -> (U), P = Europe -> (E)/(UK), J -> (J), D -> (DE), F -> (F), ...) and plain releases
over "Player's Choice"/box-set variants. Codes without a match are left alone (their title cards stay).
Personal use on your own SD card only; keep the images and output out of the repo.
"""
import argparse, io, json, re, sys, zipfile
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import make_cover
from boxfronts_to_covers import norm

REGION_PREF = {
    "E": ["U", "C", "UK", "E", "AU", "J"],            # USA
    "A": ["U", "E", "UK", "J"],
    "J": ["J", "U", "E", "UK"],
    "P": ["E", "UK", "U", "AU"], "X": ["E", "UK", "U"], "Y": ["E", "UK", "U"], "Z": ["E", "UK", "U"],
    "U": ["AU", "UK", "E", "U"],                     # Australia
    "D": ["DE", "G", "E", "UK", "U"], "F": ["F", "FR", "E", "UK", "U"], "I": ["I", "IT", "E", "U"],
    "S": ["S", "ES", "E", "U"], "H": ["NL", "E", "U"], "W": ["E", "UK", "U"], "K": ["K", "KR", "J", "U"],
    "C": ["C", "J", "U"], "B": ["B", "BR", "U"],
}
PAT = re.compile(r"^(?P<title>.*?) \((?P<reg>[A-Za-z,\-]+)\)(?P<extra>.*?) (?P<kind>Front|Back|Cart|Spine|Manual.*?)\.(jpe?g|png)$", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip"); ap.add_argument("--out", required=True)
    ap.add_argument("--codes", default=str(Path(__file__).parent / "n64_codes.json"))
    ap.add_argument("--kind", default="Front")
    ap.add_argument("--sheet")
    ap.add_argument("--report", help="write the chosen image per code (and the codes with none) to this JSON file")
    a = ap.parse_args()
    codes = json.loads(Path(a.codes).read_text(encoding="utf-8"))
    z = zipfile.ZipFile(a.zip)
    cands = {}                       # norm(title) -> [(region, extra, name)]
    skipped = 0
    for n in z.namelist():
        m = PAT.match(Path(n).name)
        if not m or m["kind"].lower() != a.kind.lower():
            skipped += 1; continue
        cands.setdefault(norm(m["title"]), []).append((m["reg"].upper(), m["extra"].strip(), n))
    nospace = {k.replace(" ", ""): k for k in cands}
    out = Path(a.out) / "COVERS"; out.mkdir(parents=True, exist_ok=True)
    chosen, missing, cache, thumbs = {}, [], {}, []
    for code, title in sorted(codes.items()):
        k = norm(title)
        k = k if k in cands else nospace.get(k.replace(" ", ""))
        if not k:
            missing.append(f"{code} {title}"); continue
        pref = REGION_PREF.get(code[3], ["U", "E", "J"])
        def rank(c):
            reg, extra, name = c
            regs = reg.split(",")
            r = min((pref.index(x) for x in regs if x in pref), default=len(pref))
            return (r, len(extra), name)
        reg, extra, name = min(cands[k], key=rank)
        if name not in cache:
            cache[name] = make_cover.encode(Image.open(io.BytesIO(z.read(name))))
            thumbs.append((code, make_cover.decode(cache[name])))
        (out / f"{code}.BIN").write_bytes(cache[name])
        chosen[code] = name
    print(f"{a.kind} images: {sum(len(v) for v in cands.values())} for {len(cands)} titles; "
          f"codes covered: {len(chosen)} of {len(codes)}; distinct images used: {len(cache)}")
    if a.report:
        Path(a.report).write_text(json.dumps({"chosen": chosen, "no_image": missing}, indent=1))
    if a.sheet and thumbs:
        cols = 24
        sheet = Image.new("RGBA", (cols * 82, ((len(thumbs) + cols - 1) // cols) * 82), (30, 30, 30, 255))
        for i, (_, t) in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * 82 + 1, (i // cols) * 82 + 1), t)
        sheet.save(a.sheet)


if __name__ == "__main__":
    main()
