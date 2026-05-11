# Vehicle Calculation (PI-Oriented)

## Purpose

This module implements PI-style vehicle future loss calculations with three components:

- Initial vehicle need (net of existing vehicle credit)
- Future replacement stream (net of trade-in value)
- Annual recurring extras (increased insurance and running costs)

## Inputs

- Loss age window:
  - `age_at_start`
  - `age_at_end`
- Claimant context:
  - `claimant_age`
  - `gender` (only needed when auto-deriving whole-life multiplier)
  - `life_expectancy_end_age` (optional override; used as an upper cap for replacement stream end)
  - `life_expectancy_years`
  - `life_multiplier`
- Vehicle values:
  - `required_vehicle_cost`
  - `existing_vehicle_credit`
  - `trade_in_value`
  - `replacement_every_value`
  - `replacement_every_unit` (`Days`, `Weeks`, `Months`, `Years`)
  - `replacement_start_age` (optional override; default is one cycle after start)
  - `increased_insurance`
  - `increased_running_costs`
- Ogden vectors:
  - Table 35 CSV (discount factors for purchase timing)
  - Table 36 CSV (term-certain multipliers for apportionment)

## Core Formulas

1. Initial net cost:

`initial_net_cost = required_vehicle_cost - existing_vehicle_credit`

2. Replacement net cost:

`replacement_net_cost = required_vehicle_cost - trade_in_value`

3. Effective end age and offsets:

`effective_end_age = min(age_at_end, life_expectancy_end_age)`

`start_years = age_at_start - claimant_age`

`end_years = effective_end_age - claimant_age`

When `life_expectancy_end_age` is not supplied, the implementation derives
`life_expectancy_years` from a Table 36 inverse lookup using `life_multiplier`,
then computes `life_expectancy_end_age = claimant_age + life_expectancy_years`.

4. Initial discounted purchase:

`initial_total = initial_net_cost * Table35(start_years)`

5. Replacement stream:

- By default, first replacement is after one full cycle from the loss start.
- Optional override: if `replacement_start_age` is provided, stream starts there.
- Build replacement times:
  - `first_replacement_years`
  - `first_replacement_years + cycle_years`
  - ...
  - include values `<= end_years`
- Replacement multiplier:
  - `replacements_multiplier = sum(Table35(t_i))`
- Replacement total:
  - `replacements_total = replacement_net_cost * replacements_multiplier`

6. Annual recurring apportionment (PI-style):

`annual_multiplier = ((Table36(end_years) - Table36(start_years)) / Table36(life_expectancy_years)) * life_multiplier`

7. Recurring totals:

`insurance_total = increased_insurance * annual_multiplier`

`running_total = increased_running_costs * annual_multiplier`

8. Final total:

`total_loss = initial_total + replacements_total + insurance_total + running_total`

## Interpolation Rules

Both Table 35 and Table 36 use linear interpolation.

- For exact integer year `n`, use row `n`.
- For fractional year `y` between `n` and `n+1`:
  - `((n+1 - y) * value_n) + ((y - n) * value_(n+1))`

Special handling:

- Table 35 at year `0` returns `1.0`.
- Table 36 at year `0` returns `0.0`.

## CLI

Command:

`python main.py vehicle-calc --help`

Example:

`python main.py vehicle-calc --claimant-age 42.76 --gender male --age-at-start 50 --age-at-end 84.69 --required-vehicle-cost 30000 --existing-vehicle-credit 5000 --trade-in-value 3000 --replacement-every-value 7 --replacement-every-unit Years --increased-insurance 1000 --increased-running-costs 750 --table35-csv data/ogden8table35dr05.csv --table36-csv data/ogden8table36dr05.csv`

## Streamlit

Use the sidebar function selector and pick `Vehicle`.

The page displays:

- Initial Cost
- Future Replacements
- Insurance Costs
- Running Costs
- Total
- Full debug trace
