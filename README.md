# Scheduel Calculator (Standalone)

Standalone CLI calculators implemented with the same structure as `excel2python`:

- Formula classes in `formulas/`
- CLI wiring in `main.py`
- Verbose trace output for intermediate calculation steps

## Implemented Functions

- `cm-calc`: Continuous Multiplier (CM) with pi-style start/end options (Age at Calculation / Rest of Life)
- `gc-calc`: General Continuous (GC) annualised loss * CM period multiplier
- `gcbf-calc`: General Continuous (But For) net annual differential * CM period multiplier
- `gof-calc`: General One Off (GOF) discounted one-off loss using Table 35
- `gp-calc`: General Periodical (GP) recurring discounted purchases using Table 35
- `ls-calc`: Lifetime (Split) piecewise annualised losses with CM apportionment per segment
- `pm-calc`: Periodical Multiplier (PM) recurring multiplier calculation using GP engine
- `care-calc`: Care annualisation (age mode or date mode) with PI-style trace
- `care-calc-split`: Multi-period split care annualisation with non-overlap validation
- `care-claim-calc`: Full care claim flow (annualisation + Table 36 apportionment + total award)
- `care-claim-split-calc`: PI-style split claim in one run (multiple rows -> one combined total)
- `equipment-calc`: Equipment capital replacement + annual insurance/maintenance (optional PI test modes)
- `travel-calc`: Travel annual loss calculation
- `travel-claim-calc`: Full travel claim calculation (annual + multiplier apportionment)
- `vehicle-calc`: Vehicle initial cost + replacement stream + annual insurance/running extras
- `loe-interp-compare`: Manual retirement-age interpolation vs Additional Tables comparison
- `loe-period-compare`: Term-certain period vs Additional Tables period comparison
- `loe-book-compare`: Ogden para 33/34 manual interpolation vs Additional Tables
- `earnings-calc`: Earnings loss calculation (tax-aware, multiplier-based; supports `auto/manual/additional`)
- `earnings-ashe-calc`: Earnings loss calculation with ASHE workbook lookup support
- `earnings-split-calc`: Multi-period earnings loss calculation
- `earnings-award-calc`: One-off non-taxable earnings award

## Project layout

```
Scheduel-Calculator/
  formulas/
    __init__.py
    care_calculation.py
    care_multiplier_calculation.py
    care_claim_calculation.py
    care_whole_life_calculation.py
  main.py
  README.md
  formulas.md
```

## Requirements

- Python 3.10+
- `openpyxl` (for ASHE `.xlsx` table lookups)

## Run CLI

Show help:

```bash
python main.py --help
```

Show command help:

```bash
python main.py care-calc --help
```

```bash
python main.py cm-calc --help
```

```bash
python main.py gc-calc --help
```

```bash
python main.py gcbf-calc --help
```

```bash
python main.py gof-calc --help
```

```bash
python main.py gp-calc --help
```

```bash
python main.py ls-calc --help
```

```bash
python main.py pm-calc --help
```

```bash
python main.py care-calc-split --help
```

```bash
python main.py care-claim-calc --help
```

```bash
python main.py care-claim-split-calc --help
```

```bash
python main.py equipment-calc --help
```

```bash
python main.py travel-calc --help
```

```bash
python main.py travel-claim-calc --help
```

```bash
python main.py vehicle-calc --help
```

```bash
python main.py loe-interp-compare --help
```

```bash
python main.py loe-period-compare --help
```

```bash
python main.py loe-book-compare --help
```

```bash
python main.py earnings-calc --help
```

```bash
python main.py earnings-ashe-calc --help
```

```bash
python main.py earnings-split-calc --help
```

```bash
python main.py earnings-award-calc --help
```

## Implemented command

### `cm-calc`

Continuous Multiplier (CM) using Table 36 apportionment:

```bash
python main.py cm-calc \
  --calculation-age 65.68 \
  --life-expectancy-age 85.35 \
  --start-at-calculation-age \
  --end-at-rest-of-life \
  --life-multiplier 18.56 \
  --table36-csv data/ogden8table36dr05.csv
```

Specific start/end ages:

```bash
python main.py cm-calc \
  --calculation-age 65.68 \
  --life-expectancy-age 85.35 \
  --no-start-at-calculation-age --start-age 66 \
  --no-end-at-rest-of-life --end-age 80 \
  --life-multiplier 18.56 \
  --table36-csv data/ogden8table36dr05.csv
```

### `care-calc`

### `gc-calc`

General Continuous (GC): annualise loss by frequency then apply CM multiplier.

```bash
python main.py gc-calc \
  --loss-amount 1000 \
  --loss-frequency Per_Year \
  --calculation-age 65.68 \
  --life-expectancy-age 85.35 \
  --start-at-calculation-age \
  --end-at-rest-of-life \
  --life-multiplier 18.56 \
  --table36-csv data/ogden8table36dr05.csv
```

Care annualisation based on `CareCalculation.md` with:
- age-based period (`--age-at-start`, `--age-at-end`) OR
- date-based period (`--start-date`, `--end-date`, ISO `YYYY-MM-DD`)

Outputs:
- `Period Years`
- `Annualised Hours`
- `Effective Rate`
- `Annualised Cost`
- `Calculation Trace` (step-by-step debug lines)

#### Example 1: Standard weekly hours

```bash
python main.py care-calc \
  --age-at-start 67 \
  --age-at-end 80 \
  --number-of-hours 10 \
  --time-increment Per_Week \
  --care-rate-type Basic_Rate \
  --rate Basic_Rate=25
```

#### Example 2: Specify rate with percentage less

```bash
python main.py care-calc \
  --age-at-start 50 \
  --age-at-end 65 \
  --number-of-hours 8 \
  --time-increment Per_Week \
  --care-rate-type Specify_Rate \
  --manual-rate 30 \
  --percentage-less 25
```

#### Example 3: Day-specify path

```bash
python main.py care-calc --age-at-start 40 --age-at-end 45 --number-of-hours 2 --time-increment Per_Day_Specify --specify-increment Per_Week_Specify --number-days-specify 3 --care-rate-type Aggregate_Rate --rate Aggregate_Rate=20
```

#### Example 4: Date mode

```bash
python main.py care-calc --start-date 2026-03-13 --end-date 2039-03-13 --number-of-hours 20 --time-increment Per_Week --care-rate-type Basic_Rate --rate Basic_Rate=12.69
```

#### Example 5: Weekday excluding public holidays

```bash
python main.py care-calc --age-at-start 67 --age-at-end 80 --number-of-hours 20 --time-increment Per_Weekday --care-rate-type Basic_Rate --rate Basic_Rate=12.69 --no-include-public-holidays --public-holidays-per-year 8
```

### `care-calc-split`

Split-period annualisation with contiguous/non-overlap checks.

```bash
python main.py care-calc-split --period-file data/sample_periods.json
```

## Validation behavior

- Invalid/unsupported combinations throw clear `ValueError` messages.
- No silent fallback behavior is used.

## Full claim example

PI-style cross-check example with auto life-multiplier lookup from Ogden whole-life CSVs and auto-derived term years:

```bash
python main.py care-claim-calc --age-at-start 67 --age-at-end 80 --number-of-hours 1 --time-increment Per_Year --care-rate-type Specify_Rate --manual-rate 1 --life-expectancy-years 19.67 --claimant-age 65.68 --gender male --table36-csv data/ogden8table36dr05.csv
```

Optional debug override (inline values):

```bash
python main.py care-claim-calc --age-at-start 67 --age-at-end 80 --number-of-hours 1 --time-increment Per_Year --care-rate-type Specify_Rate --manual-rate 1 --term-start-years 1.32 --term-end-years 14.32 --life-expectancy-years 19.67 --life-multiplier 18.56 --table36-values "1,1.99,2.98,3.96,4.94,5.91,6.88,7.84,8.8,9.75,10.7,11.65,12.59,13.52,14.45,15.38,16.3,17.22,18.13,19.03,19.94"
```

## PI-style split claim example

One command, all split rows together:

```bash
python main.py care-claim-split-calc --period-file data/sample_periods.json --claimant-age 65.68 --gender male --life-expectancy-years 19.67 --table36-csv data/ogden8table36dr05.csv
```

`sample_periods.json` rows can use either explicit `age_at_start`/`age_at_end` or `period_until_age` (contiguous rows auto-chain from prior row/start age).

## Equipment example

```bash
python main.py equipment-calc --claimant-age 42.76 --gender male --age-at-start 50 --age-at-end 80 --cost-of-equipment 5000 --replacement-every-value 3 --replacement-every-unit Years --annual-insurance 400 --annual-maintenance 200 --table35-csv data/ogden8table35dr05.csv --table36-csv data/ogden8table36dr05.csv
```

PI test-mode options (Scenario A/B):

```bash
python main.py equipment-calc --claimant-age 46.19 --gender male --age-at-start 46.19 --age-at-end 60 --cost-of-equipment 1000 --replacement-every-value 3 --replacement-every-unit Years --annual-insurance 400 --annual-maintenance 200 --recurring-life-basis full_life --life-expectancy-end-age 84.69 --purchase-boundary-mode include_start --purchase-mortality-mode no_mortality --table35-csv data/ogden8table35dr05.csv --table36-csv data/ogden8table36dr05.csv
```

## Travel examples

Annual-only:

```bash
python main.py travel-calc --distance 10 --distance-input-type Each_Way --mileage-rate 0.45 --parking-cost 5 --journey-count 3 --time-increment Per_Week
```

Full claim:

```bash
python main.py travel-claim-calc --claimant-age 42.76 --gender male --age-at-start 50 --age-at-end 80 --distance 10 --distance-input-type Each_Way --mileage-rate 0.45 --parking-cost 5 --journey-count 3 --time-increment Per_Week --table36-csv data/ogden8table36dr05.csv
```

## Vehicle example

```bash
python main.py vehicle-calc --claimant-age 42.76 --gender male --age-at-start 50 --age-at-end 84.69 --life-expectancy-end-age 84.69 --required-vehicle-cost 30000 --existing-vehicle-credit 5000 --trade-in-value 3000 --replacement-every-value 7 --replacement-every-unit Years --replacement-start-age 57 --increased-insurance 1000 --increased-running-costs 750 --table35-csv data/ogden8table35dr05.csv --table36-csv data/ogden8table36dr05.csv
```

## Loss of earnings interpolation comparison example

```bash
python main.py loe-interp-compare --retirement-age-actual 67 --retirement-age-lower 65 --retirement-age-upper 68 --multiplier-lower 12.34 --multiplier-upper 11.80 --additional-tables-multiplier 12.05
```

E3-style period comparison:

```bash
python main.py loe-period-compare --age-at-trial 42.76 --start-years-from-trial 7.24 --end-years-from-trial 17.24 --start-age 50 --end-age 60 --table36-csv data/ogden8table36dr05.csv --additional-tables-csv data/additional_male05.csv --contingency-factor 0.87
```

Book para 33/34 comparison:

```bash
python main.py loe-book-compare --claimant-age 42.76 --retirement-age-actual 68 --retirement-age-lower 65 --retirement-age-upper 70 --lower-table-csv data/tables_3-18/table_9_male_ra65.csv --upper-table-csv data/tables_3-18/table_13_male_ra70.csv --additional-tables-csv data/additional_male05.csv --discount-rate 0.5
```

## Notes

- `care-calc` supports both age and date inputs, but you must provide one mode only.
- Trace logging is intentionally verbose to mirror PI-style transparency.
- Table 36 interpolation supports `0` years (start at calculation age), matching PI split-row behavior for first phase.
- Equipment uses Table 35 for purchase-factor summation and Table 36 apportionment for recurring costs.
- Detailed equipment implementation notes are in `docs/equipment.md`.
- Vehicle uses Table 35 discount factors for initial/replacement purchases and Table 36 apportionment for annual extras.
- Detailed earnings implementation notes are in `docs/earnings.md`.
- Vehicle replacement stream end uses `min(age_at_end, life_expectancy_end_age)`.
- Vehicle supports optional `--replacement-start-age` override (default remains start + one cycle).
- Earnings multiplier mode:
  - `auto`: currently defaults to `manual` path.
  - `manual`: existing term-certain/whole-life path.
  - `additional`: Additional Tables period multiplier (`Additional(end_age) - Additional(start_age)`), requires `--additional-tables-csv`.
 - `earnings-ashe-calc` can source but-for/residual amounts either from explicit values (`--but-for-amount`, `--residual-amount`) or ASHE fields (`--but-for-ashe-field`, `--residual-ashe-field`) using `median`, `mean`, or `pXX`.
