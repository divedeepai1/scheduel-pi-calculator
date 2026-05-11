# Equipment Calculation (`EquipmentCalculation`)

## Purpose

Implements PI-oriented Equipment loss calculation with two components:

- Capital purchases of equipment on a replacement cycle.
- Recurring annual costs (insurance and maintenance).

This mirrors the PI-style structure where annual equipment cost is displayed directly and multiplier complexity is concentrated in replacement valuation.

## File and entry points

- Formula class: `formulas/equipment_calculation.py`
- CLI command: `python main.py equipment-calc ...`
- Streamlit tab: `Equipment` in `app.py`

## Inputs

- `age_at_start` (float)
- `age_at_end` (float, must be greater than `age_at_start`)
- `cost_of_equipment` (float, >= 0)
- `replacement_every_value` (float, > 0)
- `replacement_every_unit` (`Days`, `Weeks`, `Months`, `Years`)
- `claimant_age` (float)
- `life_expectancy_years` (float)
- `life_multiplier` (float)
- `annual_insurance` (float, default `0.0`)
- `annual_maintenance` (float, default `0.0`)
- `table35_vector` (List[float], from Ogden Table 35 at 0.5%)
- `table36_vector` (List[float], from Ogden Table 36 at 0.5%)

## Calculation model

### 1) Period and annual display value

- `period_years = age_at_end - age_at_start`
- `annual_equipment_cost_display = cost_of_equipment`

The displayed annual equipment figure is always the raw equipment cost, regardless of replacement frequency.

### 2) Replacement frequency normalization

`replacement_every_value` + `replacement_every_unit` is normalized to years:

- Days: `value / 365`
- Weeks: `value / (365/7)`
- Months: `value / 12`
- Years: `value`

Then:

- `purchase_count = ceil(period_years / replacement_every_years)`

### 3) Equipment purchase multiplier (Table 35)

- Derive `start_years = age_at_start - claimant_age`
- Derive `end_years = age_at_end - claimant_age`
- Build purchase years at replacement intervals from the first interval after `start_years` up to `end_years` (inclusive boundary)
- Interpolate Table 35 at each purchase year and sum factors

This sum is the equipment multiplier:

- `equipment_multiplier = sum(Table35(purchase_year_i))`

### 4) Recurring multiplier (Table 36 apportionment)

Recurring annual costs (insurance/maintenance) use care-style apportionment:

- `term_start = Table36(start_years)`
- `term_end = Table36(end_years)`
- `term_life = Table36(life_expectancy_years)`
- `recurring_multiplier = ((term_end - term_start) / term_life) * life_multiplier`

Then:

- `capital_total = annual_equipment_cost_display * equipment_multiplier`

### 5) Recurring costs and multiplier

- `annual_recurring_cost = annual_insurance + annual_maintenance`
- `insurance_total = annual_insurance * recurring_multiplier`
- `maintenance_total = annual_maintenance * recurring_multiplier`

Then:

- `recurring_total = annual_recurring_cost * recurring_multiplier`

### 6) Final result

- `total_loss = capital_total + recurring_total`

## Outputs

- `period_years`
- `annual_equipment_cost_display`
- `purchase_count`
- `capital_total`
- `equipment_multiplier`
- `annual_recurring_cost`
- `recurring_multiplier`
- `insurance_total`
- `maintenance_total`
- `recurring_total`
- `total_loss`
- `trace` (verbose debug steps)

## Assumptions in this implementation

- PI-focused multiplier-driven method (no legacy/fallback branch retained).
- Purchase count is used as a density factor (`purchase_count / period_years`) inside equipment multiplier.
- Calculations retain full precision internally; formatting/rounding is for display only.

These are explicit and configurable via CLI flags.
