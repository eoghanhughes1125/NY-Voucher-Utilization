# Why Are NY Housing Vouchers Going Unused?

A county-level look at where NYS Homes and Community Renewal (HCR) leaves Section 8 Housing Choice
Vouchers unused, and whether each area looks **market-constrained** (families get vouchers but can't
find a unit) or **administration-constrained** (vouchers aren't issued, though families who get one
do lease up).

> **Independent analysis using public data only.** It uses none of HCR's internal records. Every label
> is an indicator of where to look, not proof of why vouchers went unused.

## Files

| File | What it is |
|---|---|
| `index.html` | The page: map, scatter plot, sortable table, statewide trend, sources and limitations. All data is built in, so it opens offline by double-clicking. |
| `analysis.py` | Rebuilds every CSV from the raw files and refreshes the data inside `index.html`. Built-in Python libraries only. |
| `findings.md` | One-page memo: main takeaways and what HCR could do. |
| `data/hcr_areas_classified.csv` | **Main result.** One row per HCR area with every metric, the label and the reason. |
| `data/county_map.csv` | One row per county, as coloured on the map. |
| `data/hcr_statewide_trend.csv` | HCR statewide use 2017–2025 and the dollar estimate. |
| `data/hud_psh_ny_vouchers_by_agency.csv` | Every NY voucher agency, 2017–2025, with the county it is based in. |
| `data/hud_fmr_fy2021_ny_counties.csv` | FY2021 Fair Market Rents by county. |
| `data/acs5_2017_2021_ny_counties.csv` | Census rent, vacancy and rent-burden figures by county. |
| `data/raw/` | Untouched downloads, plus the audit table transcribed to CSV. |

## How to rebuild

1. Census key: get a free key at <https://api.census.gov/data/key_signup.html> and save it in a file
   named `.census_key` in this folder. It is already there, copied from your veterans project.
2. HUD files: huduser.gov blocks scripts, so these are downloaded once in a web browser into
   `data/raw/hud/`. They are already there. If any go missing, the script lists the URLs.
3. Run `python3 analysis.py` (about 25 seconds), then open `index.html`.

To change a threshold, edit the `THRESHOLDS` block at the top of `analysis.py` and re-run.

## Method, step by step

1. **HCR's own numbers by area.** The Comptroller's audit 2022-S-28 has an Exhibit (pp. 25–26) listing
   HCR's 59 voucher areas, April 2017–March 2022. For each it gives (a) the % of allocated vouchers HCR
   *issued* and (b) the % of issued vouchers families *used* (leased a unit). We transcribed it to
   `data/raw/osc/osc_2022s28_exhibit_areas.csv` and checked it against the PDF (also saved there).
   This is the only public source for HCR's performance below the statewide level.
2. **Estimated share in use** = min(% issued, 100) × % used. Brooklyn: 82% × 99% ≈ 81%. That fits the
   audit's statement that under 83% of Brooklyn vouchers were used.
3. **Areas mapped to counties.** Most areas are one county. Special cases:
   - "New York East" = Kings County (Brooklyn). The OSC press release says Brooklyn is part of HCR's
     "Eastern New York City".
   - "Bronx & Queens" = both counties.
   - "New York" and "New York North": boroughs not defined. NYC-wide market data is used and they are
     not mapped.
   - Towns: Hempstead → Nassau, Eastchester → Westchester, Jay → Essex.
   - Apple Meadow and Embury: location not given. They are in the table only.
4. **What the voucher pays:** HUD's FY2021 2-bedroom Fair Market Rent (the middle of the audit period).
5. **What the market charges:** Census ACS 5-year 2017–2021, the same years as the audit.
   - **Rent gap** = median gross rent for 2-bedroom units (B25031_004E) ÷ 2-bedroom FMR. We use
     2-bedroom rent rather than all-unit rent so the two sides compare like with like.
   - **Rental vacancy rate** = vacant for rent ÷ (renter-occupied + vacant for rent + rented, not yet
     occupied), using B25004 and B25003. This is the Census Bureau's definition.
   - **Rent-burdened share** = renters paying 30%+ of income on rent (B25070). It is in the CSVs as
     context but not used in the labels.
   - For multi-county areas, the counties are combined, weighted by number of renter households.
6. **Local peers:** HUD Picture of Subsidized Households, Housing Choice Vouchers. Other NY agencies
   based in the same county (located from HUD's coordinates), pooled 2017–2021: vouchers in use ÷
   vouchers available. Each agency is capped at 100%. For NYC areas the peers are all NYC agencies,
   since NYCHA and HPD serve every borough.
   **Peers vs HCR** = peer % − HCR estimated %. Positive means HCR is behind.
7. **Label** (rules below).
8. **Dollar estimate** (statewide only): see below.

## Thresholds (all in `THRESHOLDS` at the top of `analysis.py`)

| Setting | Value | Meaning |
|---|---|---|
| `use_standard` | 95% | HUD's utilization standard. At or above it, the area is "Meets standard". |
| `issued_ok` | 95% | Below this % of allocated vouchers issued = issuance shortfall |
| `success_ok` | 95% | Below this % of holders leasing = leasing shortfall |
| `rent_gap_high` | 1.00 | Typical 2-bedroom rent at or above the FMR |
| `vacancy_low` | 5% | Rental vacancy below this = tight market |
| `peer_lag_pts` | 5 pts | Local agencies use this many points more than HCR = HCR lags peers |
| `tight_market_needs_both` | False | False: a high rent gap **or** low vacancy counts as tight. True: both are needed. |

**Rules**, applied in this order to areas under 95%:

1. **Market-constrained.** Leasing shortfall, with issuance OK, in a tight market, and HCR does not lag
   its peers.
2. **Administration-constrained.** Either an issuance shortfall while holders lease fine, or the market
   is *not* tight and HCR lags local peers.
3. **Mixed / unclear.** Everything else, including a leasing shortfall in a market that looks normal.

**Where this differs from the original brief, and why:**

- *Either signal vs both.* The brief asked for "high rent gap + low vacancy". Only 14 of 62 counties
  reach a rent gap of 1.0. The Census median includes long-time and rent-stabilized tenants, while the
  FMR is built from recent movers, so the rent gap reads low almost everywhere. Requiring both signals
  would label only Tompkins market-constrained. Set `tight_market_needs_both = True` to use the
  stricter rule.
- *Normal market but holders can't lease.* The brief would call this administration. We call it
  "mixed / unclear". When holders fail to lease where rents look affordable, the cause is usually
  something else, such as landlord acceptance, failed inspections or a small rental stock. HCR's local
  administrators can influence some of that, but it isn't an issuance problem.

**Sanity check:** Brooklyn ("New York East") is labelled administration-constrained (82% issued, 99%
leased). Schuyler is labelled market-constrained (99% issued, 87% leased, vacancy 3.2%). Both match
the audit's description. Schuyler's rents are close to the FMR (gap 0.98), so it qualifies through low
vacancy, not price.

## Dollar estimate

```
assistance not reaching families (per year) = unused vouchers × HUD's average subsidy per voucher per month × 12
```

- Unused vouchers: 2017–2021 from audit Table 1. 2022–2025 from HUD: vouchers available × (1 − % in use).
- Subsidy: HUD PSH `spending_per_month` for HCR (NY904) in that year.
- Result: about $63M in 2021 and about $128M in 2025 (6,771 × $1,580 × 12).
- This is an **estimate**. HUD funds agencies by budget, not per voucher. HCR told auditors that its
  budget did not allow it to lease every voucher. The audit's own figure is up to $36M in 2021 surplus
  funds, enough for about 3,062 vouchers. HUD rounds % in use to whole numbers, so 2022–2025 counts are
  ±~250 vouchers.
- There is no area-level dollar figure because voucher counts by area are not public.

## Data sources (with dataset year)

| Source | Year / period | Used for |
|---|---|---|
| NYS Comptroller, [Audit 2022-S-28](https://www.osc.ny.gov/state-agencies/audits/2023/03/16/housing-trust-fund-corporation-internal-controls-over-and-maximization-federal-funding) (PDF in `data/raw/osc/`) | Issued 16 Mar 2023. Exhibit covers Apr 2017–Mar 2022. Table 1 covers CY 2017–2021. | Per-area issuance and leasing. Statewide unused vouchers. |
| NYS Comptroller [press release](https://www.osc.ny.gov/press/releases/2023/03/dinapoli-federal-housing-aid-going-unused-despite-new-yorks-affordable-housing-crisis) | 16 Mar 2023 | Brooklyn = "Eastern NYC"; background |
| HUD [Picture of Subsidized Households](https://www.huduser.gov/portal/datasets/assthsg.html), PHA files `PHA_2017.xlsx` … `PHA_2025_2020census.xlsx` | 2017–2025 (each file is a calendar-year snapshot) | HCR statewide trend; local peer agencies |
| HUD [Fair Market Rents](https://www.huduser.gov/portal/datasets/fmr.html), `FY21_4050_FMRs_rev.xlsx` | FY2021 | 2-bedroom FMR by county |
| US Census Bureau ACS 5-year via api.census.gov: B25031, B25064, B25003, B25004, B25070 | 2017–2021 | Rent, vacancy, rent burden |
| Census cartographic boundary county shapes (`data/ny_counties.geojson`, from the veterans project) | 2020-vintage | Map; locating agencies |

**HCR's HUD code** is **NY904, "NYS Housing Trust Fund Corporation"**. It was found by searching the
HUD PHA files rather than assumed. The audit covers HTFC, through which HCR runs the program. As a
check, HUD's 2021 figures for NY904 (49,934 vouchers available, 89% in use) are close to audit Table 1
for 2021 (49,576 available, 90.2% used).

## Limitations

- Area-level HCR data exists only as a single 5-year average (the audit Exhibit). Area trends are
  unknown, and current (2025) area performance is unknown.
- "Est. in use" is the product of two audit percentages, not HUD's official utilization measure.
- Peers are agencies *headquartered* in a county. Their vouchers can be used elsewhere (portability),
  and HUD's "% in use" is measured differently from the audit. Most rural counties have no other
  agency, so their peer comparison is unknown.
- The rent gap understates market pressure, most of all in NYC, where stabilized rents pull the median
  down (Brooklyn's gap is 0.78).
- The FMR stands in for HCR's payment standards, which are not public by area and may be 90–110% of
  FMR or higher with exceptions.
- 2017–2021 ACS and FY2021 FMR describe the audit period, not today's market.
- Two NYC areas and two project areas (Apple Meadow, Embury) can't be placed on the map.
- Correlation is not causation. These are indicators to guide a closer review.
