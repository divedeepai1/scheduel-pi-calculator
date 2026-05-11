# Multiplier Methods

Short map of multiplier methods used in this codebase, which functions use them, and why.

## Method Selection Rules
- If life expectancy basis is `standard`:
  - Use standard-life anchor routes (whole-life or additional-table derived, depending on function flow).
- If life expectancy basis is `impaired` with `term_certain`:
  - Use term-certain Table 36 style pathing for the impaired life horizon.
- If life expectancy basis is `impaired` with `find_appropriate_age`:
  - Use Additional Tables alignment/anchor lookup (or retirement-table fallback where implemented) to pick the multiplier anchor.
- If purchase mortality mode is `use_mortality` (Equipment/Vehicle):
  - Apply per-purchase survival adjustment to each Table 35 purchase factor before summation.
- If purchase mortality mode is `no_mortality`:
  - Use raw Table 35 purchase factors without survival adjustment.

## 1) Table 36 Term-Certain Interpolation (Apportionment)
- Used by:
  - Continuous Multiplier (CM)
  - General Continuous (GC)
  - General Continuous (But For)
  - Lifetime (Split)
  - Care Claim (Full), Care (Split)
  - Travel Claim (Full)
  - Equipment (recurring line)
  - Vehicle (annual extras line)
  - Accommodation (RvJ ongoing line)
  - Earnings / Earnings Split / Earnings (ASHE) (manual/auto branches)
  - Lost Years
  - Pension (term_certain lookup path)
- Purpose:
  - Convert a start-end period into a mortality-adjusted period multiplier by scaling a Table 36 slice to a life multiplier anchor.

## 2) Table 35 Discount/Deferment Interpolation
- Used by:
  - General One Off (GOF)
  - General Periodical (GP) / Periodical Multiplier (PM)
  - Equipment (capital purchase stream)
  - Vehicle (initial/replacement capital stream)
  - Earnings (deferred impaired branches)
  - Lost Years (pension lump-sum line)
  - Pension (Early receipt) (lump-sum discount)
  - Accommodation (RvJ adaptation line)
  - Accommodation (Swift v Carpenter) (early receipt discount)
- Purpose:
  - Discount future one-off/capital payments to present value based on deferment timing.

## 3) Table 35 Scheduled-Sum Multiplier (Periodical Capital Stream)
- Used by:
  - General Periodical (GP)
  - Periodical Multiplier (PM)
  - Equipment (replacement stream)
  - Vehicle (replacement stream)
- Purpose:
  - Build a multiplier by summing Table 35 factors at each scheduled purchase/replacement point.

## 4) Whole-Life Age Interpolation (Ogden Table 1/2)
- Used by:
  - CM flows (when deriving life multiplier from whole-life)
  - Earnings / Pension / Pension Early Receipt (anchor values)
  - Lost Years (anchor path)
- Purpose:
  - Get age-based life multiplier anchors from whole-life tables.

## 5) Retirement-Table Age Interpolation (Ogden Tables 3-18)
- Used by:
  - Earnings / Earnings Split / Earnings (ASHE)
- Purpose:
  - Obtain retirement-basis multiplier anchors for earnings apportionment.

## 6) Additional Tables (+0% / +0.5%) Interpolation and Alignment
- Used by:
  - Earnings / Earnings Split / Earnings (ASHE)
  - Pension
  - Pension (Early receipt)
  - Lost Years
  - Vehicle and CM UI flows (standard/impaired life derivation)
- Purpose:
  - Alternative anchor selection and mortality-to-retirement lookups.
  - Supports impaired methods like `find_appropriate_age` and standard-life derivations.

## 7) Longden Factor Method
- Used by:
  - Pension (Early receipt)
- Purpose:
  - Adjust expected/actual lump-sum pension values for early receipt timing.

## 8) Reversionary Interest Discount
- Used by:
  - Accommodation (Swift v Carpenter)
- Purpose:
  - Compute life-interest loss from net capital over the occupancy period at a reversionary rate.

## 9) Book Retirement-Age Interpolation (Testing/Comparison Only)
- Used by:
  - `LossOfEarningsInterpolation.compare_book_manual_vs_additional`
  - CLI: `loe-book-compare` (and related comparison commands)
- Purpose:
  - Implements the Ogden-book style interpolation between two retirement-age tables using shifted ages:
    - `X + A - R` in lower retirement table
    - `X + B - R` in upper retirement table
    - Weighted interpolation between the two multipliers.
- Status:
  - Comparison/testing utility only; not used in Streamlit production calculation flows.
