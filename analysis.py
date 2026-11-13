"""
Why Are NY Housing Vouchers Going Unused? -- data rebuild script
================================================================

Run it with:   python3 analysis.py

What it does, in plain terms:
  1. Reads HCR's own per-area voucher numbers from the NYS Comptroller's audit
     2022-S-28 (the Exhibit on pages 25-26: % of vouchers issued, % of issued
     vouchers that families managed to use, April 2017 - March 2022).
  2. Reads HUD's "Picture of Subsidized Households" files (2017-2025) to get
     HCR's statewide voucher use each year and the voucher use of every OTHER
     New York housing agency (the "local peers").
  3. Reads HUD's FY2021 Fair Market Rents (what a voucher is designed to pay).
  4. Downloads Census ACS 5-year 2017-2021 county data (what the market charges,
     how many rentals sit empty, how many renters are cost-burdened).
  5. Combines everything for each HCR area, labels it market-constrained /
     administration-constrained / mixed, and writes the results to data/*.csv
     and into index.html so the page works offline.

Only Python's built-in libraries are used -- nothing to install.

WHY SOME FILES MUST BE DOWNLOADED BY HAND: huduser.gov blocks automated
downloads (it answers scripts with an empty "202" bot-check page). So the HUD
files are downloaded once in a normal web browser and saved in data/raw/hud/.
The exact URLs are listed in HUD_FILES below and in README.md.

Census data is downloaded automatically. You need a free Census API key
(https://api.census.gov/data/key_signup.html) saved in a file named
`.census_key` next to this script.

This is an independent analysis using public data only. Results are
INDICATORS, not proof of why vouchers went unused.
"""

import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# 0. SETTINGS -- change the thresholds here and re-run. Nothing else needed.
# ---------------------------------------------------------------------------
THRESHOLDS = {
    # HUD expects agencies to use at least 95% of their vouchers.
    # Below this, an area counts as "low use".
    "use_standard": 95.0,
    # Share of allocated vouchers that HCR actually handed out (issued).
    # Below this = an ISSUANCE shortfall (points to administration).
    "issued_ok": 95.0,
    # Share of issued vouchers that families managed to lease up with.
    # Below this = a LEASING shortfall (families can't find a unit).
    "success_ok": 95.0,
    # Rent gap = typical 2-bedroom rent (Census) / 2-bedroom Fair Market Rent.
    # At or above this, the voucher may not cover typical rents.
    "rent_gap_high": 1.00,
    # Rental vacancy rate (%). Below this the market is "tight": few empty units.
    "vacancy_low": 5.0,
    # If other housing agencies in the same county use this many percentage
    # points MORE of their vouchers than HCR does, HCR "lags its local peers".
    "peer_lag_pts": 5.0,
    # Does a "tight market" need BOTH a high rent gap AND low vacancy (True),
    # or is EITHER one enough (False)? Default False: the Census median rent
    # includes long-time tenants on older, cheaper leases, so it reads low next
    # to the FMR (which is based on recent movers). Requiring both would let
    # almost no area count as tight. See README "Thresholds".
    "tight_market_needs_both": False,
}

HCR_CODE = "NY904"  # HUD code for NYS Housing Trust Fund Corporation (HCR's voucher program)
ACS_YEAR = 2021     # ACS 5-year 2017-2021 = same years as the audit (Apr 2017 - Mar 2022)
PEER_YEARS = [2017, 2018, 2019, 2020, 2021]  # HUD years averaged for the peer comparison

NYC_COUNTIES = ["36005", "36047", "36061", "36081", "36085"]  # Bronx, Kings, New York, Queens, Richmond

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")

HUD_BASE = "https://www.huduser.gov/portal/datasets/pictures/files/"
HUD_FILES = {  # year -> file name in data/raw/hud/  (download from HUD_BASE + name)
    2017: "PHA_2017.xlsx",
    2018: "PHA_2018.xlsx",
    2019: "PHA_2019.xlsx",
    2020: "PHA_2020.xlsx",
    2021: "PHA_2021.xlsx",
    2022: "PHA_2022_2020census.xlsx",
    2023: "PHA_2023_2020census.xlsx",
    2024: "PHA_2024_2020census.xlsx",
    2025: "PHA_2025_2020census.xlsx",
}
FMR_FILE = "FY21_4050_FMRs_rev.xlsx"
FMR_URL = "https://www.huduser.gov/portal/datasets/fmr/fmr2021/" + FMR_FILE

# Audit Table 1 (page 12): HCR statewide, monthly averages per calendar year.
AUDIT_TABLE1 = [
    # year, vouchers available / month, units leased / month, vouchers not used
    (2017, 48422, 44754, 3668),
    (2018, 48581, 44350, 4231),
    (2019, 48974, 44675, 4299),
    (2020, 49211, 45004, 4207),
    (2021, 49576, 44704, 4872),
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def say(msg):
    print(msg, flush=True)


def num(x):
    """Turn a cell into a number, or None if it's blank / a HUD 'suppressed' code.
    HUD uses negative numbers (-1, -4, -5 ...) to mean 'not available'."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v < 0 else v


def write_csv(name, rows, fields=None):
    path = os.path.join(DATA, name)
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    say(f"   wrote data/{name} ({len(rows)} rows)")


def read_xlsx(path):
    """Read the first sheet of an .xlsx file and yield one dict per row.
    (An .xlsx file is just a zip of XML files; this avoids needing pandas.)"""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for _, el in ET.iterparse(z.open("xl/sharedStrings.xml")):
                if el.tag == ns + "si":
                    shared.append("".join(t.text or "" for t in el.iter(ns + "t")))
                    el.clear()
        header = None
        for _, el in ET.iterparse(z.open("xl/worksheets/sheet1.xml")):
            if el.tag != ns + "row":
                continue
            cells = {}
            for c in el.findall(ns + "c"):
                col = re.match(r"[A-Z]+", c.get("r")).group()
                kind, v = c.get("t"), c.find(ns + "v")
                if kind == "s":
                    val = shared[int(v.text)] if v is not None else ""
                elif kind == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(ns + "t"))
                else:
                    val = v.text if v is not None else ""
                cells[col] = val
            el.clear()
            if header is None:
                header = cells
                continue
            yield {name: cells.get(col, "") for col, name in header.items()}


def point_in_polygon(x, y, ring):
    """Classic ray-casting test: is the point (x=lon, y=lat) inside this ring?"""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def county_of_point(lon, lat, shapes):
    for fips, polys in shapes:
        for poly in polys:
            if point_in_polygon(lon, lat, poly[0]) and not any(
                point_in_polygon(lon, lat, hole) for hole in poly[1:]
            ):
                return fips
    # Point falls just outside every shape (e.g. on the coastline): use the
    # county with the nearest boundary point.
    best, best_d = "", None
    for fips, polys in shapes:
        for poly in polys:
            for px, py in poly[0]:
                d = (px - lon) ** 2 + (py - lat) ** 2
                if best_d is None or d < best_d:
                    best, best_d = fips, d
    return best


# ---------------------------------------------------------------------------
# 1. County list and shapes
# ---------------------------------------------------------------------------
def load_counties():
    say("1. County shapes (Census cartographic boundaries, already in data/ny_counties.geojson)")
    gj = json.load(open(os.path.join(DATA, "ny_counties.geojson")))
    names, shapes = {}, []
    for f in gj["features"]:
        fips = f["properties"]["GEOID"]
        names[fips] = f["properties"]["NAME"]
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        shapes.append((fips, polys))
    say(f"   {len(names)} counties")
    return names, shapes


# ---------------------------------------------------------------------------
# 2. The audit's per-area table (HCR's own numbers)
# ---------------------------------------------------------------------------
def load_audit_areas():
    say("2. Audit 2022-S-28 Exhibit (per-area issuance and leasing, Apr 2017 - Mar 2022)")
    path = os.path.join(RAW, "osc", "osc_2022s28_exhibit_areas.csv")
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        r["pct_issued"] = float(r["pct_issued"])
        r["pct_used"] = float(r["pct_used"])
    say(f"   {len(rows)} areas")
    return rows


# ---------------------------------------------------------------------------
# 3. HUD Picture of Subsidized Households: every NY voucher agency, 2017-2025
# ---------------------------------------------------------------------------
def load_hud_psh(shapes):
    say("3. HUD Picture of Subsidized Households (PHA files, Housing Choice Vouchers)")
    missing = [n for n in HUD_FILES.values() if not os.path.exists(os.path.join(RAW, "hud", n))]
    if missing:
        say("   MISSING HUD files. Download these in a web browser and save them in data/raw/hud/:")
        for n in missing:
            say("     " + HUD_BASE + n)
        sys.exit(1)
    out = []
    for year, fname in HUD_FILES.items():
        n = 0
        for r in read_xlsx(os.path.join(RAW, "hud", fname)):
            # program 3 = Housing Choice Vouchers. From 2025 HUD also adds
            # tenant-/project-based sub-rows; keep only the all-vouchers row.
            if r.get("program") not in ("3", "3.0") or not str(r.get("code", "")).startswith("NY"):
                continue
            if r.get("sub_program") not in ("NA", "N/A", ""):
                continue
            lat, lon = num(r.get("latitude")), r.get("longitude")
            try:
                lon = float(lon)
            except (TypeError, ValueError):
                lon = None
            county = county_of_point(lon, lat, shapes) if lat and lon else ""
            out.append({
                "year": year,
                "code": r["code"],
                "name": r["name"],
                "hq_county_fips": county,
                "vouchers_available": num(r["total_units"]),
                "pct_in_use": num(r["pct_occupied"]),
                "hud_spending_per_month": num(r["spending_per_month"]),
            })
            n += 1
        say(f"   {year}: {n} NY voucher agencies  ({fname})")
    write_csv("hud_psh_ny_vouchers_by_agency.csv", out)
    return out


# ---------------------------------------------------------------------------
# 4. HUD Fair Market Rents, FY2021
# ---------------------------------------------------------------------------
def load_fmr():
    say("4. HUD Fair Market Rents FY2021 (county level)")
    path = os.path.join(RAW, "hud", FMR_FILE)
    if not os.path.exists(path):
        say("   MISSING. Download in a web browser and save in data/raw/hud/: " + FMR_URL)
        sys.exit(1)
    fmr = {}
    rows = []
    for r in read_xlsx(path):
        if r.get("state_alpha") != "NY":
            continue
        fips = str(r["fips2010"])[:5]
        fmr[fips] = {"fmr_2br": num(r["fmr_2"]), "fmr_area": r["areaname"]}
        rows.append({"county_fips": fips, "county": r["countyname"], "fmr_area": r["areaname"],
                     "fmr_0br": r["fmr_0"], "fmr_1br": r["fmr_1"], "fmr_2br": r["fmr_2"],
                     "fmr_3br": r["fmr_3"], "fmr_4br": r["fmr_4"]})
    write_csv("hud_fmr_fy2021_ny_counties.csv", rows)
    return fmr


# ---------------------------------------------------------------------------
# 5. Census ACS 5-year 2017-2021, county level
# ---------------------------------------------------------------------------
ACS_VARS = {
    "B25031_004E": "median_gross_rent_2br",   # Median gross rent, 2 bedrooms
    "B25064_001E": "median_gross_rent_all",   # Median gross rent, all units
    "B25003_003E": "renter_households",       # Renter-occupied units
    "B25004_002E": "vacant_for_rent",         # Vacant units: for rent
    "B25004_003E": "vacant_rented_not_occ",   # Vacant units: rented, not yet occupied
    "B25070_001E": "burden_universe",         # Renter households (gross rent as % of income)
    "B25070_007E": "burden_30_35",
    "B25070_008E": "burden_35_40",
    "B25070_009E": "burden_40_50",
    "B25070_010E": "burden_50_plus",
    "B25070_011E": "burden_not_computed",
}


def load_acs():
    say(f"5. Census ACS 5-year {ACS_YEAR - 4}-{ACS_YEAR} (api.census.gov)")
    cache = os.path.join(RAW, "acs", f"acs5_{ACS_YEAR}_ny_counties.json")
    if not os.path.exists(cache):
        key = os.environ.get("CENSUS_API_KEY")
        kf = os.path.join(HERE, ".census_key")
        if not key and os.path.exists(kf):
            key = open(kf).read().strip()
        if not key:
            say("   No Census API key. Save it in .census_key (see README).")
            sys.exit(1)
        q = urllib.parse.urlencode({"get": "NAME," + ",".join(ACS_VARS), "for": "county:*",
                                    "in": "state:36", "key": key})
        url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5?{q}"
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as resp:
            open(cache, "w").write(resp.read().decode())
        say("   downloaded and cached in data/raw/acs/")
    table = json.load(open(cache))
    head, rows = table[0], table[1:]
    acs = {}
    out = []
    for r in rows:
        d = dict(zip(head, r))
        fips = "36" + d["county"]
        v = {name: num(d[code]) for code, name in ACS_VARS.items()}
        # Rental vacancy rate, Census definition:
        #   for-rent vacant / (renter-occupied + for-rent vacant + rented-not-occupied)
        denom = (v["renter_households"] or 0) + (v["vacant_for_rent"] or 0) + (v["vacant_rented_not_occ"] or 0)
        v["rental_vacancy_pct"] = 100 * v["vacant_for_rent"] / denom if denom else None
        # Rent-burdened = paying 30%+ of income on rent (among households where it can be computed)
        burdened = sum(v[k] or 0 for k in ("burden_30_35", "burden_35_40", "burden_40_50", "burden_50_plus"))
        computed = (v["burden_universe"] or 0) - (v["burden_not_computed"] or 0)
        v["burdened"] = burdened
        v["burden_computed"] = computed
        v["rent_burdened_pct"] = 100 * burdened / computed if computed else None
        acs[fips] = v
        out.append({"county_fips": fips, "county": d["NAME"].replace(", New York", ""), **v})
    write_csv(f"acs5_{ACS_YEAR - 4}_{ACS_YEAR}_ny_counties.csv", out)
    return acs


# ---------------------------------------------------------------------------
# 6. Put it together
# ---------------------------------------------------------------------------
def market_for(counties, acs, fmr):
    """Market numbers for one or more counties (combined, weighted by renters)."""
    counties = [c for c in counties if c in acs]
    if not counties:
        return {}
    rent_w = sum(acs[c]["renter_households"] for c in counties)
    gaps = [(acs[c]["median_gross_rent_2br"] / fmr[c]["fmr_2br"], acs[c]["renter_households"])
            for c in counties
            if acs[c]["median_gross_rent_2br"] and fmr.get(c, {}).get("fmr_2br")]
    gap = sum(g * w for g, w in gaps) / sum(w for _, w in gaps) if gaps else None
    for_rent = sum(acs[c]["vacant_for_rent"] for c in counties)
    denom = rent_w + for_rent + sum(acs[c]["vacant_rented_not_occ"] for c in counties)
    burd = sum(acs[c]["burdened"] for c in counties)
    comp = sum(acs[c]["burden_computed"] for c in counties)
    # Show dollar figures only for a single county (an average of medians is misleading)
    one = counties[0] if len(counties) == 1 else None
    return {
        "median_rent_2br": acs[one]["median_gross_rent_2br"] if one else None,
        "fmr_2br": fmr[one]["fmr_2br"] if one and one in fmr else None,
        "rent_gap": gap,
        "rental_vacancy_pct": 100 * for_rent / denom if denom else None,
        "rent_burdened_pct": 100 * burd / comp if comp else None,
        "renter_households": rent_w,
    }


def peers_for(counties, psh):
    """Voucher use of NON-HCR agencies headquartered in these counties,
    pooled over PEER_YEARS (vouchers in use / vouchers available)."""
    avail = used = 0
    names = set()
    for r in psh:
        if r["year"] in PEER_YEARS and r["code"] != HCR_CODE and r["hq_county_fips"] in counties:
            if r["vouchers_available"] and r["pct_in_use"] is not None:
                # A few small agencies report more than 100% in use (leasing
                # above their baseline); cap at 100 so one outlier can't skew it.
                avail += r["vouchers_available"]
                used += r["vouchers_available"] * min(r["pct_in_use"], 100) / 100
                names.add(r["name"])
    if not avail:
        return None, 0, ""
    return 100 * used / avail, len(names), "; ".join(sorted(names))


def classify(a):
    """Return (label, plain-English reason). Rules are stated in README.md."""
    T = THRESHOLDS
    use = a["hcr_est_use"]
    gap, vac, peer_gap = a.get("rent_gap"), a.get("rental_vacancy_pct"), a.get("peer_gap_pts")
    issued, used = a["pct_issued"], a["pct_used"]

    if use >= T["use_standard"]:
        return "Meets standard", f"About {use:.0f}% of allocated vouchers in use (standard is {T['use_standard']:.0f}%)."

    issuance_short = issued < T["issued_ok"]
    leasing_short = used < T["success_ok"]
    rent_high = gap is not None and gap >= T["rent_gap_high"]
    vac_low = vac is not None and vac < T["vacancy_low"]
    tight = (rent_high and vac_low) if T["tight_market_needs_both"] else (rent_high or vac_low)
    market_known = gap is not None or vac is not None
    lags = peer_gap is not None and peer_gap >= T["peer_lag_pts"]

    facts = [f"Issued: {issued:.0f}% of allocated vouchers", f"leased up: {used:.0f}% of holders"]
    if gap is not None:
        facts.append(f"rent gap {gap:.2f}")
    if vac is not None:
        facts.append(f"vacancy {vac:.1f}%")
    if peer_gap is not None:
        facts.append(f"local peers {'+' if peer_gap >= 0 else ''}{peer_gap:.0f} pts vs HCR")
    fact_txt = "; ".join(facts) + "."

    if leasing_short and not issuance_short and tight and not lags:
        why = []
        if rent_high:
            why.append("typical rents at or above what the voucher pays")
        if vac_low:
            why.append("few vacant rentals")
        return "Market-constrained", ("Vouchers were handed out but families couldn't lease: "
                                      + " and ".join(why) + ". " + fact_txt)
    if issuance_short and not leasing_short:
        return "Administration-constrained", ("Families who got vouchers leased up, but too few vouchers "
                                              "were issued. " + fact_txt)
    if lags and not tight and market_known:
        return "Administration-constrained", ("Market looks normal and other local agencies use more of "
                                              "their vouchers than HCR. " + fact_txt)
    if leasing_short and market_known and not tight:
        return "Mixed / unclear", ("Voucher holders struggled to lease even though rents look within the "
                                   "FMR and vacancy is normal: points to search barriers (landlord "
                                   "acceptance, unit quality/inspections, small rental stock) more than "
                                   "price. " + fact_txt)
    if issuance_short and leasing_short:
        return "Mixed / unclear", "Both issuance and leasing fell short. " + fact_txt
    return "Mixed / unclear", "Small shortfalls on several fronts; no single clear cause. " + fact_txt


def build(names, areas, psh, fmr, acs):
    say("6. Combining and classifying")
    results = []
    for a in areas:
        if a["county_fips"] == "NYC":
            counties = NYC_COUNTIES
        elif a["county_fips"]:
            counties = a["county_fips"].split(";")
        else:
            counties = []
        # NYC's big agencies (NYCHA, HPD) serve all five boroughs, so NYC areas
        # are compared with every agency headquartered anywhere in NYC.
        peer_counties = NYC_COUNTIES if set(counties) & set(NYC_COUNTIES) else counties
        m = market_for(counties, acs, fmr)
        peer_use, n_peers, peer_names = peers_for(peer_counties, psh)
        # Approximate share of allocated vouchers actually in use:
        #   (% of allocated vouchers issued, capped at 100) x (% of issued vouchers used)
        est_use = min(a["pct_issued"], 100) * a["pct_used"] / 100
        r = {
            "area": a["area"],
            "counties": ("New York City (boroughs not specified)" if a["county_fips"] == "NYC"
                         else "; ".join(names.get(c, c) for c in counties) if counties else "Unknown"),
            "county_fips": ";".join(counties),
            "mapping_note": a["mapping_note"],
            "is_main_county_area": a["is_main_county_area"],
            "pct_issued": a["pct_issued"],
            "pct_used": a["pct_used"],
            "hcr_est_use": round(est_use, 1),
            **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()},
            "peer_use_2017_2021": round(peer_use, 1) if peer_use is not None else None,
            "peer_gap_pts": round(peer_use - est_use, 1) if peer_use is not None else None,
            "n_peer_agencies": n_peers,
            "peer_agencies": peer_names,
        }
        r["classification"], r["reason"] = classify(r)
        results.append(r)
    results.sort(key=lambda r: r["hcr_est_use"])
    write_csv("hcr_areas_classified.csv", results)
    counts = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    say("   " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    return results


def statewide_trend(psh):
    """HCR statewide voucher use by year, plus the rough dollar estimate.
    Estimate of assistance not reaching families (per year):
        unused vouchers x average HUD subsidy per voucher per month x 12"""
    say("7. HCR statewide trend and dollar estimate")
    out = []
    hud = {r["year"]: r for r in psh if r["code"] == HCR_CODE}
    audit = {y: (av, le, nu) for y, av, le, nu in AUDIT_TABLE1}
    for year in sorted(set(hud) | set(audit)):
        h = hud.get(year)
        row = {"year": year}
        if year in audit:
            av, le, nu = audit[year]
            row.update(audit_vouchers_available=av, audit_units_leased=le, audit_unused=nu,
                       audit_use_pct=round(100 * le / av, 1))
        if h:
            unused = h["vouchers_available"] * (1 - h["pct_in_use"] / 100)
            row.update(hud_vouchers_available=int(h["vouchers_available"]), hud_pct_in_use=h["pct_in_use"],
                       hud_unused_est=round(unused), hud_subsidy_per_month=h["hud_spending_per_month"])
            # Prefer the audit's count of unused vouchers where we have it.
            n_unused = row.get("audit_unused", unused)
            row["unused_used_for_estimate"] = round(n_unused)
            row["unused_source"] = "Audit Table 1" if "audit_unused" in row else "HUD PSH"
            row["est_assistance_not_reaching_families"] = round(n_unused * h["hud_spending_per_month"] * 12)
        out.append(row)
    fields = ["year", "audit_vouchers_available", "audit_units_leased", "audit_unused", "audit_use_pct",
              "hud_vouchers_available", "hud_pct_in_use", "hud_unused_est", "hud_subsidy_per_month",
              "unused_used_for_estimate", "unused_source", "est_assistance_not_reaching_families"]
    write_csv("hcr_statewide_trend.csv", out, fields)
    return out


def county_map(names, results, acs, fmr):
    """One row per county for the map: the label of the county-wide HCR area."""
    by_county = {}
    for r in results:
        if r["is_main_county_area"] == "yes":
            for c in r["county_fips"].split(";"):
                by_county[c] = r
    sub = {}
    for r in results:
        if r["is_main_county_area"] == "no" and r["county_fips"] and r["county_fips"] != ";".join(NYC_COUNTIES):
            for c in r["county_fips"].split(";"):
                sub.setdefault(c, []).append(r["area"])
    out = []
    for fips, name in sorted(names.items(), key=lambda kv: kv[1]):
        r = by_county.get(fips)
        m = market_for([fips], acs, fmr)
        if r:
            label, area = r["classification"], r["area"]
        elif fips in NYC_COUNTIES:
            label, area = "NYC: boundary not published", "New York / New York North (boroughs not defined in audit)"
        else:
            label, area = "No HCR area in audit", ""
        out.append({
            "county_fips": fips, "county": name, "hcr_area": area, "classification": label,
            "hcr_est_use": r["hcr_est_use"] if r else None,
            "other_hcr_areas_here": "; ".join(sub.get(fips, [])),
            "rent_gap": round(m["rent_gap"], 3) if m.get("rent_gap") else None,
            "rental_vacancy_pct": round(m["rental_vacancy_pct"], 1) if m.get("rental_vacancy_pct") is not None else None,
            "median_rent_2br": m.get("median_rent_2br"), "fmr_2br": m.get("fmr_2br"),
        })
    write_csv("county_map.csv", out)
    return out


def inject_into_page(payload):
    page = os.path.join(HERE, "index.html")
    if not os.path.exists(page):
        say("   index.html not found; skipped")
        return
    html = open(page).read()
    blob = "/*DATA_START*/" + json.dumps(payload, separators=(",", ":")) + "/*DATA_END*/"
    html, n = re.subn(r"/\*DATA_START\*/.*?/\*DATA_END\*/", lambda _: blob, html, flags=re.S)
    if n != 1:
        say("   could not find the data marker in index.html; skipped")
        return
    open(page, "w").write(html)
    say("   refreshed the data inside index.html")


def main():
    names, shapes = load_counties()
    areas = load_audit_areas()
    psh = load_hud_psh(shapes)
    fmr = load_fmr()
    acs = load_acs()
    results = build(names, areas, psh, fmr, acs)
    trend = statewide_trend(psh)
    cmap = county_map(names, results, acs, fmr)
    say("8. Updating index.html")
    geo = json.load(open(os.path.join(DATA, "ny_counties.geojson")))
    inject_into_page({"thresholds": THRESHOLDS, "areas": results, "trend": trend,
                      "counties": cmap, "geo": geo})
    say("Done.")


if __name__ == "__main__":
    main()
