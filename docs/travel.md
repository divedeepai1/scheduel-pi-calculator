# Travel Calculation (`TravelCalculation`, `TravelClaimCalculation`)

## Purpose

Implements PI-style Travel loss flow:

- Annual travel loss from journey economics and recurrence.
- Total claim by applying apportionment multiplier to annual travel loss.

## Components

- `formulas/travel_calculation.py` -> annual travel loss.
- `formulas/travel_claim_calculation.py` -> annual loss + multiplier + total.

## Annual travel logic

Inputs:

- `distance`
- `distance_input_type` (`Each_Way` or `Overall`)
- `mileage_rate`
- `parking_cost`
- `journey_count`
- `time_increment`

Calculation:

1. `effective_distance = distance * 2` when `Each_Way`, else `distance`.
2. `journey_cost = (effective_distance * mileage_rate) + parking_cost`.
3. `annual_journey_count`:
   - for `Over_Period`: `journey_count / period_years`
   - otherwise: `journey_count * frequency_per_year(time_increment)`
4. `annual_loss = annual_journey_count * journey_cost`.

## Multiplier logic (claim mode)

Travel claim uses the same apportionment structure as care multipliers:

- `start_years = age_at_start - claimant_age`
- `end_years = age_at_end - claimant_age`
- `period_multiplier = ((M_end - M_start) / M_life) * life_multiplier`
  where `M_*` are Table 36 term-certain interpolations.

Then:

- `total_loss = annual_loss * period_multiplier`

## Outputs

- `AnnualLoss`
- `PeriodMultiplier`
- `TotalLoss`
- `Trace` (intermediate debug lines)

## Commands

- Annual-only: `python main.py travel-calc ...`
- Full claim: `python main.py travel-claim-calc ...`
