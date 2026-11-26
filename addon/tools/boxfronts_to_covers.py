#!/usr/bin/env python3
"""Turn a folder of N64 box-front images named with No-Intro titles (e.g. "Super Mario 64 (USA).png")
into M64 cover files COVERS/<CODE>.BIN, matching titles to game codes with n64_codes.json.

  python boxfronts_to_covers.py <images dir> --out E:/ [--sheet preview.png] [--report matches.json]

Writes <out>/COVERS/<CODE>.BIN for every code whose title matches an image, and prints what matched.
By default a box is used for every code of that title (USA box also for the PAL/Japan code of the same title,
which is better than a title card); unmatched codes are left alone so existing title cards stay.
Personal use only: the images are not ours to redistribute, so keep them and the output out of the repo.
"""
import argparse, json, re, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import make_cover

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def norm(title: str) -> str:
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", title)            # drop (USA), (Rev 1), [!] ...
    t = t.strip()
    m = re.match(r"^(.*?), (The|A|An)( - .*)?$", t)              # "Legend of Zelda, The - X" -> "The Legend of Zelda - X"
    if m:
        t = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    t = t.lower().replace("&", " and ").replace("'", "")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    return " ".join(t.split())


def region_rank(name: str) -> int:
    n = name.lower()
    return 0 if "(usa)" in n else 1 if "usa" in n else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("--out", required=True)
    ap.add_argument("--codes", default=str(Path(__file__).parent / "n64_codes.json"))
    ap.add_argument("--sheet")
    ap.add_argument("--report")
    a = ap.parse_args()
    codes = json.loads(Path(a.codes).read_text(encoding="utf-8"))
    imgs = {}
    for p in sorted(Path(a.src).rglob("*")):
        if p.suffix.lower() in EXTS:
            k = norm(p.stem)
            if k not in imgs or region_rank(p.name) < region_rank(imgs[k].name):
                imgs[k] = p
    by_title = {}
    for code, title in codes.items():
        by_title.setdefault(norm(title), []).append(code)
    nospace = {k.replace(" ", ""): k for k in by_title}
    out = Path(a.out) / "COVERS"; out.mkdir(parents=True, exist_ok=True)
    done, unmatched, thumbs = {}, [], []
    for k, p in sorted(imgs.items()):
        key = k if k in by_title else nospace.get(k.replace(" ", ""))
        if not key:
            unmatched.append(p.name); continue
        im = Image.open(p)
        data = make_cover.encode(im)
        for code in by_title[key]:
            (out / f"{code}.BIN").write_bytes(data)
            done[code] = p.name
        thumbs.append(make_cover.decode(data))
    print(f"images: {len(imgs)}  matched titles: {len(imgs) - len(unmatched)}  cover files written: {len(done)}")
    for n in unmatched:
        print("  no game code for:", n)
    if a.report:
        Path(a.report).write_text(json.dumps(done, indent=1, sort_keys=True))
    if a.sheet and thumbs:
        cols = 20
        sheet = Image.new("RGBA", (cols * 82, ((len(thumbs) + cols - 1) // cols) * 82), (40, 40, 40, 255))
        for i, t in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * 82 + 1, (i // cols) * 82 + 1), t)
        sheet.save(a.sheet)


if __name__ == "__main__":
    main()
