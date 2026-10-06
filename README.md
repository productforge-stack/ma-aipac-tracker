# New England Candidates & AIPAC Money

A static website for the November 3, 2026 general election in Connecticut, Maine,
Massachusetts, New Hampshire, Rhode Island and Vermont. A voter enters a ZIP code
or street address and sees their U.S. Senate and U.S. House candidates with each
candidate's party, split into **received AIPAC PAC money** and **no AIPAC PAC money found**.

## What's here

| Path | Purpose |
|---|---|
| `site/` | The website: `index.html`, `app.js`, `style.css`, and `data/` |
| `config/ballot_2026.json` | Candidates printed on each state's general election ballot, with the source and date checked per state |
| `scripts/build_data.py` | Pulls FEC data and writes `site/data/candidates.json` |
| `scripts/build_zips.py` | Builds `site/data/zips.json` from the Census ZIP-to-district file (run once) |
| `.github/workflows/deploy.yml` | Daily data refresh and deploy to GitHub Pages |

## Data sources
- **AIPAC PAC** (FEC `C00797670`): direct contributions and earmarked/bundled contributions to each candidate's committees, 2022–2026 cycles.
- **United Democracy Project** (FEC `C00799031`, AIPAC's super PAC): spending for or against each candidate, shown separately.
- **ZIP → district**: Census 2020 ZCTA-to-congressional-district relationship files for the six states. Split ZIPs prompt for an address.
- **Address → district**: U.S. Census Geocoder, called from the visitor's browser. It needs no key.

## Keeping your FEC API key safe
- The key lives **only** in a GitHub Actions secret (for the daily refresh) or your local `.env` file (git-ignored).
- The website never sees the key. The build script uses it server-side and publishes only the finished JSON.
- The build script never prints the key and refuses to write output that contains it.
- If the key ever leaks, request a new one at https://api.data.gov/signup/. The old one stops mattering once you replace the secret.

## Run locally
```
copy .env.example .env          # then paste your key into .env
python scripts/build_data.py
python -m http.server 8000 --directory site
```
Then open http://localhost:8000.

## Publish free on GitHub Pages
1. Create a **public** GitHub repo and push this folder to its `main` branch.
2. Under **Settings → Secrets and variables → Actions → New repository secret**, add `FEC_API_KEY`.
3. Under **Settings → Pages**, set **Source** to **GitHub Actions**.
4. Under **Actions → Refresh FEC data and deploy**, click **Run workflow**. After that it refreshes every morning.

## Before sharing
- Spot-check a few candidates' totals against the linked FEC records.
- If a ballot changes (for example a withdrawal), edit `config/ballot_2026.json` and update that state's `checked` date.
- Connecticut's list was cross-checked against Ballotpedia and The Green Papers because the official SOTS list could not be read automatically. Confirm it against a CT sample ballot if you can.
- FEC data lags. Contributions made in the final weeks may not appear until after the election.
