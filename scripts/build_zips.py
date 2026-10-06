"""Build site/data/zips.json: New England ZIP code -> congressional district(s).

Uses the Census Bureau's 2020 ZCTA-to-119th-Congress district relationship files,
one per state. (District lines in these states are fixed through 2030.)
A ZIP that crosses a district or state line maps to every district holding at
least 1% of its land area; the site asks those users for a street address.

Output: {"02139": [["MA", 7], ["MA", 5]], ...}  District 0 = at-large (VT).

Usage:  python scripts/build_zips.py   (run once; the output is committed)
"""

import csv
import io
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

URL = ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/"
       "tab20_cd11920_zcta520_st{fips}.txt")
STATES = {"09": "CT", "23": "ME", "25": "MA", "33": "NH", "44": "RI", "50": "VT"}
OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "zips.json"
MIN_SHARE = 0.01


def main():
    zips = defaultdict(list)
    for fips, st in STATES.items():
        with urllib.request.urlopen(URL.format(fips=fips), timeout=60) as resp:
            text = resp.read().decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text), delimiter="|"):
            zcta = row["GEOID_ZCTA5_20"]
            if not zcta:
                continue
            total = int(row["AREALAND_ZCTA5_20"] or 0)
            part = int(row["AREALAND_PART"] or 0)
            share = part / total if total else 0
            if share >= MIN_SHARE:
                cd = row["GEOID_CD119_20"][2:]
                zips[zcta].append((st, 0 if cd in ("00", "98") else int(cd), share))
    out = {z: [[s, d] for s, d, _ in sorted(v, key=lambda x: -x[2])] for z, v in sorted(zips.items())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    split = sum(1 for d in out.values() if len(d) > 1)
    print(f"Wrote {len(out)} ZIP codes ({split} split across districts) to {OUT}")


if __name__ == "__main__":
    main()
