"""Build site/data/zips.json: Massachusetts ZIP code -> congressional district(s).

Uses the Census Bureau's 2020 ZCTA-to-119th-Congress district relationship file.
(Massachusetts district lines are fixed for 2022-2030, so this stays valid.)
A ZIP that crosses a district line maps to every district holding at least
1% of its land area; the site asks those users for a street address.

Usage:  python scripts/build_zips.py   (run once; the output is committed)
"""

import csv
import io
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

URL = ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/"
       "tab20_cd11920_zcta520_st25.txt")
OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "zips.json"
MIN_SHARE = 0.01


def main():
    with urllib.request.urlopen(URL, timeout=60) as resp:
        text = resp.read().decode("utf-8-sig")
    zips = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        zcta = row["GEOID_ZCTA5_20"]
        if not zcta or not zcta.startswith(("01", "02", "05")):  # MA ZIPs (055 = Andover)
            continue
        total = int(row["AREALAND_ZCTA5_20"] or 0)
        part = int(row["AREALAND_PART"] or 0)
        share = part / total if total else 0
        if share >= MIN_SHARE:
            zips[zcta].append((int(row["GEOID_CD119_20"][2:]), share))
    out = {z: [d for d, _ in sorted(ds, key=lambda x: -x[1])] for z, ds in sorted(zips.items())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    split = sum(1 for d in out.values() if len(d) > 1)
    print(f"Wrote {len(out)} ZIP codes ({split} split across districts) to {OUT}")


if __name__ == "__main__":
    main()
