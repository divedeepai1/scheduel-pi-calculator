# Scheduel Calculator (Standalone)

Standalone CLI calculators implemented with the same structure as `excel2python`:

- Formula classes in `formulas/`
- CLI wiring in `main.py`
- Verbose trace output for intermediate calculation steps

## Implemented Functions

- `care-calc`: Care annualisation (age mode or date mode) with PI-style trace
- `care-calc-split`: Multi-period split care annualisation with non-overlap validation
- `care-claim-calc`: Full care claim flow (annualisation + Table 36 apportionment + total award)

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

No external dependencies are required for current functions.

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
python main.py care-calc-split --help
```

```bash
python main.py care-claim-calc --help
```

## Implemented command

### `care-calc`

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

## Notes

- `care-calc` supports both age and date inputs, but you must provide one mode only.
- Trace logging is intentionally verbose to mirror PI-style transparency.
