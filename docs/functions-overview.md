# Heads of Loss

In this codebase context, `heads of loss` means the **categories of damages** being calculated.

Practically, your main heads are:
- Care
- Travel
- Vehicle
- Equipment
- Earnings
- Lost Years
- Pension
- Accommodation

General functions (CM/GC/GP/etc.) are calculation engines, not heads themselves.

# Functions Overview

This document summarizes the Streamlit-exposed calculation functions, the multiplier method(s) they use, and the core calculation flow.

## Global LE and Mortality Controls
- Life expectancy basis:
  - `standard`: use standard-life anchor routes (whole-life/additional-table derived in relevant flows).
  - `impaired`: use impairment inputs (`end_age` or `years_reduction`) and impaired anchor routes.
- Multiplier method switches (where available):
  - `term_certain`: uses term-certain style Table 36 pathing.
  - `find_appropriate_age`: uses alignment/anchor lookup from Additional Tables (or retirement-table fallback where implemented).
- Purchase mortality mode (Equipment, Vehicle):
  - `no_mortality`: no survival adjustment on purchase factors.
  - `use_mortality`: applies per-purchase survival adjustment to the Table 35 factor stream.

## 1) Continuous Multiplier (CM)
- Class: `ContinuousMultiplierCalculation`
- Multiplier methods:
  - Uses Table 36 apportionment for start/end/life term, then scales by a supplied life multiplier.
  - Life multiplier can come from whole-life/additional tables in UI flows.
- How it works:
  - Resolve start/end ages (with caps to life expectancy).
  - Convert to years from calculation age.
  - Interpolate Table 36 at start, end, and life-expectancy years.
  - Compute period multiplier: `((end - start) / life_term) * life_multiplier`.
- Lookups/tables: `ogden8table36dr05.csv`.

## 2) General Continuous (GC)
- Class: `GeneralContinuousCalculation`
- Multiplier methods: Reuses CM multiplier.
- How it works:
  - Convert periodic loss to annual loss.
  - Run CM for period multiplier.
  - Total = annual loss x period multiplier.
- Lookups/tables: Table 36 (via CM).

## 3) General Continuous (But For) (GCBF)
- Class: `GeneralContinuousButForCalculation`
- Multiplier methods: Reuses CM multiplier.
- How it works:
  - Annualise prior and result values.
  - Net annual loss = result - prior.
  - Apply CM period multiplier.
- Lookups/tables: Table 36 (via CM).

## 4) General One Off (GOF)
- Class: `GeneralOneOffCalculation`
- Multiplier methods: Table 35 deferment factor.
- How it works:
  - Compute deferment years from calculation age to start age.
  - Interpolate Table 35 at deferment.
  - Total = one-off amount x Table 35 factor.
- Lookups/tables: `ogden8table35dr05.csv`.

## 5) General Periodical (GP)
- Class: `GeneralPeriodicalCalculation`
- Multiplier methods:
  - Raw multiplier = sum of Table 35 factors at each scheduled purchase point.
  - Mortality adjustment = scale by `life_multiplier / Table36(life years)`.
- How it works:
  - Build purchase schedule from recurrence config.
  - Sum discounted factors (Table 35 interpolation).
  - Mortality-adjust multiplier using Table 36 term and life multiplier.
  - Total = loss amount x adjusted multiplier.
- Lookups/tables: `ogden8table35dr05.csv`, `ogden8table36dr05.csv`.

## 6) Lifetime (Split) (LS)
- Class: `LifetimeSplitCalculation`
- Multiplier methods: CM apportionment per phase.
- How it works:
  - Split claim into contiguous phases.
  - Annualise each phase amount by frequency.
  - Compute CM multiplier for each phase interval.
  - Sum phase totals.
- Lookups/tables: Table 36 (via CM).

## 7) Periodical Multiplier (PM)
- Class: `PeriodicalMultiplierCalculation`
- Multiplier methods: Same as GP (Table 35 schedule + Table 36 mortality scaling).
- How it works:
  - Delegates to GP and returns multiplier-focused outputs.
- Lookups/tables: `ogden8table35dr05.csv`, `ogden8table36dr05.csv`.

## 8) Care Annualisation
- Class: `CareCalculation`
- Multiplier methods: None (annualisation only).
- How it works:
  - Resolve period from ages or dates.
  - Resolve effective rate (manual or named care rate, less percentage deduction).
  - Annualise hours by increment rules (daily/weekly/monthly/weekday/weekend/specified modes).
  - Annualised cost = annualised hours x effective rate.
- Lookups/tables:
  - Date-mode calendar/day-count lookups (weekdays/weekends/day-of-week/public holidays).

## 9) Care Claim (Full)
- Class: `CareClaimCalculation`
- Multiplier methods: Care annualisation + CM-style Table 36 apportionment.
- How it works:
  - Compute annualised care cost via `CareCalculation`.
  - Compute period multiplier via `CareMultiplierCalculation`.
  - Total award = annualised cost x period multiplier.
- Lookups/tables: Table 36.

## 10) Care (Split)
- Class: `CareSplitCalculation` / `CareClaimCalculation.calculate_split`
- Multiplier methods: Per-phase care annualisation + per-phase Table 36 apportionment.
- How it works:
  - For each phase: annualise care and compute phase multiplier.
  - Compute phase award and aggregate total.
- Lookups/tables: Table 36.

## 11) Equipment
- Class: `EquipmentCalculation`
- Multiplier methods:
  - Capital replacement stream: sum of Table 35 factors at purchase years.
  - Recurring items (insurance/maintenance): Table 36 apportionment scaled by life multiplier.
- How it works:
  - Build purchase schedule by replacement cycle and boundary mode.
  - Discount each purchase using Table 35 (optional mortality adjustment mode).
  - Compute recurring multiplier from Table 36 start/end/life terms.
  - Total = capital total + recurring totals.
- Lookups/tables: `ogden8table35dr05.csv`, `ogden8table36dr05.csv`.

## 12) Travel Claim (Full)
- Class: `TravelClaimCalculation`
- Multiplier methods: Annual travel loss + Table 36 apportionment.
- How it works:
  - Compute annual travel loss (distance mode, mileage, parking, journey frequency).
  - Compute period multiplier from start/end/life years.
  - Total loss = annual loss x period multiplier.
- Lookups/tables: Table 36.

## 13) Vehicle
- Class: `VehicleCalculation`
- Multiplier methods:
  - Initial and replacement capital costs: Table 35 factors.
  - Annual extras (insurance/running): Table 36 apportionment scaled by life multiplier.
- How it works:
  - Calculate net initial and replacement costs.
  - Build replacement stream and discount via Table 35 (optional purchase mortality mode).
  - Compute annual-extras multiplier from Table 36 terms.
  - Sum initial + replacements + annual extras.
- Lookups/tables:
  - `ogden8table35dr05.csv`, `ogden8table36dr05.csv`.
  - Additional tables may be used in UI to derive standard/impaired life anchors:
    - `ogden8_additional_*_0.csv`, `ogden8_additional_*_05.csv`.

## 14) Earnings
- Class: `EarningsCalculation`
- Multiplier methods/configs:
  - `multiplier_mode=manual/auto`: retirement-anchor method using Table 36 apportionment and retirement table multiplier.
  - `multiplier_mode=additional`: period multiplier directly from Additional Tables deltas.
  - Impaired options: `term_certain` or `find_appropriate_age` for anchor selection.
  - Can auto-split across retirement boundary.
- How it works:
  - Annualise but-for/residual; convert gross to net if needed (tax/NI logic).
  - Determine period (pre/post retirement handling and optional split).
  - Build multiplier using selected mode and impairment config.
  - Total = net annual loss x final multiplier.
- Lookups/tables:
  - Table 36, retirement tables (3-18), whole-life table.
  - Additional tables (`additional_*05.csv`, `ogden8_additional_*_0.csv`, `ogden8_additional_*_05.csv`).
  - Table 35 in deferred impaired branches.

## 15) Earnings (ASHE)
- Class: `EarningsAsheCalculation`
- Multiplier methods: Delegates to `EarningsCalculation` modes above.
- How it works:
  - Load ASHE row/value (but-for/residual as configured).
  - Feed resolved amounts into `EarningsCalculation`.
- Lookups/tables:
  - ASHE workbook(s) (2025 bundled provisional table paths).
  - Then same tables as Earnings for multipliers.

## 16) Earnings (Split)
- Class: `EarningsSplitCalculation`
- Multiplier methods: Runs `EarningsCalculation` per phase with same mode options.
- How it works:
  - Evaluate each earnings phase independently.
  - Sum phase totals; keep per-phase multipliers and traces.
- Lookups/tables: Same as Earnings.

## 17) Earnings Award
- Class: `EarningsAwardCalculation`
- Multiplier methods: None.
- How it works:
  - Simple award pass-through/formatting calculation for entered amount.
- Lookups/tables: None.

## 18) Lost Years
- Class: `LostYearsCalculation`
- Multiplier methods/configs:
  - Base normalization from but-for life multiplier vs current-life multiplier.
  - Supports `term_certain` and `find_appropriate_age` style anchoring.
- How it works:
  - Compute lost-years ratio and multiplier normalization.
  - For each period, net annual x lost-years rate, then apply normalized Table 36 slice.
  - Optional pension lump-sum line uses Table 35 deferment.
  - Optional pension annual line uses normalized life slice.
- Lookups/tables:
  - Table 36, whole-life, additional tables (for anchor alignment), and optional Table 35.

## 19) Pension
- Class: `PensionCalculation`
- Multiplier methods/configs:
  - `multiplier_method=term_certain` or `find_appropriate_age`.
  - `life_expectancy_basis=Impaired|Standard` influences but-for life multiplier source.
- How it works:
  - Convert but-for and residual annuals to net (if gross).
  - Calculate mortality-to-retirement multiplier from Additional +0.5 table.
  - Determine but-for life multiplier by selected basis/method.
  - Pension multiplier = but-for life multiplier - mortality-to-retirement multiplier.
  - Total = net annual loss x pension multiplier.
- Lookups/tables:
  - Additional +0.5 table (required), optional Additional 0 for alignment, whole-life/Table 36 as configured.

## 20) Pension (Early receipt)
- Class: `PensionEarlyReceiptCalculation`
- Multiplier methods:
  - Lump-sum line uses Longden factor and Table 35 deferment discount.
  - Annual line reuses `PensionCalculation` multiplier logic.
- How it works:
  - Compute Longden factor at receipt age vs retirement anchor.
  - Discount expected lump sum to receipt timing (Table 35), compare to adjusted actual lump sum.
  - Compute annual pension loss x pension multiplier.
  - Total = lump-sum loss + annual-line total.
- Lookups/tables: Additional +0.5 table, Table 35, and Pension tables/methods.

## 21) Accommodation (RvJ)
- Class: `AccommodationRvJCalculation`
- Multiplier methods:
  - Ongoing annual line uses Table 36 apportionment scaled by life multiplier.
  - Adaptation line uses Table 35 deferment factor.
- How it works:
  - Compute capital increase and RvJ annual value.
  - Add increased running costs for ongoing annual.
  - Apply period multiplier to ongoing annual.
  - Discount adaptation net and add to ongoing total.
- Lookups/tables: Table 36 and Table 35.

## 22) Accommodation (Swift v Carpenter)
- Class: `AccommodationSwiftCarpenterCalculation`
- Multiplier methods:
  - Reversionary-interest discount for period at chosen rate.
  - Early-receipt discount via Table 35 at deferment start.
- How it works:
  - Compute net capital.
  - Compute reversionary interest and life interest.
  - Discount life interest at deferment using Table 35.
- Lookups/tables: Table 35.
