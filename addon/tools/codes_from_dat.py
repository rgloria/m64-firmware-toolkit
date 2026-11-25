#!/usr/bin/env python3
"""Build the {game code: title} table that make_title_cards.py needs, from a No-Intro style DAT you supply.

This repository does not ship a game database. Get a ClrMamePro-format "Nintendo - Nintendo 64" DAT that has
`serial "XXXX"` fields (for example from the libretro-database project's metadat/no-intro folder), then:

  python codes_from_dat.py "Nintendo - Nintendo 64.dat" n64_codes.json

Prototype / beta / unlicensed entries are only used when no retail entry has the same code.
"""
import collections
import json
import re
import sys
from pathlib import Path

SKIP = ("(Beta", "(Proto", "(Demo", "(Kiosk", "(Unl", "(Aftermarket", "(Pirate", "(Sample", "(Debug")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    table = collections.OrderedDict()
    for name, body in re.findall(r'game \(\s*name "([^"]+)"(.*?)\n\)', text, flags=re.S):
        m = re.search(r'serial "([^"]+)"', body)
        if not m:
            continue
        code = m.group(1).upper()
        if not re.fullmatch(r"[0-9A-Z]{4}", code):
            continue
        skip = any(k in name for k in SKIP)
        title = re.sub(r"\s*\(.*$", "", name).strip()
        # "Legend of Zelda, The - ..." -> "The Legend of Zelda - ..."
        title = re.sub(r"^(.*?), (The|A|An)( - |$)", lambda k: f"{k.group(2)} {k.group(1)}{k.group(3)}", title)
        if code not in table or (table[code][1] and not skip):
            table[code] = (title, skip)
    Path(sys.argv[2]).write_text(json.dumps({c: v[0] for c, v in table.items()}, indent=0), encoding="utf-8")
    print(f"{len(table)} game codes written to {sys.argv[2]}")


if __name__ == "__main__":
    main()
