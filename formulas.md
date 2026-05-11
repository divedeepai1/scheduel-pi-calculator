## Implemented Functions Index

- `Care Calculation (Age-Based v1)` -> class `CareCalculation` -> CLI `care-calc`
- `Care Split Calculation` -> class `CareSplitCalculation` -> CLI `care-calc-split`
- `Care Multiplier Calculation (Table 36 + Apportionment)` -> class `CareMultiplierCalculation`
- `Care Whole-Life Calculation` -> class `CareWholeLifeCalculation`
- `Care Claim Calculation (Orchestrator)` -> class `CareClaimCalculation` -> CLI `care-claim-calc`
- `Care Claim Split Calculation (PI-style)` -> class `CareClaimCalculation` (`calculate_split`) -> CLI `care-claim-split-calc`
- `Equipment Calculation` -> class `EquipmentCalculation` -> CLI `equipment-calc`
- `Travel Calculation` -> class `TravelCalculation` -> CLI `travel-calc`
- `Travel Claim Calculation` -> class `TravelClaimCalculation` -> CLI `travel-claim-calc`
- `Vehicle Calculation` -> class `VehicleCalculation` -> CLI `vehicle-calc`
- `Loss Of Earnings Interpolation` -> class `LossOfEarningsInterpolation` -> CLI `loe-interp-compare`
- `Earnings Calculation` -> class `EarningsCalculation` -> CLI `earnings-calc`
- `Earnings Split Calculation` -> class `EarningsSplitCalculation` -> CLI `earnings-split-calc`
- `Earnings Award Calculation` -> class `EarningsAwardCalculation` -> CLI `earnings-award-calc`

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

## Care Claim Split Calculation (PI-style)

```
Function CalculateCareClaimSplit
Inputs:
  Periods (List of split rows; each row has either age_at_start+age_at_end OR period_until_age)
  ClaimantAge (Float, used to derive term years)
  LifeExpectancyYears (Float)
  LifeMultiplier (Float)
  RequireContiguous (Boolean, default true)

Outputs:
  PhaseResults (List: annualised_cost, period_multiplier, total_award per row)
  TotalAward (Float, sum of phase totals)
  Trace (List<String>)

Calc:
  Step 1: Resolve each row into [age_at_start, age_at_end] and validate end > start
  Step 2: Validate no overlap, and contiguity if enabled
  Step 3: For each row:
          term_start_years = age_at_start - claimant_age
          term_end_years = age_at_end - claimant_age
          phase = CalculateCareClaim(...) with shared life inputs
  Step 4: Sum phase totals into TotalAward
  Step 5: Return phase list + total + trace
```

---

## Error policy

```
- No silent ignore/fallback behavior.
- Invalid combinations throw meaningful ValueError messages.
- Missing required specify fields throw explicit errors.
- Table 36 years must be `>= 0`; year `0` interpolates to `0.0` for start-at-calculation handling.
```

---

## Equipment Calculation

```

---

## Travel Calculation

```
Function CalculateTravelAnnualLoss
Inputs:
  Distance (Float)
  DistanceInputType (Each_Way|Overall)
  MileageRate (Float)
  ParkingCost (Float)
  JourneyCount (Float)
  TimeIncrement (Over_Period|Per_Day|Per_Week|Per_Month|Per_Year|Per_Weekday|Per_Weekend)

Outputs:
  EffectiveDistance
  JourneyCost
  AnnualJourneyCount
  AnnualLoss
  Trace

Calc:
  Step 1: EffectiveDistance = Distance * 2 when Each_Way else Distance
  Step 2: JourneyCost = (EffectiveDistance * MileageRate) + ParkingCost
  Step 3: AnnualJourneyCount:
          Over_Period -> JourneyCount / PeriodYears
          otherwise -> JourneyCount * FrequencyPerYear(TimeIncrement)
  Step 4: AnnualLoss = AnnualJourneyCount * JourneyCost
```

---

## Travel Claim Calculation

```
Function CalculateTravelClaim
Inputs:
  Inputs for CalculateTravelAnnualLoss
  AgeAtStart
  AgeAtEnd
  ClaimantAge
  LifeExpectancyYears
  LifeMultiplier
  Table36Vector

Outputs:
  AnnualLoss
  PeriodMultiplier
  TotalLoss
  Trace

Calc:
  Step 1: AnnualLoss = CalculateTravelAnnualLoss(...)
  Step 2: start_years = AgeAtStart - ClaimantAge
  Step 3: end_years = AgeAtEnd - ClaimantAge
  Step 4: PeriodMultiplier = care-style apportionment using Table 36 and LifeMultiplier
  Step 5: TotalLoss = AnnualLoss * PeriodMultiplier
```
Function CalculateEquipmentLoss
Inputs:
  AgeAtStart (Float)
  AgeAtEnd (Float)
  ClaimantAge (Float)
  CostOfEquipment (Float)
  ReplacementEveryValue (Float)
  ReplacementEveryUnit (Days|Weeks|Months|Years)
  LifeExpectancyYears (Float)
  LifeMultiplier (Float)
  PurchaseMortalityMode (no_mortality|use_mortality, default no_mortality)
  PurchaseBoundaryMode (future_only|include_start, default future_only)
  AnnualInsurance (Float, default 0)
  AnnualMaintenance (Float, default 0)
  Table35Vector (List<Float>, from Ogden Table 35)
  Table36Vector (List<Float>, from Ogden Table 36)

Outputs:
  PeriodYears
  AnnualEquipmentCostDisplay
  PurchaseCount
  CapitalTotal
  EquipmentMultiplier
  AnnualRecurringCost
  RecurringMultiplier
  RecurringTotal
  TotalLoss
  Trace

Calc:
  Step 1: PeriodYears = AgeAtEnd - AgeAtStart
  Step 2: StartYears = AgeAtStart - ClaimantAge; EndYears = AgeAtEnd - ClaimantAge
  Step 2: Convert replacement frequency to years:
          Days -> value/365, Weeks -> value/(365/7), Months -> value/12, Years -> value
  Step 3: Build purchase years:
          future_only -> first purchase after start
          include_start -> include start-year purchase, then each interval to end
  Step 4: For each purchase year:
          factor = Table35(purchase_year_i)
          if PurchaseMortalityMode = use_mortality:
             apply calibrated mortality adjustment to factor
          EquipmentMultiplier += factor
  Step 5: CapitalTotal = CostOfEquipment * EquipmentMultiplier
  Step 6: RecurringMultiplier = ((Table36(EndYears)-Table36(StartYears))/Table36(LifeExpectancyYears)) * LifeMultiplier
  Step 7: InsuranceTotal = AnnualInsurance * RecurringMultiplier
  Step 8: MaintenanceTotal = AnnualMaintenance * RecurringMultiplier
  Step 9: TotalLoss = CapitalTotal + InsuranceTotal + MaintenanceTotal
```

---

## Vehicle Calculation

```

---

## Loss Of Earnings Interpolation Comparison

```
Function CompareRetirementAgeInterpolation
Inputs:
  RetirementAgeActual (Float)
  RetirementAgeLower (Float)
  RetirementAgeUpper (Float)
  MultiplierLower (Float)
  MultiplierUpper (Float)
  AdditionalTablesMultiplier (Float, optional)

Outputs:
  ManualMultiplier
  AdditionalTablesMultiplier
  Delta
  PercentDelta
  Trace

Calc:
  Step 1: Validate RetirementAgeLower <= RetirementAgeActual <= RetirementAgeUpper
  Step 2: ManualMultiplier =
          ((RetirementAgeUpper - RetirementAgeActual) * MultiplierLower
           + (RetirementAgeActual - RetirementAgeLower) * MultiplierUpper)
           / (RetirementAgeUpper - RetirementAgeLower)
  Step 3: If AdditionalTablesMultiplier provided:
          Delta = ManualMultiplier - AdditionalTablesMultiplier
          PercentDelta = (Delta / AdditionalTablesMultiplier) * 100
  Step 4: Return comparison values + trace
```
Function CalculateVehicleLoss
Inputs:
  ClaimantAge (Float)
  AgeAtStart (Float)
  AgeAtEnd (Float)
  LifeExpectancyEndAge (Float)
  LifeExpectancyYears (Float)
  LifeMultiplier (Float)
  RequiredVehicleCost (Float)
  ExistingVehicleCredit (Float)
  TradeInValue (Float)
  ReplacementEveryValue (Float)
  ReplacementEveryUnit (Days|Weeks|Months|Years)
  IncreasedInsurance (Float)
  IncreasedRunningCosts (Float)
  Table35Vector (List<Float>)
  Table36Vector (List<Float>)

Outputs:
  InitialNetCost
  ReplacementNetCost
  InitialMultiplier
  InitialTotal
  ReplacementCount
  ReplacementsMultiplier
  ReplacementsTotal
  AnnualMultiplier
  InsuranceTotal
  RunningTotal
  TotalLoss
  Trace

Calc:
  Step 1: EffectiveEndAge = min(AgeAtEnd, LifeExpectancyEndAge)
          StartYears = AgeAtStart - ClaimantAge; EndYears = EffectiveEndAge - ClaimantAge
  Step 2: InitialNetCost = RequiredVehicleCost - ExistingVehicleCredit
  Step 3: ReplacementNetCost = RequiredVehicleCost - TradeInValue
  Step 4: Convert replacement cycle to years (Days/Weeks/Months/Years)
  Step 5: InitialMultiplier = Table35(StartYears), with interpolation
  Step 6: InitialTotal = InitialNetCost * InitialMultiplier
  Step 7: Build replacement times from (StartYears + CycleYears) to EndYears (inclusive)
  Step 8: ReplacementsMultiplier = sum(Table35(replacement_time_i))
  Step 9: ReplacementsTotal = ReplacementNetCost * ReplacementsMultiplier
  Step 10: AnnualMultiplier = ((Table36(EndYears)-Table36(StartYears))/Table36(LifeExpectancyYears)) * LifeMultiplier
  Step 11: InsuranceTotal = IncreasedInsurance * AnnualMultiplier
  Step 12: RunningTotal = IncreasedRunningCosts * AnnualMultiplier
  Step 13: TotalLoss = InitialTotal + ReplacementsTotal + InsuranceTotal + RunningTotal
```
