"""Build site/data/candidates.json from FEC data.

Reads the general-election ballot from config/ballot_2026.json, then pulls from
the FEC API:
  * AIPAC PAC (C00797670) contributions to each candidate's committees,
    split into direct contributions and earmarked (bundled) contributions.
  * United Democracy Project (C00799031, AIPAC's super PAC) independent
    expenditures supporting or opposing each candidate.

The FEC API key is read ONLY from the FEC_API_KEY environment variable (or a
local, git-ignored .env file). It is never written to output or printed.

Usage:  python scripts/build_data.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BALLOT_FILE = ROOT / "config" / "ballot_2026.json"
OUT_DIR = ROOT / "site" / "data"
OUT_FILE = OUT_DIR / "candidates.json"

API = "https://api.open.fec.gov/v1"
AIPAC_PAC = "C00797670"
UDP_SUPER_PAC = "C00799031"
# AIPAC PAC was formed in December 2021, so 2022 is the first cycle with data.
CYCLES = [2022, 2024, 2026]


def load_api_key():
    key = os.environ.get("FEC_API_KEY", "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "FEC_API_KEY":
                key = value.strip().strip('"').strip("'")
    if not key and os.environ.get("CI"):
        sys.exit("FEC_API_KEY secret is missing. Add it under Settings > Secrets and variables > Actions.")
    if not key:
        print("FEC_API_KEY is not set; falling back to DEMO_KEY (heavily rate-limited).")
        key = "DEMO_KEY"
    return key


API_KEY = load_api_key()


def get(path, params):
    """GET an FEC endpoint. Error messages never include the API key."""
    query = urllib.parse.urlencode({**params, "api_key": API_KEY}, doseq=True)
    url = f"{API}{path}?{query}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"FEC API error {e.code} on {path}") from None
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"Network error on {path}: {e.reason}") from None


def get_all(path, params):
    """Fetch every page, handling both page-number and keyset pagination."""
    params = {**params, "per_page": 100}
    results = []
    page = 1
    while True:
        data = get(path, params)
        rows = data.get("results", [])
        results.extend(rows)
        pag = data.get("pagination", {})
        last = pag.get("last_indexes")
        if "last_indexes" in pag:  # keyset pagination (itemized schedules)
            if not rows or not last or len(results) >= pag.get("count", 0):
                break
            params.update(last)
        else:
            if page >= pag.get("pages", 1):
                break
            page += 1
            params["page"] = page
    return results


def fec_search_link(path, params):
    return f"https://www.fec.gov/data/{path}/?" + urllib.parse.urlencode(params, doseq=True)


def main():
    ballot = json.loads(BALLOT_FILE.read_text(encoding="utf-8"))
    fec_ids = [c["fec_id"] for r in ballot["races"] for c in r["candidates"] if c["fec_id"]]

    # 1. Each candidate's authorized committees (principal + other authorized).
    committees = get_all("/committees/", {"candidate_id": fec_ids, "designation": ["P", "A"]})
    committee_to_candidate = {}
    candidate_committees = defaultdict(list)
    for cm in committees:
        for cid in cm.get("candidate_ids") or []:
            if cid in fec_ids:
                committee_to_candidate[cm["committee_id"]] = cid
                candidate_committees[cid].append(cm["committee_id"])
    print(f"Found {len(committee_to_candidate)} committees for {len(fec_ids)} candidates.")

    # 2. AIPAC PAC disbursements to those committees.
    rows = get_all("/schedules/schedule_b/", {
        "committee_id": AIPAC_PAC,
        "recipient_committee_id": sorted(committee_to_candidate),
        "two_year_transaction_period": CYCLES,
    })
    print(f"AIPAC PAC: {len(rows)} itemized disbursements to these committees.")
    money = defaultdict(lambda: defaultdict(lambda: {"direct": 0.0, "earmarked": 0.0, "count": 0}))
    seen = set()
    for r in rows:
        if r.get("memo_code") == "X":  # memo lines duplicate an itemized total
            continue
        if r["sub_id"] in seen:
            continue
        seen.add(r["sub_id"])
        cid = committee_to_candidate.get(r.get("recipient_committee_id"))
        if not cid:
            continue
        kind = "earmarked" if "EARMARK" in (r.get("disbursement_description") or "").upper() else "direct"
        bucket = money[cid][str(r["two_year_transaction_period"])]
        bucket[kind] += r["disbursement_amount"] or 0
        bucket["count"] += 1

    # 3. United Democracy Project independent expenditures, by candidate.
    ie_rows = get_all("/schedules/schedule_e/by_candidate/", {
        "committee_id": UDP_SUPER_PAC,
        "candidate_id": fec_ids,
        "cycle": CYCLES,
    })
    print(f"United Democracy Project: {len(ie_rows)} candidate/cycle spending totals.")
    super_pac = defaultdict(lambda: {"support": 0.0, "oppose": 0.0})
    for r in ie_rows:
        side = "support" if r.get("support_oppose_indicator") == "S" else "oppose"
        super_pac[r["candidate_id"]][side] += r.get("total") or 0

    # 4. Assemble output.
    races_out = []
    for race in ballot["races"]:
        cands_out = []
        for c in race["candidates"]:
            fid = c["fec_id"]
            entry = {
                "name": c["name"],
                "party": c["party"],
                "incumbent": bool(c.get("incumbent")),
                "fec_id": fid,
            }
            if fid:
                by_cycle = {
                    cy: {k: round(v, 2) if isinstance(v, float) else v for k, v in vals.items()}
                    for cy, vals in sorted(money[fid].items())
                }
                direct = round(sum(v["direct"] for v in money[fid].values()), 2)
                earmarked = round(sum(v["earmarked"] for v in money[fid].values()), 2)
                entry.update({
                    "aipac_pac": {
                        "direct": direct,
                        "earmarked": earmarked,
                        "total": round(direct + earmarked, 2),
                        "by_cycle": by_cycle,
                        "source_url": fec_search_link("disbursements", {
                            "committee_id": AIPAC_PAC,
                            "recipient_committee_id": candidate_committees[fid],
                            "two_year_transaction_period": CYCLES,
                        }),
                    },
                    "super_pac": {
                        "support": round(super_pac[fid]["support"], 2),
                        "oppose": round(super_pac[fid]["oppose"], 2),
                        "source_url": fec_search_link("independent-expenditures", {
                            "committee_id": UDP_SUPER_PAC,
                            "candidate_id": fid,
                        }),
                    },
                    "fec_url": f"https://www.fec.gov/data/candidate/{fid}/",
                })
            cands_out.append(entry)
        races_out.append({**{k: race[k] for k in ("office", "district", "title")}, "candidates": cands_out})

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "election_date": ballot["election_date"],
        "cycles": CYCLES,
        "ballot_source": ballot["_source"],
        "races": races_out,
    }
    text = json.dumps(out, indent=1)
    if API_KEY != "DEMO_KEY" and API_KEY in text:  # belt and braces: never publish the key
        sys.exit("Refusing to write output: it contains the API key.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(str(e))
