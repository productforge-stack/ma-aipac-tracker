"use strict";

const GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress";
const MA_FIPS = "25";

let data = null;   // candidates.json
let zips = null;   // zips.json

const $ = (id) => document.getElementById(id);
const money = (n) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// Small DOM builder. All text goes in through textContent, never innerHTML.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function link(href, text) {
  return el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

function setStatus(msg, isError = false) {
  const s = $("status");
  s.textContent = msg;
  s.classList.toggle("error", isError);
  if (isError) $("results").replaceChildren();  // don't leave stale results under an error
}

async function loadData() {
  const [c, z] = await Promise.all([
    fetch("data/candidates.json").then((r) => { if (!r.ok) throw new Error(); return r.json(); }),
    fetch("data/zips.json").then((r) => { if (!r.ok) throw new Error(); return r.json(); }),
  ]);
  data = c;
  zips = z;
  const updated = new Date(data.generated_at).toLocaleDateString("en-US", { dateStyle: "long" });
  $("sources").replaceChildren(
    `FEC data last refreshed ${updated}. Ballot: `,
    link(data.ballot_source.split(": ").pop(), "Massachusetts Secretary of the Commonwealth"),
    "."
  );
}

function partyClass(party) {
  const p = party.toLowerCase();
  if (p.startsWith("democrat")) return "party dem";
  if (p.startsWith("republican")) return "party rep";
  return "party other";
}

function candidateCard(c) {
  const a = c.aipac_pac;
  const s = c.super_pac;
  const took = a && a.total > 0;

  const head = el("div", { class: "card-head" },
    el("h4", {}, c.name),
    el("div", { class: "tags" },
      el("span", { class: partyClass(c.party) }, c.party),
      c.incumbent && el("span", { class: "tag" }, "Incumbent")
    )
  );

  let body;
  if (!c.fec_id) {
    body = el("p", { class: "verdict none" }, "Not registered with the FEC, so there are no federal filings to check.");
  } else if (took) {
    const cycles = Object.entries(a.by_cycle)
      .filter(([, v]) => v.direct + v.earmarked !== 0)
      .map(([cy, v]) => `${cy}: ${money(v.direct + v.earmarked)}`);
    body = el("div", {},
      el("p", { class: "verdict took" }, el("strong", {}, money(a.total)), " from AIPAC PAC"),
      el("ul", { class: "breakdown" },
        el("li", {}, `Direct contributions: ${money(a.direct)}`),
        el("li", {}, `Earmarked (bundled): ${money(a.earmarked)}`),
        cycles.length && el("li", {}, `By cycle — ${cycles.join(" · ")}`)
      )
    );
  } else {
    body = el("p", { class: "verdict none" }, "No AIPAC PAC money found in FEC filings.");
  }

  const spPieces = [];
  if (s && s.support > 0) spPieces.push(`${money(s.support)} supporting`);
  if (s && s.oppose > 0) spPieces.push(`${money(s.oppose)} opposing`);
  const superPac = spPieces.length
    ? el("p", { class: "superpac" }, `AIPAC's super PAC (United Democracy Project) spent ${spPieces.join(" and ")} this candidate. `,
        link(s.source_url, "FEC records"))
    : null;

  const links = c.fec_id
    ? el("p", { class: "links" }, link(a.source_url, "AIPAC PAC records"), " · ", link(c.fec_url, "FEC candidate page"))
    : null;

  return el("article", { class: `card ${took ? "is-took" : "is-none"}` }, head, body, superPac, links);
}

function raceSection(race, note) {
  const took = race.candidates.filter((c) => c.aipac_pac && c.aipac_pac.total > 0);
  const none = race.candidates.filter((c) => !(c.aipac_pac && c.aipac_pac.total > 0));
  const col = (title, list, cls) =>
    el("div", { class: `col ${cls}` },
      el("h3", {}, title, el("span", { class: "count" }, String(list.length))),
      list.length ? list.map(candidateCard) : el("p", { class: "empty" }, "None on this ballot.")
    );
  return el("section", { class: "race" },
    el("h2", {}, race.title),
    note && el("p", { class: "race-note" }, note),
    race.candidates.length === 1 && el("p", { class: "race-note" }, "Only one candidate is on the ballot for this seat."),
    el("div", { class: "cols" },
      col("Received AIPAC PAC money", took, "col-took"),
      col("No AIPAC PAC money found", none, "col-none")
    )
  );
}

function showDistricts(districts, how) {
  const races = data.races;
  const senate = races.find((r) => r.office === "S");
  const house = districts.map((d) => races.find((r) => r.office === "H" && r.district === d)).filter(Boolean);
  const split = house.length > 1;
  const out = [];
  out.push(raceSection(senate, "Every Massachusetts voter votes in this race."));
  for (const r of house) {
    out.push(raceSection(r, split ? "Your ZIP code is split between districts. Use the address search above to confirm which one is yours." : null));
  }
  $("results").replaceChildren(...out);
  const names = house.map((r) => r.title.replace("U.S. House, ", "")).join(" and the ");
  setStatus(`${how} ${names}.`);
  if (split) $("address-box").open = true;
}

function lookupZip(zip) {
  if (!/^\d{5}$/.test(zip)) return setStatus("Please enter a 5-digit ZIP code.", true);
  const districts = zips[zip];
  if (!/^(01|02|055)/.test(zip)) return setStatus(`${zip} isn't a Massachusetts ZIP code.`, true);
  if (!districts) {
    $("address-box").open = true;
    return setStatus(`We couldn't match ${zip} to a Massachusetts district (it may be a PO box or business ZIP). Try your street address instead.`, true);
  }
  showDistricts(districts, districts.length > 1 ? `ZIP ${zip} covers parts of the` : `ZIP ${zip} is in the`);
  history.replaceState(null, "", `?zip=${zip}`);
}

// The Census geocoder doesn't send CORS headers, but it supports JSONP.
function geocode(address) {
  return new Promise((resolve, reject) => {
    const cb = `__geo${Date.now()}${Math.floor(Math.random() * 1e6)}`;
    const script = document.createElement("script");
    const timer = setTimeout(() => finish(new Error("timeout")), 15000);
    function finish(err, result) {
      clearTimeout(timer);
      delete window[cb];
      script.remove();
      err ? reject(err) : resolve(result);
    }
    window[cb] = (json) => finish(null, json);
    const params = new URLSearchParams({
      address, benchmark: "Public_AR_Current", vintage: "Current_Current",
      layers: "54", format: "jsonp", callback: cb,
    });
    script.src = `${GEOCODER}?${params}`;
    script.onerror = () => finish(new Error("network"));
    document.head.append(script);
  });
}

async function lookupAddress(address) {
  if (address.trim().length < 6) return setStatus("Please enter a street address with city or ZIP.", true);
  setStatus("Looking up your address with the U.S. Census Bureau…");
  let json;
  try {
    json = await geocode(address);
  } catch (e) {
    return setStatus("The Census geocoder didn't respond. Please try again in a moment.", true);
  }
  const match = json?.result?.addressMatches?.[0];
  if (!match) return setStatus("No match found. Check the street number and spelling, and include the city or ZIP.", true);
  const layer = Object.entries(match.geographies || {}).find(([k]) => /Congressional Districts/i.test(k));
  const cd = layer && layer[1][0];
  if (!cd || cd.STATE !== MA_FIPS) return setStatus(`That address (${match.matchedAddress}) isn't in Massachusetts.`, true);
  showDistricts([parseInt(cd.BASENAME, 10)], `${match.matchedAddress} is in the`);
  history.replaceState(null, "", location.pathname);  // never keep the address in the URL
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadData();
  } catch {
    return setStatus("Couldn't load candidate data. Please refresh the page.", true);
  }
  $("zip-form").addEventListener("submit", (e) => { e.preventDefault(); lookupZip($("zip").value.trim()); });
  $("address-form").addEventListener("submit", (e) => { e.preventDefault(); lookupAddress($("address").value); });
  const zip = new URLSearchParams(location.search).get("zip");
  if (zip) { $("zip").value = zip; lookupZip(zip); }
});
