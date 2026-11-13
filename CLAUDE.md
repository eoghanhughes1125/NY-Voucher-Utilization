# Project: Why Are NY Housing Vouchers Going Unused? (Voucher Utilization Analyzer)

## Goal
Analyze where Housing Choice Vouchers (Section 8) administered by NYS Homes and Community Renewal
(HCR) go unused, and sort areas into likely causes:
- **Market-constrained:** vouchers are issued but families can't find units (tight market, rents
  above what the voucher pays).
- **Administration-constrained:** vouchers aren't being issued even though families who get them
  succeed in leasing.
- **Mixed / unclear.**

This is an independent analysis using public data only. We don't have HCR's internal records.
Label conclusions as indicators, not proof.

## Background (the problem this addresses)
From the NYS Comptroller's March 2023 audit (Report 2022-S-28):
- HCR did not meet HUD's 95% voucher-use standard in any year from 2017 to 2022.
- Share of HCR's 53 voucher areas using less than 95% rose from 30% (SFY 2017-18) to over 76%
  (SFY 2021-22).
- Up to $36M in surplus funds could have supported ~3,062 more vouchers in 2021; administrative
  fee reserves doubled to ~$131M.
- Two different failure patterns, which this project should separate:
  - Brooklyn ("Eastern NYC"): only ~82% of available vouchers distributed, but 99% of families who
    got one used it → looks like an issuance/administration problem.
  - Schuyler County: 99% issued, but only 87% used → looks like a market/search problem.
- HCR hadn't fully investigated why vouchers went unused.
- Press release: https://www.osc.ny.gov/press/releases/2023/03/dinapoli-federal-housing-aid-going-unused-despite-new-yorks-affordable-housing-crisis

## Data sources (verify each before using; note the year of every dataset)
1. **Voucher use by agency:** HUD Housing Choice Voucher data.
   - HUD "Picture of Subsidized Households" (huduser.gov): units, % occupied, tenant
     characteristics, by public housing agency (PHA), county, and tract.
   - HUD HCV Data Dashboard / Voucher Management System data for leasing and budget utilization
     by PHA, if available.
   - Find HCR's PHA code(s) and how its local administrators map to counties. Don't assume the
     code; look it up and cite it.
2. **What the voucher pays:** HUD Fair Market Rents by county/metro (and Small Area FMRs where they
   apply), huduser.gov.
3. **What the market charges and how tight it is:** Census ACS 5-year, county level, NY (FIPS 36):
   median gross rent, rental vacancy rate, share of renters who are rent-burdened, number of
   rental units. Use the Census API (api.census.gov).
4. **Comparison group:** other NY PHAs' voucher use in the same counties, so we can see whether HCR
   lags local peers in the same market (points to administration) or everyone struggles there
   (points to the market).

If HUD data doesn't line up neatly with HCR's 53 areas, work at the county level and explain the
mismatch in the README.

## Analysis
For each county/area:
- Voucher use rate (and trend over available years)
- Rent gap: median gross rent ÷ FMR (above ~1.0 means the voucher may not cover typical rents)
- Rental vacancy rate
- HCR's use rate vs. other PHAs in the same county
- Classify:
  - Low use + high rent gap + low vacancy → **market-constrained**
  - Low use + rents within FMR / normal vacancy, or HCR lags local peers → **administration-constrained**
  - Otherwise → mixed/unclear
- Keep thresholds simple, stated up front, and easy to change in one place.
- Rough dollar estimate: unused vouchers × average subsidy = assistance not reaching families.
  Show the formula and label it an estimate.
- Sanity check: do Brooklyn and Schuyler land where the audit's numbers suggest? If not, explain why.

## Deliverables
- `analysis.py` (or a notebook) that downloads/cleans data and writes `data/` CSVs
- `index.html`: single self-contained page with:
  - NY county map colored by classification
  - scatter plot: rent gap vs. voucher use rate
  - sortable table of the worst-performing areas with the reason for each label
  - short summary of findings and a "Data sources / Limitations" section
- `README.md`: method, thresholds, every source with dataset year, limitations
- `findings.md`: 1-page plain-English memo of the 3–5 most important takeaways and what HCR could
  do about each (e.g., higher payment standards in market-constrained areas; review local
  administration where issuance lags)

## Rules
- Cite a source and year for every number. Never invent data; mark gaps as unknown.
- Treat correlations as indicators, not causes.
- Keep code readable. I'm a finance/real estate student, not a software engineer;
  explain each step in plain terms.
- Check the page in a browser and make sure it works at phone width.
