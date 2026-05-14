# Implementation Overview

Purpose: complete map of implemented calculation paths, alternatives, and selection triggers for use.

## How to Read This
- `Primary path`: default/typical route in current implementation.
- `Alternatives`: other implemented routes for the same outcome.
- `Trigger`: what input/setting switches to that route.
- `Sources`: tables/files looked up by that route.

## General Engines

### Continuous Multiplier (CM) (`ContinuousMultiplierCalculation`)
- Primary path:
  - Table 36 apportionment: `((T_end - T_start) / T_life) * life_multiplier`.
- Alternatives:
  - Start/end can be explicit ages or derived (`at calculation age` / `rest of life`).
  - Life multiplier can be provided/overridden or derived upstream.
  - Apportioning method selector:
    - `term_certain_end_minus_start` (Table 36 apportionment baseline).
    - `discount_factor_to_start_x_term_certain_period` (Table 35 discount-to-start x Table 36 period term, then life scaling).
- Trigger:
  - UI `start_mode`, `end_mode`, life-multiplier override, LE basis controls.
- Sources:
  - `data/ogden8table36dr05.csv`.
  - `data/ogden8table35dr05.csv` (when discount-factor apportionment method is selected).

### General Continuous (GC) (`GeneralContinuousCalculation`)
- Primary path:
  - Annualise periodic loss, then apply CM period multiplier.
- Alternatives:
  - Frequency variants: year/month/week/day.
  - Inherited CM apportioning method selector:
    - `term_certain_end_minus_start`.
    - `discount_factor_to_start_x_term_certain_period`.
- Trigger:
  - `loss_frequency`.
- Sources:
  - `data/ogden8table36dr05.csv` (through CM period-multiplier calculation).
  - `data/ogden8table35dr05.csv` (through CM when discount-factor apportionment method is selected).

### General Continuous But For (`GeneralContinuousButForCalculation`)
- Primary path:
  - Annualise prior and result streams; net annual x CM multiplier.
- Alternatives:
  - Frequency variants on both streams.
  - Inherited CM apportioning method selector:
    - `term_certain_end_minus_start`.
    - `discount_factor_to_start_x_term_certain_period`.
- Trigger:
  - `cost_prior_frequency`, `cost_result_frequency`.
- Sources:
  - `data/ogden8table36dr05.csv` (through CM period-multiplier calculation).
  - `data/ogden8table35dr05.csv` (through CM when discount-factor apportionment method is selected).

### General One Off (GOF) (`GeneralOneOffCalculation`)
- Primary path:
  - One-off amount x Table 35 deferment factor at start years.
- Alternatives:
  - Start at calculation age vs specific start age.
- Trigger:
  - `start_at_calculation_age`.
- Sources:
  - `data/ogden8table35dr05.csv`.

### General Periodical (GP) (`GeneralPeriodicalCalculation`)
- Primary path:
  - Build purchase schedule; sum Table 35 factors; mortality-adjust by `life_multiplier / Table36(life_years)`.
- Alternatives:
  - Recurrence units (days/weeks/months/years), PI parity rounding on/off.
  - PI parity mode meaning (in this function): rounding behavior only.
    - ON: round each Table 35 purchase factor to 2dp before summing, then round adjusted multiplier to 3dp.
    - OFF: keep full-precision factors and adjusted multiplier (no parity rounding).
- Trigger:
  - `recurrence_unit`, `pi_parity_mode`.
- Sources:
  - `data/ogden8table35dr05.csv`, `data/ogden8table36dr05.csv`.

### Periodical Multiplier (PM) (`PeriodicalMultiplierCalculation`)
- Primary path:
  - Uses the GP purchase-schedule engine and returns multiplier-focused outputs.
- Alternatives:
  - Recurrence units: days/weeks/months/years.
  - PI parity rounding on/off.
  - PI parity mode meaning (in this function): inherited GP rounding behavior only.
    - ON: 2dp rounding per Table 35 purchase factor + 3dp rounding of adjusted multiplier.
    - OFF: full-precision path (no parity rounding).
- Trigger:
  - `recurrence_unit`, `pi_parity_mode`.
- Sources:
  - `data/ogden8table35dr05.csv`, `data/ogden8table36dr05.csv`.

### Lifetime Split (LS) (`LifetimeSplitCalculation`)
- Primary path:
  - Split phases; annualise each; apply CM per phase; sum totals.
- Alternatives:
  - Capping phase end to LE on/off.
  - Inherited CM apportioning method selector:
    - `term_certain_end_minus_start`.
    - `discount_factor_to_start_x_term_certain_period`.
- Trigger:
  - `cap_end_to_life_expectancy`.
- Sources:
  - `data/ogden8table36dr05.csv` (through CM period-multiplier calculation).
  - `data/ogden8table35dr05.csv` (through CM when discount-factor apportionment method is selected).

## Care Head

### Care Annualisation (`CareCalculation`)
- Primary path:
  - Resolve period (age/date), annualise hours by increment rule, apply effective rate.
- Alternatives:
  - Age-based vs date-based periods.
  - Standard increment modes vs `Specify` modes.
  - Public holiday inclusion on/off for weekday logic.
- Trigger:
  - Period input mode, `time_increment`, `specify_increment`, `include_public_holidays`.
- Sources:
  - Calendar/day-count lookup (date mode).

### Care Claim Full (`CareClaimCalculation.calculate`)
- Primary path:
  - Care annualisation x Table 36 apportionment multiplier.
- Alternatives:
  - All care annualisation alternatives + custom term bounds.
  - Apportioning method selector:
    - `term_certain_end_minus_start` (Table 36 apportionment baseline).
    - `discount_factor_to_start_x_term_certain_period` (Table 35 discount-to-start x Table 36 period term, then life scaling).
  - Impaired override:
    - `life_expectancy_basis=impaired` + `impaired_multiplier_method=term_certain` uses direct term-certain period multiplier (no apportionment scaling).
- Trigger:
  - Care inputs, term/life inputs, `apportionment_method`, impaired method settings.
- Sources:
  - Table 36 (+ Table 35 when discount-factor apportionment method is selected).

### Care Split (`CareSplitCalculation` / `CareClaimCalculation.calculate_split`)
- Primary path:
  - Per-phase care annualisation + per-phase apportionment.
- Alternatives:
  - Strict contiguity required vs not required.
  - Apportioning method selector:
    - `term_certain_end_minus_start` (Table 36 apportionment baseline).
    - `discount_factor_to_start_x_term_certain_period` (Table 35 discount-to-start x Table 36 period term, then life scaling).
  - Impaired method routing:
    - `find_appropriate_age`: apportionment path.
    - `term_certain`: direct term-certain period per phase (no apportionment scaling).
- Trigger:
  - `require_contiguous`, LE basis/method settings.
- Sources:
  - Table 36 (+ Table 35 when discount-factor apportionment method is selected).

## Travel Head

### Travel Annual (`TravelCalculation.calculate_annual`)
- Primary path:
  - Annual journey count x per-journey cost.
- Alternatives:
  - Distance mode: `Each_Way` vs `Overall`.
  - `Over_Period` annualisation vs fixed frequency modes.
- Trigger:
  - `distance_input_type`, `time_increment`.
- Sources:
  - No Ogden table (annualisation only).

### Travel Claim Full (`TravelClaimCalculation`)
- Primary path:
  - Travel annual loss x Table 36 apportionment multiplier.
- Alternatives:
  - Distance input type: `Each_Way` vs `Overall`.
  - Time increment: `Over_Period`, `Per_Day`, `Per_Week`, `Per_Month`, `Per_Year`, `Per_Weekday`, `Per_Weekend`.
  - `Over_Period` annualisation uses supplied period length; other increments use fixed annual frequency factors.
  - Apportioning method selector:
    - `term_certain_end_minus_start` (Table 36 apportionment baseline).
    - `discount_factor_to_start_x_term_certain_period` (Table 35 discount-to-start x Table 36 period term, then life scaling).
  - Impaired method routing:
    - `find_appropriate_age`: apportionment path.
    - `term_certain`: direct term-certain period (no apportionment scaling).
- Trigger:
  - Travel inputs + term/life inputs + impaired method settings.
- Sources:
  - Table 36 (+ Table 35 when discount-factor apportionment method is selected).

## Equipment Head

### Equipment (`EquipmentCalculation`)
- Primary path:
  - Capital stream: sum Table 35 factors at purchase years.
  - Recurring stream: Table 36 apportionment x life multiplier.
- Alternatives:
  - Purchase boundary mode: default PI stream / `future_only` / `include_start`.
  - Purchase mortality mode: `no_mortality` vs `use_mortality`.
  - Replacement cycle unit: days/weeks/months/years.
- Trigger:
  - `purchase_boundary_mode`, `purchase_mortality_mode`, replacement settings.
- Sources:
  - `data/ogden8table35dr05.csv`, `data/ogden8table36dr05.csv`.

## Vehicle Head

### Vehicle (`VehicleCalculation`)
- Primary path:
  - Initial cost discounted by Table 35 at start.
  - Replacement stream discounted by Table 35 at schedule points.
  - Annual extras (insurance/running) via Table 36 apportionment x life multiplier.
- Alternatives:
  - Replacement stream start derived vs explicit `replacement_start_age`.
  - Purchase mortality mode `no_mortality` vs `use_mortality`.
  - LE anchor derivation helpers (standard/impaired) via Additional Tables in UI.
- Trigger:
  - Replacement start input, `purchase_mortality_mode`, LE basis settings.
- Sources:
  - `data/ogden8table35dr05.csv`, `data/ogden8table36dr05.csv`.
  - Additional tables: `data/ogden8_additional_*_0.csv`, `data/ogden8_additional_*_05.csv`.

## Earnings Head

### Earnings Core (`EarningsCalculation`)
- Primary path:
  - Annualise but-for/residual, convert gross-to-net (tax/NI where applicable), compute net annual loss, apply selected multiplier route, total loss.
- Alternatives (multiplier routes):
  - `multiplier_mode=auto/manual`:
    - Retirement-anchor path using Table 36 apportionment and retirement-table/anchor multiplier.
  - `multiplier_mode=additional`:
    - Period multiplier from Additional Tables delta between start/end ages.
- Alternatives (impaired anchor):
  - `impaired_multiplier_method=term_certain`.
  - `impaired_multiplier_method=find_appropriate_age`.
- Alternatives (life basis and splitting):
  - Standard vs impaired life handling.
  - Auto-split across retirement boundary when period crosses retirement.
  - Post-retirement residual can be included/excluded.
- Trigger:
  - `multiplier_mode`, `impaired_multiplier_method`, LE inputs, retirement crossing, `residual_after_retirement`.
- Sources:
  - Table 36 (`data/ogden8table36dr05.csv`).
  - Retirement tables (`data/tables_3-18/*.csv`).
  - Whole life (`data/ogden8table1dr05.csv` / `data/ogden8table2dr05.csv`).
  - Additional tables (`data/additional_*05.csv`, `data/ogden8_additional_*_0.csv`, `data/ogden8_additional_*_05.csv`).
  - Table 35 in deferred impaired branches (`data/ogden8table35dr05.csv`).

### Earnings ASHE (`EarningsAsheCalculation`)
- Primary path:
  - Resolve but-for/residual from ASHE workbook fields, then delegate to `EarningsCalculation`.
- Alternatives:
  - Explicit amount vs ASHE-derived amount for each stream.
- Trigger:
  - ASHE field/amount inputs.
- Sources:
  - ASHE workbook path(s), then same sources as Earnings Core.

### Earnings Split (`EarningsSplitCalculation`)
- Primary path:
  - Run `EarningsCalculation` per phase and aggregate.
- Alternatives:
  - Per phase: `multiplier_mode` (`auto`/`manual`/`additional`).
  - Per phase impaired path: `impaired_multiplier_method` (`term_certain`/`find_appropriate_age`).
  - Per phase retirement crossing behavior and residual-after-retirement handling.
- Trigger:
  - Phase definitions and per-phase settings.
- Sources:
  - Table 36: `data/ogden8table36dr05.csv`.
  - Retirement tables: `data/tables_3-18/*.csv`.
  - Whole life: `data/ogden8table1dr05.csv` / `data/ogden8table2dr05.csv`.
  - Additional tables: `data/additional_*05.csv`, `data/ogden8_additional_*_0.csv`, `data/ogden8_additional_*_05.csv`.
  - Table 35 in deferred impaired branches: `data/ogden8table35dr05.csv`.

### Earnings Award (`EarningsAwardCalculation`)
- Primary path:
  - One-off award passthrough (non-taxable treatment in trace).
- Alternatives:
  - None.
- Trigger:
  - Award amount only.
- Sources:
  - None.

## Lost Years Head

### Lost Years (`LostYearsCalculation`)
- Primary path:
  - Build normalization from but-for multiplier vs current-life multiplier, apply to period slices, sum lines.
- Alternatives:
  - But-for multiplier method: `term_certain` vs `find_appropriate_age`.
  - Values net vs gross (with conversion).
  - Optional pension lump-sum line and optional pension annual line.
- Trigger:
  - `but_for_multiplier_method`, net/gross flags, optional pension inputs.
- Sources:
  - Table 36, whole life, additional tables; optional Table 35 for pension lump sum.

## Pension Head

### Pension (`PensionCalculation`)
- Primary path:
  - Net annual loss x pension multiplier.
  - Pension multiplier = but-for life multiplier - mortality-to-retirement multiplier.
- Alternatives:
  - `life_expectancy_basis=Standard`:
    - but-for life multiplier from whole-life interpolation.
  - `life_expectancy_basis=Impaired` + `multiplier_method=term_certain`:
    - but-for life multiplier from Table 36 term-certain lookup.
  - `life_expectancy_basis=Impaired` + `multiplier_method=find_appropriate_age`:
    - but-for anchor from Additional Tables alignment (or whole-life fallback when relevant inputs absent).
- Trigger:
  - `life_expectancy_basis`, `multiplier_method`, additional-table availability.
- Sources:
  - Additional +0.5 table (mortality-to-retirement), optional Additional 0 for alignment, whole-life/Table 36.

### Pension Early Receipt (`PensionEarlyReceiptCalculation`)
- Primary path:
  - Lump-sum line (Longden + Table 35 discount) + annual line (delegated Pension calculation).
- Alternatives:
  - Annual line with `life_expectancy_basis=Standard`.
  - Annual line with `life_expectancy_basis=Impaired` + `multiplier_method=term_certain`.
  - Annual line with `life_expectancy_basis=Impaired` + `multiplier_method=find_appropriate_age`.
- Trigger:
  - Pension method settings and LE basis.
- Sources:
  - Additional +0.5 tables for mortality-to-retirement and Longden components.
  - Table 35 for deferment discount of expected lump sum.
  - Whole-life and/or Table 36 for annual-line pension method (per Pension route).
  - Optional Additional 0 table for impaired `find_appropriate_age` alignment.

## Accommodation Head

### Accommodation RvJ (`AccommodationRvJCalculation`)
- Primary path:
  - Ongoing annual component via Table 36 apportionment.
  - Adaptation component via Table 35 deferment.
- Alternatives:
  - Discount-rate source toggle (discount-rate column vs custom percent) in UI.
  - Standard vs impaired LE derivation in UI.
  - Apportioning method selector:
    - `term_certain_end_minus_start` (Table 36 apportionment baseline).
    - `discount_factor_to_start_x_term_certain_period` (Table 35 discount-to-start x Table 36 period term, then life scaling).
  - Impaired method routing for ongoing annual component:
    - `find_appropriate_age`: apportionment path.
    - `term_certain`: direct term-certain period (no apportionment scaling).
- Trigger:
  - Rate toggle, LE basis, impairment inputs, impaired method settings.
- Sources:
  - Table 36, Table 35, and (for LE derivation in UI) Additional tables.

### Accommodation Swift v Carpenter (`AccommodationSwiftCarpenterCalculation`)
- Primary path:
  - Reversionary-interest discount for life interest, then Table 35 early-receipt discount.
- Alternatives:
  - Standard vs impaired LE derivation in UI for period bounds.
- Trigger:
  - LE basis and impairment inputs.
- Sources:
  - Table 35; Additional tables used upstream in UI LE derivation.

## Comparison/Testing Implementations (Not Streamlit Production Paths)

### Loss of Earnings Interpolation Utility (`LossOfEarningsInterpolation`)
- Implemented methods:
  - Manual retirement-age interpolation comparator (`compare`).
  - Term-certain vs Additional period comparator (`compare_period_methods`).
  - Ogden-book shifted-age method (`compare_book_manual_vs_additional`, `X+A-R` / `X+B-R`).
- Exposure:
  - CLI commands: `loe-interp-compare`, `loe-period-compare`, `loe-book-compare`.
- Status:
  - Testing/comparison only; not wired as a Streamlit production function.
