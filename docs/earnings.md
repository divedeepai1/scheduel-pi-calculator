# Earnings Calculations

## Purpose

Implements PI-style earnings valuation across three related flows:

- `EarningsCalculation` for a single period (`earnings-calc`)
- `EarningsSplitCalculation` for multi-period claims (`earnings-split-calc`)
- `EarningsAsheCalculation` for ASHE-driven amount selection (`earnings-ashe-calc`)

The implementation combines:

- annual gross-to-net conversion (tax/NI path),
- period multiplier derivation (manual/additional/impaired branches),
- contingency adjustment,
- total valuation (`net annual loss * final multiplier`).

## Files and entry points

- Formula classes:
  - `formulas/earnings_calculation.py`
  - `formulas/earnings_split_calculation.py`
  - `formulas/earnings_ashe_calculation.py`
  - `formulas/ashe_loader.py`
- CLI wiring:
  - `main.py` (`earnings-calc`, `earnings-split-calc`, `earnings-ashe-calc`, `earnings-award-calc`)
- UI:
  - `app.py` (Earnings/Earnings Split sections)

## Core data sources and tables

- `data/ogden8table36dr05.csv`
  - Term-certain interpolation vector used for period apportionment.
- `data/tables_3-18/table_*.csv`
  - Retirement tables with discount-rate columns (used for retirement anchor interpolation).
- `data/ogden8table35dr05.csv`
  - Deferred factor interpolation (used in impaired-life branch with deferral).
- Additional tables:
  - legacy: `data/additional_male05.csv`, `data/additional_female05.csv`
  - exported full matrices:
    - `data/ogden8_additional_males_0.csv`
    - `data/ogden8_additional_females_0.csv`
    - `data/ogden8_additional_males_05.csv`
    - `data/ogden8_additional_females_05.csv`
- ASHE workbook(s): `.xlsx` sheets (All, Male, Female, etc.) loaded by `openpyxl`.

## High-level calculation flow (single period)

`EarningsCalculation.calculate(...)` runs in this order:

1. Validate inputs and normalize frequencies.
2. Convert but-for/residual amounts to annual gross values.
3. Convert annual gross to annual net (unless input marked net).
4. Compute `net_annual_loss = but_for_net - residual_net`.
5. Compute `period_multiplier` using selected branch.
6. Apply contingency: `final_multiplier = period_multiplier * contingency_factor`.
7. Compute `total_loss = net_annual_loss * final_multiplier`.
8. Return values + verbose `trace`.

## Frequency normalization

Supported earnings frequencies:

- `Per_Year` -> `* 1.0`
- `Per_Month` -> `* 12.0`
- `Per_Week` -> `* (365 / 7)`

## Tax and NI model currently implemented

Region supported in code path: `England_Wales_NI` (Scotland is rejected).

### Income tax

- Personal allowance base: `12570`
- Taper after `100000` income
- Bands:
  - 20% basic
  - 40% higher
  - 45% additional

### NI (employed)

- Primary threshold basis in code: `12584`
- Main rate to UEL (`50270`): 8%
- Above UEL: 2%

### NI (self-employed)

- Class 2 fixed component: `182` (when NI applies and gross > 0)
- Class 4:
  - 6% between `12570` and `50270`
  - 2% above `50270`

### Retirement NI shutoff behavior

- NI application is toggled by period start vs inferred retirement age:
  - `apply_ni = age_at_start < retirement_age`

### Rounding

- Tax rounded to 2 dp.
- NI rounded to 2 dp.
- Net annual rounded to 2 dp.
- Multiplier math is otherwise high precision; formatting/outputs are printed to 8 dp.

## Multiplier framework

`multiplier_mode` options:

- `auto` (currently resolves to `manual`)
- `manual`
- `additional`

### Additional mode

Uses Additional Tables period difference:

- `period_multiplier = Additional(end_age) - Additional(start_age)`

Additional table lookup is 2D interpolation over:

- row axis: age at trial
- column axis: target end age

Interpolation method:

- bracketing on both axes,
- bilinear interpolation,
- nearest non-empty fallback cell where needed.

### Manual mode (base branch)

For pre-retirement periods:

- `term_full_to_retirement = Table36(retirement_age - claimant_age)`
- `term_slice = Table36(end_from_trial) - Table36(start_from_trial)`
- `period_multiplier = (term_slice / term_full_to_retirement) * retirement_anchor`

For post-retirement periods:

- uses PI-style slice beyond retirement on Table 36:
- `period_multiplier = ((Table36(end_from_trial) - Table36(retirement_from_trial)) / term_full_to_retirement) * retirement_anchor`

## Impaired-life multiplier methodology

Additional inputs supported:

- `impairment_end_age`
- `impaired_multiplier_method`:
  - `find_appropriate_age`
  - `term_certain`
- `additional_tables_zero_csv`
- `additional_tables_point5_csv`
- `table35_csv`

### Branch rule in implementation

1. If `impairment_end_age` is not provided:
   - fallback to retirement-table anchor interpolation (`_retirement_interp(claimant_age)`).

2. If `impairment_end_age > retirement_age`:
   - retirement anchor is pulled from Additional +0.5% table directly at claimant age to retirement age.

3. If `impairment_end_age <= retirement_age`:
   - use selected impaired method and apply deferral factor where needed.

### Deferral handling

- `deferred_years = max(0, age_at_start - claimant_age)`
- `deferred_factor = Table35(deferred_years)` (interpolated)

### `term_certain` impaired method

- `anchor_years = impairment_end_age - age_at_start`
- anchor multiplier before apportionment:
  - `retirement_anchor = Table36(anchor_years) * deferred_factor`

### `find_appropriate_age` impaired method

Implemented inverse-style solve on Additional 0% grid:

1. Compute remaining life at start:
   - `remaining_life = impairment_end_age - age_at_start`
2. Solve effective age `x` such that:
   - `Additional0%(x, impairment_end_age) ~= remaining_life`
   - solved via binary search.
3. Use solved age to get +0.5% anchor:
   - `anchor = Additional+0.5%(x, retirement_age)`
4. Apply deferral:
   - `retirement_anchor = anchor * deferred_factor`

Then normal manual apportionment uses this anchor.

## Table interpolation details

### Table 36 interpolation

- For `years <= 0`: 0
- For `0 < years < 1`: linear from 0 to year-1 entry
- For `years >= 1`: linear interpolation between integer year points.

### Table 35 interpolation

- For `years <= 0`: 1
- For fractional first year: linear between 1 and first table value
- Otherwise linear between neighboring integer year entries.

### Age-table interpolation (retirement/whole-life)

- Piecewise linear by age row pairs.
- Boundary clamp at first/last row values.

### Additional table interpolation

- Axes parsed from header and first column.
- Bilinear interpolation with bracketing.
- Nearest non-empty fallback search for sparse cells.

## Split earnings flow

`EarningsSplitCalculation.calculate_split(...)`:

- sorts periods by `age_at_start`,
- validates non-overlap and optional contiguity,
- runs `EarningsCalculation.calculate(...)` per phase,
- sums `total_loss`,
- returns phase list (`net_annual_loss`, `final_multiplier`, `total_loss`) + trace.

This means split periods inherit all multiplier/tax options from single-period calculation.

## ASHE flow

`EarningsAsheCalculation` uses `ashe_loader`:

- Reads selected workbook sheet based on dataset key.
- Finds row by SOC code (optional region prefix filter).
- Parses `median`, `mean`, and percentile columns.
- Supports amount resolution for but-for/residual as:
  - explicit amount, or
  - ASHE field (`median`, `mean`, `pXX`).
- Then delegates to `EarningsCalculation`.

## CLI options (current key switches)

### `earnings-calc`

- Core earnings:
  - ages, but-for/residual amounts, frequencies, net/gross flags, employment type, region
- Multiplier:
  - `--multiplier-mode {auto,manual,additional}`
  - `--additional-tables-csv`
- Impaired branch:
  - `--impairment-end-age`
  - `--impaired-multiplier-method {find_appropriate_age,term_certain}`
  - `--additional-tables-zero-csv`
  - `--additional-tables-point5-csv`
  - `--table35-csv`
- Table files:
  - `--table36-csv`
  - `--retirement-table-csv`
  - `--whole-life-csv`

### `earnings-split-calc`

Same multiplier/impaired switches as above plus:

- `--period-file` or repeated `--period-json`
- `--require-contiguous`

### `earnings-ashe-calc`

- ASHE workbook + dataset + SOC code
- optional region filter
- amount selection by explicit value or ASHE field
- standard multiplier/table switches

## Current behavior notes

- Multiplier parity has been improved significantly for PI-style examples, especially post-retirement slices.
- Remaining output differences are typically tied to tax/NI edge-case parity and rounding checkpoints across scenarios.
- `Scotland` path is intentionally not implemented yet in the tax engine.

## Related files

- `docs/equipment.md`
- `docs/travel.md`
- `docs/vehicle.md`
- `implementation/earnings.txt`
- `implementation/earnings-examples.txt`
- `implementation/earnings-multipliers.txt`
