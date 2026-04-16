## Implemented Functions Index

- `Care Calculation (Age-Based v1)` -> class `CareCalculation` -> CLI `care-calc`
- `Care Split Calculation` -> class `CareSplitCalculation` -> CLI `care-calc-split`
- `Care Multiplier Calculation (Table 36 + Apportionment)` -> class `CareMultiplierCalculation`
- `Care Whole-Life Calculation` -> class `CareWholeLifeCalculation`
- `Care Claim Calculation (Orchestrator)` -> class `CareClaimCalculation` -> CLI `care-claim-calc`

---

## Care Calculation

```
Function CalculateCareAnnualisedCost
Inputs:
  AgeAtStart (Float, optional if using dates)
  AgeAtEnd (Float, optional if using dates)
  StartDate (ISO date, optional if using ages)
  EndDate (ISO date, optional if using ages)
  NumberOfHours (Float)
  TimeIncrement (Enum)
  CareRateType (Enum)
  RateValues (Map<String, Float>, optional)
  PercentageLess (Float, default 0)
  ManualRate (Float, required only when CareRateType = Specify_Rate)
  SpecifyIncrement (Enum, required for *_Specify increments)
  NumberDaysSpecify (Float, required for Per_Day_Specify)
  NumberWeeksSpecify (Float, required for Per_Week_Specify / Per_Weekday_Specify / Per_Weekend_Specify)
  NumberMonthsSpecify (Float, required for Per_Month_Specify)
  IncludePublicHolidays (Boolean, for Per_Weekday)
  PublicHolidaysPerYear (Float, used when IncludePublicHolidays = false)

Outputs:
  PeriodYears (Float)
  AnnualisedHours (Float)
  EffectiveRate (Float)
  AnnualisedCost (Float)
  Trace (List<String>)

Calc:
  Step 1: Resolve PeriodYears from either age or date mode
          Age mode:  PeriodYears = AgeAtEnd - AgeAtStart
          Date mode: PeriodYears = (EndDate - StartDate in days) / 365.25
          If invalid or <=0 -> raise error

  Step 2: Resolve EffectiveRate
          If CareRateType = Specify_Rate:
              base_rate = ManualRate (required)
          Else:
              base_rate = RateValues[CareRateType] (required)
          EffectiveRate = base_rate * (1 - PercentageLess / 100)

  Step 3: Resolve AnnualisedHours by TimeIncrement

    If TimeIncrement = Over_Period:
      AnnualisedHours = NumberOfHours / PeriodYears

    If TimeIncrement = Per_Day:
      AnnualisedHours = NumberOfHours * 365.25

    If TimeIncrement = Per_Week:
      AnnualisedHours = NumberOfHours * 52

    If TimeIncrement = Per_Month:
      AnnualisedHours = NumberOfHours * 12

    If TimeIncrement = Per_Year:
      AnnualisedHours = NumberOfHours

    If TimeIncrement = Per_Weekday:
      AnnualisedHours = NumberOfHours * (260 if IncludePublicHolidays else (260 - PublicHolidaysPerYear))

    If TimeIncrement = Per_Weekend:
      AnnualisedHours = NumberOfHours * 104

    If TimeIncrement in {Per_Monday..Per_Sunday}:
      AnnualisedHours = NumberOfHours * (365.25 / 7)

    If TimeIncrement = Per_Day_Specify:
      Require NumberDaysSpecify and SpecifyIncrement.
      Over_Period_Specify: total_hours = NumberDaysSpecify * NumberOfHours
      Per_Week_Specify:   total_hours = (PeriodYears * 52) * NumberDaysSpecify * NumberOfHours
      Per_Month_Specify:  total_hours = (PeriodYears * 12) * NumberDaysSpecify * NumberOfHours
      Per_Year_Specify:   total_hours = PeriodYears * NumberDaysSpecify * NumberOfHours
      AnnualisedHours = total_hours / PeriodYears

    If TimeIncrement in {Per_Week_Specify, Per_Weekday_Specify, Per_Weekend_Specify}:
      Require NumberWeeksSpecify and SpecifyIncrement.
      If SpecifyIncrement = Per_Week_Specify -> raise error (unsupported)
      multiplier = 5 only for Per_Weekday_Specify, otherwise 1
      Over_Period_Specify: total_hours = NumberWeeksSpecify * NumberOfHours * multiplier
      Per_Month_Specify:   total_hours = (PeriodYears * 12) * NumberWeeksSpecify * NumberOfHours * multiplier
      Per_Year_Specify:    total_hours = PeriodYears * NumberWeeksSpecify * NumberOfHours * multiplier
      AnnualisedHours = total_hours / PeriodYears

    If TimeIncrement = Per_Month_Specify:
      Require NumberMonthsSpecify and SpecifyIncrement.
      If SpecifyIncrement in {Per_Week_Specify, Per_Month_Specify} -> raise error (unsupported)
      Over_Period_Specify: total_hours = NumberMonthsSpecify * NumberOfHours
      Per_Year_Specify:    total_hours = PeriodYears * NumberMonthsSpecify * NumberOfHours
      AnnualisedHours = total_hours / PeriodYears

    Else:
      raise error for unsupported increment

  Step 4: AnnualisedCost = AnnualisedHours * EffectiveRate

  Step 5: Return outputs + Trace lines for each intermediate step
```

---

## Implemented class mapping

```
Class: CareCalculation
File: formulas/care_calculation.py
Public method: calculate(...)
CLI hook: main.py -> command "care-calc"
```

---

## Care Split Calculation

```
Function CalculateCareSplitAnnualisedCost
Inputs:
  Periods (List of period objects with age ranges and care inputs)
  RequireContiguous (Boolean, default true)

Outputs:
  PeriodResults (List)
  TotalSplitAnnualisedCost (Float)

Calc:
  Step 1: Validate each period has age_at_start < age_at_end
  Step 2: Validate no overlap across periods
  Step 3: If RequireContiguous=true, enforce end of period n == start of period n+1
  Step 4: Run CalculateCareAnnualisedCost for each period
  Step 5: Sum annualised_cost values
```

---

## Care Multiplier Calculation (Table 36 + Apportionment)

```
Function CalculateCarePeriodMultiplier
Inputs:
  StartYears (Float)
  EndYears (Float)
  LifeExpectancyYears (Float)
  LifeMultiplier (Float)
  Table36Vector (List<Float>, 1-based years: year1, year2, ...)
  // In CLI, primary source is --table36-csv (e.g. data/ogden8table36dr05.csv)
  // Optional debug source is --table36-values

Outputs:
  TermMultiplierStart (Float)
  TermMultiplierEnd (Float)
  LifeTermMultiplier (Float)
  PeriodMultiplier (Float)
  Trace (List<String>)

Calc:
  Step 1: Interpolate Table 36 at StartYears:
          floor=start_year_floor, ceil=start_year_floor+1
          M_start = ((ceil - StartYears) * table[floor]) + ((StartYears - floor) * table[ceil])

  Step 2: Interpolate Table 36 at EndYears to get M_end

  Step 3: Interpolate Table 36 at LifeExpectancyYears to get M_life

  Step 4: PeriodMultiplier = ((M_end - M_start) / M_life) * LifeMultiplier

  Step 5: Return outputs + interpolation trace
```

---

## Care Claim Calculation (Orchestrator)

```
Function CalculateCareClaim
Inputs:
  Inputs for CalculateCareAnnualisedCost
  Inputs for CalculateCarePeriodMultiplier
  // If LifeMultiplier not provided manually:
  // derive from claimant_age + gender using whole-life tables (Ogden Table 1/2 at 0.5%)
  // If term_start/term_end years are not provided:
  // derive as (age_at_start - claimant_age) and (age_at_end - claimant_age)

Outputs:
  AnnualisedCost (Float)
  PeriodMultiplier (Float)
  TotalAward (Float)
  Trace (List<String>)

Calc:
  Step 1: annualised_cost = CalculateCareAnnualisedCost(...)
  Step 2: period_multiplier = CalculateCarePeriodMultiplier(...)
  Step 3: total_award = annualised_cost * period_multiplier
  Step 4: return merged trace and outputs
```

---

## Error policy

```
- No silent ignore/fallback behavior.
- Invalid combinations throw meaningful ValueError messages.
- Missing required specify fields throw explicit errors.
```
