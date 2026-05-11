import argparse
import sys
from typing import Dict
import csv
import json

from formulas import (
    CareCalculation,
    CareSplitCalculation,
    CareMultiplierCalculation,
    CareClaimCalculation,
    CareWholeLifeCalculation,
    ContinuousMultiplierCalculation,
    GeneralContinuousCalculation,
    GeneralContinuousButForCalculation,
    GeneralOneOffCalculation,
    GeneralPeriodicalCalculation,
    LifetimeSplitCalculation,
    PeriodicalMultiplierCalculation,
    EquipmentCalculation,
    TravelCalculation,
    TravelClaimCalculation,
    VehicleCalculation,
    LossOfEarningsInterpolation,
    EarningsCalculation,
    EarningsAsheCalculation,
    EarningsSplitCalculation,
    EarningsAwardCalculation,
    LostYearsCalculation,
    PensionCalculation,
    PensionEarlyReceiptCalculation,
)


def _parse_rate_entry(entry: str) -> tuple[str, float]:
    if "=" not in entry:
        raise argparse.ArgumentTypeError("Rate entry must be in KEY=VALUE format.")
    key, value = entry.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("Rate key cannot be empty.")
    try:
        parsed = float(value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid float value in rate entry: {entry}") from exc
    return key, parsed


def _build_rates_dict(rate_entries: list[tuple[str, float]]) -> Dict[str, float]:
    rates: Dict[str, float] = {}
    for key, value in rate_entries:
        rates[key] = value
    return rates


def _parse_float_list(values: str) -> list[float]:
    try:
        parsed = [float(v.strip()) for v in values.split(",") if v.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid float list for --table36-values.") from exc
    if not parsed:
        raise argparse.ArgumentTypeError("--table36-values cannot be empty.")
    return parsed


def _load_table36_vector(csv_path: str) -> list[float]:
    vector: list[float] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header:
            try:
                vector.append(float(header[0]))
            except (TypeError, ValueError, IndexError):
                pass
        for row in reader:
            if not row:
                continue
            try:
                vector.append(float(row[0]))
            except (TypeError, ValueError, IndexError):
                continue
    if not vector:
        raise ValueError(f"No numeric values found in {csv_path}.")
    return vector


def _load_whole_life_table(csv_path: str) -> list[tuple[float, float]]:
    table: list[tuple[float, float]] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            try:
                age = float(row[0])
                value = float(row[1])
                table.append((age, value))
            except (TypeError, ValueError, IndexError):
                continue
    if not table:
        raise ValueError(f"No usable [age, multiplier] rows found in {csv_path}.")
    return table


def _load_retirement_table(csv_path: str, discount_rate: float = 0.5) -> list[tuple[float, float]]:
    return EarningsCalculation.load_retirement_table(csv_path=csv_path, discount_rate=discount_rate)


def cmd_continuous_multiplier_calculation(args: argparse.Namespace) -> None:
    table36_vector = _load_table36_vector(args.table36_csv)

    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=float(args.calculation_age),
            gender=str(args.gender),
        )
    else:
        life_multiplier = float(args.life_multiplier)

    calc = ContinuousMultiplierCalculation(table36_vector=table36_vector)
    result = calc.calculate(
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        end_age=(None if args.end_at_rest_of_life else float(args.end_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
        end_at_rest_of_life=bool(args.end_at_rest_of_life),
        pi_parity_mode=bool(args.pi_parity_mode),
    )

    print(f"Calculation Age: {result['calculation_age']:.8f}")
    print(f"Start Age: {result['start_age']:.8f}")
    print(f"End Age: {result['end_age']:.8f}")
    print(f"Life Expectancy Age: {result['life_expectancy_age']:.8f}")
    print(f"Start Years: {result['start_years']:.8f}")
    print(f"End Years: {result['end_years']:.8f}")
    print(f"Life Expectancy Years: {result['life_expectancy_years']:.8f}")
    print(f"Life Multiplier: {result['life_multiplier']:.8f}")
    print(f"Term Multiplier Start: {result['term_multiplier_start']:.8f}")
    print(f"Term Multiplier End: {result['term_multiplier_end']:.8f}")
    print(f"Life Term Multiplier: {result['term_multiplier_life_expectancy']:.8f}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_general_continuous_calculation(args: argparse.Namespace) -> None:
    table36_vector = _load_table36_vector(args.table36_csv)

    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=float(args.calculation_age),
            gender=str(args.gender),
        )
    else:
        life_multiplier = float(args.life_multiplier)

    cm = ContinuousMultiplierCalculation(table36_vector=table36_vector)
    gc = GeneralContinuousCalculation(cm_calculation=cm)
    result = gc.calculate(
        loss_amount=float(args.loss_amount),
        loss_frequency=str(args.loss_frequency),
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        end_age=(None if args.end_at_rest_of_life else float(args.end_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
        end_at_rest_of_life=bool(args.end_at_rest_of_life),
    )

    print(f"Annual Loss: {result['annual_loss']:.8f}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_general_continuous_butfor_calculation(args: argparse.Namespace) -> None:
    table36_vector = _load_table36_vector(args.table36_csv)
    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(claimant_age=float(args.calculation_age), gender=str(args.gender))
    else:
        life_multiplier = float(args.life_multiplier)

    cm = ContinuousMultiplierCalculation(table36_vector=table36_vector)
    gcbf = GeneralContinuousButForCalculation(cm_calculation=cm)
    result = gcbf.calculate(
        cost_prior=float(args.cost_prior),
        cost_prior_frequency=str(args.cost_prior_frequency),
        cost_result=float(args.cost_result),
        cost_result_frequency=str(args.cost_result_frequency),
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        end_age=(None if args.end_at_rest_of_life else float(args.end_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
        end_at_rest_of_life=bool(args.end_at_rest_of_life),
    )

    print(f"Annual Prior: {result['annual_prior']:.8f}")
    print(f"Annual Result: {result['annual_result']:.8f}")
    print(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_general_one_off_calculation(args: argparse.Namespace) -> None:
    table35_vector = _load_table36_vector(args.table35_csv)
    calc = GeneralOneOffCalculation(table35_vector=table35_vector)
    result = calc.calculate(
        loss_amount=float(args.loss_amount),
        calculation_age=float(args.calculation_age),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
    )
    print(f"Start Years: {result['start_years']:.8f}")
    print(f"Multiplier: {result['multiplier']:.8f}")
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_general_periodical_calculation(args: argparse.Namespace) -> None:
    table35_vector = _load_table36_vector(args.table35_csv)
    table36_vector = _load_table36_vector(args.table36_csv)
    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(claimant_age=float(args.calculation_age), gender=str(args.gender))
    else:
        life_multiplier = float(args.life_multiplier)

    calc = GeneralPeriodicalCalculation(table35_vector=table35_vector, table36_vector=table36_vector)
    result = calc.calculate(
        loss_amount=float(args.loss_amount),
        recurrence_every=float(args.recurrence_every),
        recurrence_unit=str(args.recurrence_unit),
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        end_age=(None if args.end_at_rest_of_life else float(args.end_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
        end_at_rest_of_life=bool(args.end_at_rest_of_life),
    )
    print(f"Purchase Count: {result['purchase_count']}")
    print(f"Raw Multiplier: {result['raw_multiplier']:.8f}")
    print(f"Life Term Multiplier: {result['life_term_multiplier']:.8f}")
    print(f"Life Multiplier: {result['life_multiplier']:.8f}")
    print(f"Multiplier: {result['multiplier']:.8f}")
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_lifetime_split_calculation(args: argparse.Namespace) -> None:
    table36_vector = _load_table36_vector(args.table36_csv)
    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(claimant_age=float(args.calculation_age), gender=str(args.gender))
    else:
        life_multiplier = float(args.life_multiplier)

    periods: list[dict] = []
    if args.period_file:
        with open(args.period_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            raise ValueError("period_file must contain a JSON array.")
        periods.extend(payload)
    for item in args.period_json or []:
        parsed = json.loads(item)
        if not isinstance(parsed, dict):
            raise ValueError("--period-json entries must be JSON objects.")
        periods.append(parsed)
    if not periods:
        raise ValueError("Provide at least one period via --period-json or --period-file.")

    calc = LifetimeSplitCalculation(cm_calculation=ContinuousMultiplierCalculation(table36_vector=table36_vector))
    result = calc.calculate(
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        periods=periods,
        start_at_calculation_age=bool(args.start_at_calculation_age),
        start_age=args.start_age,
    )
    for p in result["periods"]:
        print(
            f"Period {p['index']}: start={p['start_age']:.8f}, end={p['end_age']:.8f}, "
            f"annual={p['annualised_amount']:.8f}, mult={p['period_multiplier']:.8f}, total={p['period_total']:.8f}"
        )
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_periodical_multiplier_calculation(args: argparse.Namespace) -> None:
    table35_vector = _load_table36_vector(args.table35_csv)
    table36_vector = _load_table36_vector(args.table36_csv)
    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(claimant_age=float(args.calculation_age), gender=str(args.gender))
    else:
        life_multiplier = float(args.life_multiplier)

    gp = GeneralPeriodicalCalculation(table35_vector=table35_vector, table36_vector=table36_vector)
    pm = PeriodicalMultiplierCalculation(gp_calculation=gp)
    result = pm.calculate(
        recurrence_every=float(args.recurrence_every),
        recurrence_unit=str(args.recurrence_unit),
        calculation_age=float(args.calculation_age),
        life_expectancy_age=float(args.life_expectancy_age),
        life_multiplier=float(life_multiplier),
        start_age=(None if args.start_at_calculation_age else float(args.start_age)),
        end_age=(None if args.end_at_rest_of_life else float(args.end_age)),
        start_at_calculation_age=bool(args.start_at_calculation_age),
        end_at_rest_of_life=bool(args.end_at_rest_of_life),
        loss_amount=float(args.loss_amount or 0.0),
        pi_parity_mode=bool(args.pi_parity_mode),
    )
    print(f"Purchase Count: {result['purchase_count']}")
    print(f"Raw Multiplier: {result['raw_multiplier']:.8f}")
    print(f"Life Term Multiplier: {result['life_term_multiplier']:.8f}")
    print(f"Life Multiplier: {result['life_multiplier']:.8f}")
    print(f"Multiplier: {result['multiplier']:.8f}")
    print(f"Total: {result['total']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_care_calculation(args: argparse.Namespace) -> None:
    calc = CareCalculation()
    rates = _build_rates_dict(args.rate or [])
    result = calc.calculate(
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        start_date=args.start_date,
        end_date=args.end_date,
        number_of_hours=args.number_of_hours,
        time_increment=args.time_increment,
        care_rate_type=args.care_rate_type,
        rate_values=rates,
        percentage_less=args.percentage_less,
        manual_rate=args.manual_rate,
        specify_increment=args.specify_increment,
        number_days_specify=args.number_days_specify,
        number_weeks_specify=args.number_weeks_specify,
        number_months_specify=args.number_months_specify,
        include_public_holidays=args.include_public_holidays,
        public_holidays_per_year=args.public_holidays_per_year,
    )

    print(f"Period Years: {result['period_years']:.8f}")
    print(f"Annualised Hours: {result['annualised_hours']:.8f}")
    print(f"Effective Rate: {result['effective_rate']:.8f}")
    print(f"Annualised Cost: {result['annualised_cost']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_care_split_calculation(args: argparse.Namespace) -> None:
    if not args.period_json and not args.period_file:
        raise ValueError("Provide --period-file or at least one --period-json entry.")

    periods = []
    if args.period_file:
        with open(args.period_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            raise ValueError("--period-file must contain a JSON array of period objects.")
        for item in loaded:
            if not isinstance(item, dict):
                raise ValueError("Each entry in --period-file must be a JSON object.")
            periods.append(item)
    for raw in args.period_json:
        try:
            period = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --period-json: {raw}") from exc
        if not isinstance(period, dict):
            raise ValueError(f"Each --period-json must decode to an object: {raw}")
        periods.append(period)

    split_calc = CareSplitCalculation(care_calculation=CareCalculation())
    result = split_calc.calculate_split(
        periods=periods,
        require_contiguous=args.require_contiguous,
    )

    for idx, period_result in enumerate(result["period_results"], start=1):
        print(f"Period {idx} Annualised Cost: {period_result['annualised_cost']:.8f}")
    print(f"Total Split Annualised Cost: {result['total_split_annualised_cost']:.8f}")


def cmd_care_claim_calculation(args: argparse.Namespace) -> None:
    rates = _build_rates_dict(args.rate or [])
    table36_vector = args.table36_values
    if args.table36_csv:
        table36_vector = _load_table36_vector(args.table36_csv)
    if not table36_vector:
        raise ValueError("Provide either --table36-values or --table36-csv.")

    if args.life_multiplier is None:
        if args.claimant_age is None or args.gender is None:
            raise ValueError(
                "Provide --life-multiplier, or provide both --claimant-age and --gender for auto-calculation."
            )
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=args.claimant_age,
            gender=args.gender,
        )
    else:
        life_multiplier = args.life_multiplier

    if args.term_start_years is None or args.term_end_years is None:
        if args.claimant_age is None:
            raise ValueError(
                "Provide --term-start-years and --term-end-years, or provide --claimant-age to auto-derive term years."
            )
        term_start_years = args.age_at_start - args.claimant_age
        term_end_years = args.age_at_end - args.claimant_age
    else:
        term_start_years = args.term_start_years
        term_end_years = args.term_end_years

    orchestrator = CareClaimCalculation(
        care_calculation=CareCalculation(),
        care_multiplier_calculation=CareMultiplierCalculation(table36_vector=table36_vector),
    )
    result = orchestrator.calculate(
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        number_of_hours=args.number_of_hours,
        time_increment=args.time_increment,
        care_rate_type=args.care_rate_type,
        rate_values=rates,
        percentage_less=args.percentage_less,
        manual_rate=args.manual_rate,
        specify_increment=args.specify_increment,
        number_days_specify=args.number_days_specify,
        number_weeks_specify=args.number_weeks_specify,
        number_months_specify=args.number_months_specify,
        term_start_years=term_start_years,
        term_end_years=term_end_years,
        life_expectancy_years=args.life_expectancy_years,
        life_multiplier=life_multiplier,
    )

    print(f"Annualised Cost: {result['annualised_cost']:.8f}")
    print(f"Life Multiplier: {life_multiplier:.8f}")
    print(f"Term Start Years: {term_start_years:.8f}")
    print(f"Term End Years: {term_end_years:.8f}")
    print(f"Term Multiplier Start: {result['term_multiplier_start']:.8f}")
    print(f"Term Multiplier End: {result['term_multiplier_end']:.8f}")
    print(f"Life Term Multiplier: {result['term_multiplier_life_expectancy']:.8f}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Total Award: {result['total_award']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_care_claim_split_calculation(args: argparse.Namespace) -> None:
    if not args.period_file and not args.period_json:
        raise ValueError("Provide --period-file or at least one --period-json for split claim.")

    periods = []
    if args.period_file:
        with open(args.period_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            raise ValueError("--period-file must contain a JSON array.")
        periods.extend(loaded)
    for raw in args.period_json:
        periods.append(json.loads(raw))

    table36_vector = args.table36_values
    if args.table36_csv:
        table36_vector = _load_table36_vector(args.table36_csv)
    if not table36_vector:
        raise ValueError("Provide either --table36-values or --table36-csv.")

    if args.life_multiplier is None:
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=args.claimant_age,
            gender=args.gender,
        )
    else:
        life_multiplier = args.life_multiplier

    orchestrator = CareClaimCalculation(
        care_calculation=CareCalculation(),
        care_multiplier_calculation=CareMultiplierCalculation(table36_vector=table36_vector),
    )
    result = orchestrator.calculate_split(
        periods=periods,
        claimant_age=args.claimant_age,
        life_expectancy_years=args.life_expectancy_years,
        life_multiplier=life_multiplier,
        require_contiguous=args.require_contiguous,
    )

    print(f"Life Multiplier: {life_multiplier:.8f}")
    for phase in result["phase_results"]:
        print(
            f"Phase {phase['phase']}: age {phase['age_at_start']:.2f}->{phase['age_at_end']:.2f}, "
            f"annual={phase['annualised_cost']:.8f}, multiplier={phase['period_multiplier']:.8f}, total={phase['total_award']:.8f}"
        )
    print(f"Split Claim Total Award: {result['total_award']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_equipment_calculation(args: argparse.Namespace) -> None:
    table35_vector = _load_table36_vector(args.table35_csv)
    table36_vector = args.table36_values
    if args.table36_csv:
        table36_vector = _load_table36_vector(args.table36_csv)
    if not table36_vector:
        raise ValueError("Provide either --table36-values or --table36-csv.")

    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError(
                "Provide --life-multiplier, or provide --gender for auto life multiplier."
            )
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=args.claimant_age,
            gender=args.gender,
        )
    else:
        life_multiplier = args.life_multiplier

    if args.life_expectancy_years is None:
        if args.recurring_life_basis == "period":
            life_expectancy_years = args.age_at_end - args.claimant_age
        else:
            # PI default: full-life denominator for recurring apportionment.
            life_expectancy_years = args.life_expectancy_end_age - args.claimant_age
    else:
        life_expectancy_years = args.life_expectancy_years

    calc = EquipmentCalculation(table35_vector=table35_vector, table36_vector=table36_vector)
    result = calc.calculate(
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        cost_of_equipment=args.cost_of_equipment,
        replacement_every_value=args.replacement_every_value,
        replacement_every_unit=args.replacement_every_unit,
        claimant_age=args.claimant_age,
        life_expectancy_years=life_expectancy_years,
        life_multiplier=life_multiplier,
        annual_insurance=args.annual_insurance,
        annual_maintenance=args.annual_maintenance,
        purchase_mortality_mode=args.purchase_mortality_mode,
        purchase_boundary_mode=args.purchase_boundary_mode,
    )

    unit_lower = args.replacement_every_unit.lower()
    if unit_lower.endswith("s"):
        unit_singular = unit_lower[:-1]
    else:
        unit_singular = unit_lower

    print(
        f"Equipment Loss: {result['capital_total']:.8f} "
        f"(calculated as {result['annual_equipment_cost_display']:.8f} every {args.replacement_every_value:.8f} {unit_singular} "
        f"for {result['purchase_count']} purchases; Multiplier: {result['equipment_multiplier']:.8f})"
    )
    print(
        f"Insurance Costs: {result['insurance_total']:.8f} "
        f"(at {args.annual_insurance:.8f} per year; Multiplier: {result['recurring_multiplier']:.8f})"
    )
    print(
        f"Maintenance Costs: {result['maintenance_total']:.8f} "
        f"(at {args.annual_maintenance:.8f} per year; Multiplier: {result['recurring_multiplier']:.8f})"
    )
    print(f"Life Multiplier: {life_multiplier:.8f}")
    print(f"Life Expectancy Years: {life_expectancy_years:.8f}")
    print(f"Total: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_travel_calculation(args: argparse.Namespace) -> None:
    calc = TravelCalculation()
    result = calc.calculate_annual(
        distance=args.distance,
        distance_input_type=args.distance_input_type,
        mileage_rate=args.mileage_rate,
        parking_cost=args.parking_cost,
        journey_count=args.journey_count,
        time_increment=args.time_increment,
        period_years=args.period_years,
    )

    print(f"Effective Distance: {result['effective_distance']:.8f}")
    print(f"Journey Cost: {result['journey_cost']:.8f}")
    print(f"Annual Journey Count: {result['annual_journey_count']:.8f}")
    print(f"Annual Loss: {result['annual_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_travel_claim_calculation(args: argparse.Namespace) -> None:
    table36_vector = args.table36_values
    if args.table36_csv:
        table36_vector = _load_table36_vector(args.table36_csv)
    if not table36_vector:
        raise ValueError("Provide either --table36-values or --table36-csv.")

    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError(
                "Provide --life-multiplier, or provide --gender for auto life multiplier."
            )
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(
            claimant_age=args.claimant_age,
            gender=args.gender,
        )
    else:
        life_multiplier = args.life_multiplier

    if args.life_expectancy_years is None:
        if args.life_expectancy_end_age is None:
            raise ValueError(
                "Provide --life-expectancy-years or --life-expectancy-end-age for Travel claim."
            )
        life_expectancy_years = args.life_expectancy_end_age - args.claimant_age
    else:
        life_expectancy_years = args.life_expectancy_years

    calc = TravelClaimCalculation(
        travel_calculation=TravelCalculation(),
        care_multiplier_calculation=CareMultiplierCalculation(table36_vector=table36_vector),
    )
    result = calc.calculate(
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        claimant_age=args.claimant_age,
        life_expectancy_years=life_expectancy_years,
        life_multiplier=life_multiplier,
        distance=args.distance,
        distance_input_type=args.distance_input_type,
        mileage_rate=args.mileage_rate,
        parking_cost=args.parking_cost,
        journey_count=args.journey_count,
        time_increment=args.time_increment,
    )

    print(f"Annual Loss: {result['annual_loss']:.8f}")
    print(f"Life Multiplier: {life_multiplier:.8f}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_vehicle_calculation(args: argparse.Namespace) -> None:
    table35_vector = _load_table36_vector(args.table35_csv)
    table36_vector = _load_table36_vector(args.table36_csv)

    if args.life_multiplier is None:
        if args.gender is None:
            raise ValueError("Provide --life-multiplier, or provide --gender for auto life multiplier.")
        whole_life_calc = CareWholeLifeCalculation(
            male_table=_load_whole_life_table(args.male_whole_life_csv),
            female_table=_load_whole_life_table(args.female_whole_life_csv),
        )
        life_multiplier = whole_life_calc.multiplier(claimant_age=args.claimant_age, gender=args.gender)
    else:
        life_multiplier = args.life_multiplier

    if args.life_expectancy_years is None:
        if args.life_expectancy_end_age is not None:
            life_expectancy_years = args.life_expectancy_end_age - args.claimant_age
        else:
            if args.gender is None:
                raise ValueError(
                    "Provide --gender when auto-deriving standard LE years from Additional Tables."
                )
            if str(args.gender).lower() == "male":
                add_zero = args.additional_tables_zero_csv_male
                add_p5 = args.additional_tables_point5_csv_male
            else:
                add_zero = args.additional_tables_zero_csv_female
                add_p5 = args.additional_tables_point5_csv_female
            add_le_years, add_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                zero_csv=add_zero,
                point5_csv=add_p5,
                claimant_age=float(args.claimant_age),
            )
            life_expectancy_years = add_le_years
            if args.life_multiplier is None:
                life_multiplier = add_anchor
    else:
        life_expectancy_years = args.life_expectancy_years

    life_expectancy_end_age = (
        args.life_expectancy_end_age
        if args.life_expectancy_end_age is not None
        else (args.claimant_age + life_expectancy_years)
    )

    calc = VehicleCalculation(table35_vector=table35_vector, table36_vector=table36_vector)
    result = calc.calculate(
        claimant_age=args.claimant_age,
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        life_expectancy_end_age=life_expectancy_end_age,
        life_expectancy_years=life_expectancy_years,
        life_multiplier=life_multiplier,
        required_vehicle_cost=args.required_vehicle_cost,
        existing_vehicle_credit=args.existing_vehicle_credit,
        trade_in_value=args.trade_in_value,
        replacement_every_value=args.replacement_every_value,
        replacement_every_unit=args.replacement_every_unit,
        replacement_start_age=args.replacement_start_age,
        increased_insurance=args.increased_insurance,
        increased_running_costs=args.increased_running_costs,
        purchase_mortality_mode=args.purchase_mortality_mode,
    )

    print(f"Initial Cost: {result['initial_total']:.8f} (Multiplier: {result['initial_multiplier']:.8f})")
    print(
        f"Future Replacements: {result['replacements_total']:.8f} "
        f"(for {result['replacement_count']} purchases; Multiplier: {result['replacements_multiplier']:.8f})"
    )
    print(f"Insurance Costs: {result['insurance_total']:.8f} (Multiplier: {result['annual_multiplier']:.8f})")
    print(f"Running Costs: {result['running_total']:.8f} (Multiplier: {result['annual_multiplier']:.8f})")
    print(f"Total: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_loe_interpolation_compare(args: argparse.Namespace) -> None:
    calc = LossOfEarningsInterpolation()
    multiplier_lower = args.multiplier_lower
    multiplier_upper = args.multiplier_upper
    if multiplier_lower is None and args.multiplier_lower_csv:
        multiplier_lower = calc.multiplier_from_retirement_table_csv(
            csv_path=args.multiplier_lower_csv,
            age_at_trial=args.age_at_trial,
            discount_rate=args.discount_rate_for_manual,
        )
    if multiplier_upper is None and args.multiplier_upper_csv:
        multiplier_upper = calc.multiplier_from_retirement_table_csv(
            csv_path=args.multiplier_upper_csv,
            age_at_trial=args.age_at_trial,
            discount_rate=args.discount_rate_for_manual,
        )
    if multiplier_lower is None or multiplier_upper is None:
        raise ValueError(
            "Provide --multiplier-lower/--multiplier-upper or provide both --multiplier-lower-csv and --multiplier-upper-csv."
        )

    additional_tables_multiplier = args.additional_tables_multiplier
    if additional_tables_multiplier is None and args.additional_tables_csv:
        if args.age_at_trial is None or args.target_end_age is None:
            raise ValueError("Provide --age-at-trial and --target-end-age when using --additional-tables-csv.")
        additional_tables_multiplier = calc.additional_tables_multiplier_from_csv(
            csv_path=args.additional_tables_csv,
            age_at_trial=args.age_at_trial,
            target_end_age=args.target_end_age,
        )

    result = calc.compare(
        retirement_age_actual=args.retirement_age_actual,
        retirement_age_lower=args.retirement_age_lower,
        retirement_age_upper=args.retirement_age_upper,
        multiplier_lower=multiplier_lower,
        multiplier_upper=multiplier_upper,
        additional_tables_multiplier=additional_tables_multiplier,
    )

    print(f"Manual Interpolation Multiplier: {result['manual_multiplier']:.8f}")
    if result["additional_tables_multiplier"] is not None:
        print(f"Additional Tables Multiplier: {result['additional_tables_multiplier']:.8f}")
        print(f"Delta (Manual - Additional): {result['delta']:.8f}")
        if result["percent_delta"] is not None:
            print(f"Percent Delta: {result['percent_delta']:.8f}%")
    else:
        print("Additional Tables Multiplier: not provided")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_loe_period_compare(args: argparse.Namespace) -> None:
    calc = LossOfEarningsInterpolation()
    table36_vector = _load_table36_vector(args.table36_csv)
    result = calc.compare_period_methods(
        table36_vector=table36_vector,
        age_at_trial=args.age_at_trial,
        start_years_from_trial=args.start_years_from_trial,
        end_years_from_trial=args.end_years_from_trial,
        additional_tables_csv=args.additional_tables_csv,
        start_age=args.start_age,
        end_age=args.end_age,
        contingency_factor=args.contingency_factor,
    )

    print(
        f"Manual Term-Certain Period: {result['manual_period']:.8f} "
        f"(start={result['manual_start']:.8f}, end={result['manual_end']:.8f})"
    )
    print(f"Manual After Contingency: {result['manual_after_contingency']:.8f}")
    print(
        f"Additional Tables Period: {result['additional_period']:.8f} "
        f"(start={result['additional_start']:.8f}, end={result['additional_end']:.8f})"
    )
    print(f"Additional After Contingency: {result['additional_after_contingency']:.8f}")
    print(f"Delta (Manual - Additional): {result['delta']:.8f}")
    print(f"Percent Delta: {result['percent_delta']:.8f}%")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_loe_book_compare(args: argparse.Namespace) -> None:
    calc = LossOfEarningsInterpolation()
    result = calc.compare_book_manual_vs_additional(
        claimant_age=args.claimant_age,
        retirement_age_actual=args.retirement_age_actual,
        retirement_age_lower=args.retirement_age_lower,
        retirement_age_upper=args.retirement_age_upper,
        lower_table_csv=args.lower_table_csv,
        upper_table_csv=args.upper_table_csv,
        additional_tables_csv=args.additional_tables_csv,
        discount_rate=args.discount_rate,
    )
    print(f"Manual Multiplier (Book para 33/34): {result['manual_multiplier']:.8f}")
    print(f"Additional Tables Multiplier: {result['additional_multiplier']:.8f}")
    print(f"Delta (Manual - Additional): {result['delta']:.8f}")
    print(f"Percent Delta: {result['percent_delta']:.8f}%")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_earnings_calculation(args: argparse.Namespace) -> None:
    calc = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    result = calc.calculate(
        claimant_age=args.claimant_age,
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        but_for_amount=args.but_for_amount,
        but_for_frequency=args.but_for_frequency,
        but_for_is_net=args.but_for_is_net,
        residual_amount=args.residual_amount,
        residual_frequency=args.residual_frequency,
        residual_is_net=args.residual_is_net,
        employment_type=args.employment_type,
        region=args.region,
        contingency_factor=args.contingency_factor,
        multiplier_mode=args.multiplier_mode,
        additional_tables_csv=args.additional_tables_csv,
        impairment_end_age=args.impairment_end_age,
        impaired_multiplier_method=args.impaired_multiplier_method,
        additional_tables_zero_csv=args.additional_tables_zero_csv,
        additional_tables_point5_csv=args.additional_tables_point5_csv,
        table35_csv=args.table35_csv,
        retirement_table_full_csv=args.retirement_table_csv,
    )
    print(f"Duration Years: {result['period_years']:.8f}")
    print(f"But For Net Annual: {result['but_for_annual_net']:.8f}")
    print(f"Residual Net Annual: {result['residual_annual_net']:.8f}")
    print(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
    print(f"Multiplier Mode Used: {result['multiplier_mode_used']}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Final Multiplier: {result['final_multiplier']:.8f}")
    print(f"Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_earnings_ashe_calculation(args: argparse.Namespace) -> None:
    base = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    calc = EarningsAsheCalculation(earnings_calculation=base)
    result = calc.calculate(
        claimant_age=args.claimant_age,
        age_at_start=args.age_at_start,
        age_at_end=args.age_at_end,
        ashe_workbook_path=args.ashe_workbook_path,
        ashe_dataset=args.ashe_dataset,
        ashe_code=args.ashe_code,
        ashe_region_prefix=args.ashe_region_prefix,
        but_for_amount=args.but_for_amount,
        but_for_ashe_field=args.but_for_ashe_field,
        but_for_frequency=args.but_for_frequency,
        but_for_is_net=args.but_for_is_net,
        residual_amount=args.residual_amount,
        residual_ashe_field=args.residual_ashe_field,
        residual_frequency=args.residual_frequency,
        residual_is_net=args.residual_is_net,
        employment_type=args.employment_type,
        region=args.region,
        contingency_factor=args.contingency_factor,
        multiplier_mode=args.multiplier_mode,
        additional_tables_csv=args.additional_tables_csv,
        life_expectancy_end_age=args.life_expectancy_end_age,
        round_final_multiplier_dp=args.round_final_multiplier_dp,
        pi_round_intermediates_2dp=args.pi_round_intermediates_2dp,
    )
    print(f"ASHE Code Used: {result['ashe_code_used']}")
    print(f"ASHE Description Used: {result['ashe_description_used']}")
    print(f"But For Amount Used: {result['but_for_amount_used']:.8f}")
    print(f"Residual Amount Used: {result['residual_amount_used']:.8f}")
    print(f"Duration Years: {result['period_years']:.8f}")
    print(f"But For Net Annual: {result['but_for_annual_net']:.8f}")
    print(f"Residual Net Annual: {result['residual_annual_net']:.8f}")
    print(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
    print(f"Multiplier Mode Used: {result['multiplier_mode_used']}")
    print(f"Period Multiplier: {result['period_multiplier']:.8f}")
    print(f"Final Multiplier: {result['final_multiplier']:.8f}")
    print(f"Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_earnings_split_calculation(args: argparse.Namespace) -> None:
    if not args.period_file and not args.period_json:
        raise ValueError("Provide --period-file or at least one --period-json.")
    periods = []
    if args.period_file:
        with open(args.period_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            raise ValueError("--period-file must contain a JSON array.")
        periods.extend(loaded)
    for raw in args.period_json:
        periods.append(json.loads(raw))

    base = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    calc = EarningsSplitCalculation(earnings_calculation=base)
    result = calc.calculate_split(
        claimant_age=args.claimant_age,
        periods=periods,
        employment_type=args.employment_type,
        region=args.region,
        contingency_factor=args.contingency_factor,
        require_contiguous=args.require_contiguous,
        multiplier_mode=args.multiplier_mode,
        additional_tables_csv=args.additional_tables_csv,
        impairment_end_age=args.impairment_end_age,
        impaired_multiplier_method=args.impaired_multiplier_method,
        additional_tables_zero_csv=args.additional_tables_zero_csv,
        additional_tables_point5_csv=args.additional_tables_point5_csv,
        table35_csv=args.table35_csv,
        retirement_table_full_csv=args.retirement_table_csv,
    )
    for phase in result["phase_results"]:
        print(
            f"Phase {int(phase['phase'])}: age {phase['age_at_start']:.2f}->{phase['age_at_end']:.2f}, "
            f"net={phase['net_annual_loss']:.8f}, mult={phase['final_multiplier']:.8f}, total={phase['total_loss']:.8f}"
        )
    print(f"Split Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_earnings_award_calculation(args: argparse.Namespace) -> None:
    calc = EarningsAwardCalculation()
    result = calc.calculate(award_amount=args.award_amount)
    print(f"Total Award: {result['total_award']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_lost_years_calculation(args: argparse.Namespace) -> None:
    if not args.earnings_period_file and not args.earnings_period_json:
        raise ValueError("Provide --earnings-period-file or at least one --earnings-period-json entry.")

    periods = []
    if args.earnings_period_file:
        with open(args.earnings_period_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            raise ValueError("--earnings-period-file must contain a JSON array.")
        periods.extend(loaded)
    for raw in args.earnings_period_json:
        periods.append(json.loads(raw))

    base = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    calc = LostYearsCalculation(earnings_calculation=base)
    result = calc.calculate(
        claimant_age=args.claimant_age,
        current_life_end_age=args.current_life_end_age,
        but_for_remaining_life_years=args.but_for_remaining_life_years,
        but_for_multiplier_method=args.but_for_multiplier_method,
        lost_years_rate=args.lost_years_rate,
        contingency_factor=args.contingency_factor,
        earnings_periods=periods,
        pension_lump_sum_amount=args.pension_lump_sum_amount,
        pension_lump_sum_age=args.pension_lump_sum_age,
        pension_annual_amount=args.pension_annual_amount,
        pension_annual_start_age=args.pension_annual_start_age,
        pension_annual_end_age=args.pension_annual_end_age,
        employment_type=args.employment_type,
        region=args.region,
        values_are_net=args.values_are_net,
        table35_csv=args.table35_csv,
        but_for_age=args.but_for_age,
        additional_tables_zero_csv=args.additional_tables_zero_csv,
        additional_tables_point5_csv=args.additional_tables_point5_csv,
    )
    print(f"But For Injury Life Multiplier: {result['but_for_injury_life_multiplier']:.8f}")
    print(f"Current Life Multiplier: {result['current_life_multiplier']:.8f}")
    print(f"Lost Years Multiplier: {result['lost_years_multiplier']:.8f}")
    print(f"Normalization Ratio: {result['normalization_ratio']:.8f}")
    for row in result["line_items"]:
        print(
            f"Line {int(row['index'])}: annual_used={row['annual_used']:.8f}, "
            f"multiplier={row['period_multiplier']:.8f}, total={row['total']:.8f}"
        )
    print(f"Total Future Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_pension_calculation(args: argparse.Namespace) -> None:
    base = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    calc = PensionCalculation(earnings_calculation=base)
    result = calc.calculate(
        claimant_age=args.claimant_age,
        impairment_end_age=args.impairment_end_age,
        but_for_amount=args.but_for_amount,
        but_for_is_net=args.but_for_is_net,
        but_for_employment_type=args.but_for_employment_type,
        residual_amount=args.residual_amount,
        residual_is_net=args.residual_is_net,
        residual_employment_type=args.residual_employment_type,
        region=args.region,
        multiplier_method=args.multiplier_method,
        additional_tables_point5_csv=args.additional_tables_point5_csv,
        additional_tables_zero_csv=args.additional_tables_zero_csv,
    )
    print(f"Retirement Age: {result['retirement_age']:.8f}")
    print(f"Period Years: {result['period_years']:.8f}")
    print(f"But For Net Annual: {result['but_for_net_annual']:.8f}")
    print(f"Residual Net Annual: {result['residual_net_annual']:.8f}")
    print(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
    print(f"But For Injury Life Multiplier: {result['but_for_life_multiplier']:.8f}")
    print(f"Mortality-To-Retirement Multiplier: {result['mortality_to_retirement_multiplier']:.8f}")
    print(f"Pension Multiplier: {result['pension_multiplier']:.8f}")
    print(f"Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def cmd_pension_early_receipt_calculation(args: argparse.Namespace) -> None:
    base = EarningsCalculation(
        table36_vector=_load_table36_vector(args.table36_csv),
        retirement_table=_load_retirement_table(args.retirement_table_csv, args.discount_rate),
        whole_life_table=_load_whole_life_table(args.whole_life_csv),
    )
    calc = PensionEarlyReceiptCalculation(earnings_calculation=base)
    result = calc.calculate(
        claimant_age=args.claimant_age,
        age_at_receipt=args.age_at_receipt,
        retirement_age=args.retirement_age,
        impairment_end_age=args.impairment_end_age,
        expected_lump_sum=args.expected_lump_sum,
        actual_lump_sum=args.actual_lump_sum,
        expected_annual_rate=args.expected_annual_rate,
        expected_annual_is_net=args.expected_annual_is_net,
        expected_annual_employment_type=args.expected_annual_employment_type,
        actual_annual_rate=args.actual_annual_rate,
        actual_annual_is_net=args.actual_annual_is_net,
        actual_annual_employment_type=args.actual_annual_employment_type,
        region=args.region,
        multiplier_method=args.multiplier_method,
        additional_tables_point5_csv=args.additional_tables_point5_csv,
        table35_csv=args.table35_csv,
        additional_tables_zero_csv=args.additional_tables_zero_csv,
    )
    print(f"Life Multiplier at Receipt: {result['life_multiplier_at_receipt']:.8f}")
    print(f"Multiplier to Retirement at Receipt: {result['multiplier_to_retirement_at_receipt']:.8f}")
    print(f"Longden Factor: {result['longden_factor']:.8f}")
    print(f"Years to Retirement: {result['years_to_retirement']:.8f}")
    print(f"Discount Factor: {result['discount_factor']:.8f}")
    print(f"Present Value Expected Lump Sum: {result['present_value_expected_lump_sum']:.8f}")
    print(f"Lump Sum Loss: {result['lump_sum_loss']:.8f}")
    print(f"Annual Loss: {result['annual_loss']:.8f}")
    print(f"Pension Multiplier: {result['pension_multiplier']:.8f}")
    print(f"Annual Line Total: {result['annual_line_total']:.8f}")
    print(f"Total Loss: {result['total_loss']:.8f}")
    print("\nCalculation Trace:")
    for line in result["trace"]:
        print(line)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone schedule calculators.")
    sub = parser.add_subparsers(dest="command", required=True)

    pcm = sub.add_parser("cm-calc", help="Run Continuous Multiplier (CM) calculation.")
    pcm.add_argument("--calculation-age", type=float, required=True)
    pcm.add_argument("--life-expectancy-age", type=float, required=True)
    pcm.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    pcm.add_argument("--end-age", type=float, help="Required unless --end-at-rest-of-life is provided.")
    pcm.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pcm.add_argument("--end-at-rest-of-life", action=argparse.BooleanOptionalAction, default=True)
    pcm.add_argument("--life-multiplier", type=float, help="Optional override.")
    pcm.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pcm.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pcm.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pcm.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pcm.set_defaults(func=cmd_continuous_multiplier_calculation)

    pgc = sub.add_parser("gc-calc", help="Run General Continuous (GC) calculation.")
    pgc.add_argument("--loss-amount", type=float, required=True)
    pgc.add_argument("--loss-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week", "Per_Day"], default="Per_Year")
    pgc.add_argument("--calculation-age", type=float, required=True)
    pgc.add_argument("--life-expectancy-age", type=float, required=True)
    pgc.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    pgc.add_argument("--end-age", type=float, help="Required unless --end-at-rest-of-life is provided.")
    pgc.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pgc.add_argument("--end-at-rest-of-life", action=argparse.BooleanOptionalAction, default=True)
    pgc.add_argument("--life-multiplier", type=float, help="Optional override.")
    pgc.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pgc.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pgc.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pgc.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pgc.set_defaults(func=cmd_general_continuous_calculation)

    pgcbf = sub.add_parser("gcbf-calc", help="Run General Continuous (But For) calculation.")
    pgcbf.add_argument("--cost-prior", type=float, required=True)
    pgcbf.add_argument("--cost-prior-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week", "Per_Day"], default="Per_Year")
    pgcbf.add_argument("--cost-result", type=float, required=True)
    pgcbf.add_argument("--cost-result-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week", "Per_Day"], default="Per_Year")
    pgcbf.add_argument("--calculation-age", type=float, required=True)
    pgcbf.add_argument("--life-expectancy-age", type=float, required=True)
    pgcbf.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    pgcbf.add_argument("--end-age", type=float, help="Required unless --end-at-rest-of-life is provided.")
    pgcbf.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pgcbf.add_argument("--end-at-rest-of-life", action=argparse.BooleanOptionalAction, default=True)
    pgcbf.add_argument("--life-multiplier", type=float, help="Optional override.")
    pgcbf.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pgcbf.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pgcbf.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pgcbf.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pgcbf.set_defaults(func=cmd_general_continuous_butfor_calculation)

    pgof = sub.add_parser("gof-calc", help="Run General One Off (GOF) calculation.")
    pgof.add_argument("--loss-amount", type=float, required=True)
    pgof.add_argument("--calculation-age", type=float, required=True)
    pgof.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    pgof.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pgof.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pgof.set_defaults(func=cmd_general_one_off_calculation)

    pgp = sub.add_parser("gp-calc", help="Run General Periodical (GP) calculation.")
    pgp.add_argument("--loss-amount", type=float, required=True)
    pgp.add_argument("--recurrence-every", type=float, required=True)
    pgp.add_argument("--recurrence-unit", type=str, choices=["Days", "Weeks", "Months", "Years"], required=True)
    pgp.add_argument("--calculation-age", type=float, required=True)
    pgp.add_argument("--life-expectancy-age", type=float, required=True)
    pgp.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    pgp.add_argument("--end-age", type=float, help="Required unless --end-at-rest-of-life is provided.")
    pgp.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pgp.add_argument("--end-at-rest-of-life", action=argparse.BooleanOptionalAction, default=True)
    pgp.add_argument("--life-multiplier", type=float, help="Optional override.")
    pgp.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pgp.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pgp.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pgp.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pgp.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pgp.add_argument("--pi-parity-mode", action=argparse.BooleanOptionalAction, default=True)
    pgp.set_defaults(func=cmd_general_periodical_calculation)

    pls = sub.add_parser("ls-calc", help="Run Lifetime (Split) calculation.")
    pls.add_argument("--calculation-age", type=float, required=True)
    pls.add_argument("--life-expectancy-age", type=float, required=True)
    pls.add_argument("--life-multiplier", type=float, help="Optional override.")
    pls.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pls.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pls.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pls.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pls.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    pls.add_argument("--start-age", type=float, help="Required if --no-start-at-calculation-age.")
    pls.add_argument("--period-json", action="append", default=[], help='Period object e.g. {"end_age":67,"amount":2000,"frequency":"Per_Year"} or {"rest_of_life":true,"amount":4000,"frequency":"Per_Year"}')
    pls.add_argument("--period-file", type=str, help="JSON file containing an array of period objects.")
    pls.set_defaults(func=cmd_lifetime_split_calculation)

    ppm = sub.add_parser("pm-calc", help="Run Periodical Multiplier (PM) calculation.")
    ppm.add_argument("--recurrence-every", type=float, required=True)
    ppm.add_argument("--recurrence-unit", type=str, choices=["Days", "Weeks", "Months", "Years"], required=True)
    ppm.add_argument("--calculation-age", type=float, required=True)
    ppm.add_argument("--life-expectancy-age", type=float, required=True)
    ppm.add_argument("--life-multiplier", type=float, help="Optional override.")
    ppm.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    ppm.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    ppm.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    ppm.add_argument("--start-age", type=float, help="Required unless --start-at-calculation-age is provided.")
    ppm.add_argument("--end-age", type=float, help="Required unless --end-at-rest-of-life is provided.")
    ppm.add_argument("--start-at-calculation-age", action=argparse.BooleanOptionalAction, default=True)
    ppm.add_argument("--end-at-rest-of-life", action=argparse.BooleanOptionalAction, default=True)
    ppm.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    ppm.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    ppm.add_argument("--loss-amount", type=float, default=0.0, help="Optional amount to produce a total line.")
    ppm.add_argument("--pi-parity-mode", action=argparse.BooleanOptionalAction, default=True)
    ppm.set_defaults(func=cmd_periodical_multiplier_calculation)

    pcare = sub.add_parser("care-calc", help="Run care annualisation calculation (age-based v1).")
    pcare.add_argument("--age-at-start", type=float)
    pcare.add_argument("--age-at-end", type=float)
    pcare.add_argument("--start-date", type=str, help="ISO date (YYYY-MM-DD). Use with --end-date.")
    pcare.add_argument("--end-date", type=str, help="ISO date (YYYY-MM-DD). Use with --start-date.")
    pcare.add_argument("--number-of-hours", type=float, required=True)
    pcare.add_argument("--time-increment", type=str, required=True)
    pcare.add_argument("--care-rate-type", type=str, required=True)
    pcare.add_argument(
        "--rate",
        type=_parse_rate_entry,
        action="append",
        help="Care rate entries in KEY=VALUE format. Repeatable.",
    )
    pcare.add_argument("--manual-rate", type=float)
    pcare.add_argument("--percentage-less", type=float, default=0.0)
    pcare.add_argument("--specify-increment", type=str)
    pcare.add_argument("--number-days-specify", type=float)
    pcare.add_argument("--number-weeks-specify", type=float)
    pcare.add_argument("--number-months-specify", type=float)
    pcare.add_argument(
        "--include-public-holidays",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="For Per_Weekday increments, include or exclude public holidays.",
    )
    pcare.add_argument("--public-holidays-per-year", type=float, default=8.0)
    pcare.set_defaults(func=cmd_care_calculation)

    psplit = sub.add_parser("care-calc-split", help="Run split care annualisation across non-overlapping periods.")
    psplit.add_argument(
        "--period-json",
        default=[],
        action="append",
        help='JSON object per period, repeatable. Example: --period-json "{\\"age_at_start\\":67,\\"age_at_end\\":70,\\"number_of_hours\\":20,\\"time_increment\\":\\"Per_Week\\",\\"care_rate_type\\":\\"Basic_Rate\\",\\"rate_values\\":{\\"Basic_Rate\\":12.69}}"',
    )
    psplit.add_argument("--period-file", type=str, help="Path to JSON file containing an array of period objects.")
    psplit.add_argument(
        "--require-contiguous",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require each period to start exactly when previous ends.",
    )
    psplit.set_defaults(func=cmd_care_split_calculation)

    pclaim = sub.add_parser("care-claim-calc", help="Run full care claim calculation (annualisation + multiplier apportionment).")
    pclaim.add_argument("--age-at-start", type=float, required=True)
    pclaim.add_argument("--age-at-end", type=float, required=True)
    pclaim.add_argument("--number-of-hours", type=float, required=True)
    pclaim.add_argument("--time-increment", type=str, required=True)
    pclaim.add_argument("--care-rate-type", type=str, required=True)
    pclaim.add_argument("--rate", type=_parse_rate_entry, action="append")
    pclaim.add_argument("--manual-rate", type=float)
    pclaim.add_argument("--percentage-less", type=float, default=0.0)
    pclaim.add_argument("--specify-increment", type=str)
    pclaim.add_argument("--number-days-specify", type=float)
    pclaim.add_argument("--number-weeks-specify", type=float)
    pclaim.add_argument("--number-months-specify", type=float)
    pclaim.add_argument("--term-start-years", type=float, help="Optional manual override. If omitted, auto-derived from ages.")
    pclaim.add_argument("--term-end-years", type=float, help="Optional manual override. If omitted, auto-derived from ages.")
    pclaim.add_argument("--life-expectancy-years", type=float, required=True)
    pclaim.add_argument("--life-multiplier", type=float, help="Optional manual override. If omitted, auto-calculated from whole-life tables.")
    pclaim.add_argument("--claimant-age", type=float, help="Required when --life-multiplier is not provided.")
    pclaim.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    pclaim.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pclaim.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pclaim.add_argument("--table36-values", type=_parse_float_list, help="Comma-separated Table 36 vector (year1,year2,...).")
    pclaim.add_argument("--table36-csv", type=str, help="CSV file path where first column contains Table 36 values.")
    pclaim.set_defaults(func=cmd_care_claim_calculation)

    pclaims = sub.add_parser("care-claim-split-calc", help="Run full split care claim calculation in one command.")
    pclaims.add_argument("--period-json", default=[], action="append", help="JSON period object. Repeatable.")
    pclaims.add_argument("--period-file", type=str, help="JSON file containing an array of split period objects.")
    pclaims.add_argument("--claimant-age", type=float, required=True)
    pclaims.add_argument("--gender", type=str, choices=["male", "female"], required=True)
    pclaims.add_argument("--life-expectancy-years", type=float, required=True)
    pclaims.add_argument("--life-multiplier", type=float, help="Optional manual override.")
    pclaims.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pclaims.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pclaims.add_argument("--table36-values", type=_parse_float_list, help="Comma-separated Table 36 vector.")
    pclaims.add_argument("--table36-csv", type=str, help="CSV path for Table 36 first column.")
    pclaims.add_argument(
        "--require-contiguous",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require each period to start exactly when previous ends.",
    )
    pclaims.set_defaults(func=cmd_care_claim_split_calculation)

    peq = sub.add_parser("equipment-calc", help="Run equipment calculation (capital replacements + recurring costs).")
    peq.add_argument("--age-at-start", type=float, required=True)
    peq.add_argument("--age-at-end", type=float, required=True)
    peq.add_argument("--cost-of-equipment", type=float, required=True)
    peq.add_argument("--replacement-every-value", type=float, required=True)
    peq.add_argument(
        "--replacement-every-unit",
        type=str,
        choices=["Days", "Weeks", "Months", "Years"],
        required=True,
    )
    peq.add_argument("--annual-insurance", type=float, default=0.0)
    peq.add_argument("--annual-maintenance", type=float, default=0.0)
    peq.add_argument("--claimant-age", type=float, required=True)
    peq.add_argument(
        "--life-expectancy-years",
        type=float,
        help="Optional override. When omitted, defaults to full-life years (life_expectancy_end_age - claimant_age).",
    )
    peq.add_argument(
        "--recurring-life-basis",
        type=str,
        choices=["period", "full_life"],
        default=None,
        help="Optional override. period=use age_at_end-claimant_age, full_life=use life_expectancy_end_age-claimant_age. Default is full_life (PI-style).",
    )
    peq.add_argument("--life-expectancy-end-age", type=float, default=84.69)
    peq.add_argument("--life-multiplier", type=float, help="Optional override.")
    peq.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    peq.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    peq.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    peq.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    peq.add_argument(
        "--purchase-mortality-mode",
        type=str,
        choices=["no_mortality", "use_mortality"],
        default="no_mortality",
    )
    peq.add_argument(
        "--purchase-boundary-mode",
        type=str,
        choices=["future_only", "include_start"],
        default=None,
    )
    peq.add_argument("--table36-values", type=_parse_float_list, help="Comma-separated Table 36 vector.")
    peq.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv", help="CSV path for Table 36 first column.")
    peq.set_defaults(func=cmd_equipment_calculation)

    pt = sub.add_parser("travel-calc", help="Run travel annual loss calculation.")
    pt.add_argument("--distance", type=float, required=True)
    pt.add_argument("--distance-input-type", type=str, choices=["Each_Way", "Overall"], required=True)
    pt.add_argument("--mileage-rate", type=float, required=True)
    pt.add_argument("--parking-cost", type=float, default=0.0)
    pt.add_argument("--journey-count", type=float, required=True)
    pt.add_argument(
        "--time-increment",
        type=str,
        choices=["Over_Period", "Per_Day", "Per_Week", "Per_Month", "Per_Year", "Per_Weekday", "Per_Weekend"],
        required=True,
    )
    pt.add_argument("--period-years", type=float, help="Required when --time-increment Over_Period.")
    pt.set_defaults(func=cmd_travel_calculation)

    ptc = sub.add_parser("travel-claim-calc", help="Run full travel claim calculation (annual + multiplier).")
    ptc.add_argument("--age-at-start", type=float, required=True)
    ptc.add_argument("--age-at-end", type=float, required=True)
    ptc.add_argument("--claimant-age", type=float, required=True)
    ptc.add_argument("--life-expectancy-years", type=float, help="Optional explicit life expectancy years.")
    ptc.add_argument(
        "--life-expectancy-end-age",
        type=float,
        default=84.69,
        help="Rest-of-life age used to derive life_expectancy_years when explicit years are omitted.",
    )
    ptc.add_argument("--life-multiplier", type=float, help="Optional override.")
    ptc.add_argument("--gender", type=str, choices=["male", "female"], help="Required when --life-multiplier is not provided.")
    ptc.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    ptc.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    ptc.add_argument("--distance", type=float, required=True)
    ptc.add_argument("--distance-input-type", type=str, choices=["Each_Way", "Overall"], required=True)
    ptc.add_argument("--mileage-rate", type=float, required=True)
    ptc.add_argument("--parking-cost", type=float, default=0.0)
    ptc.add_argument("--journey-count", type=float, required=True)
    ptc.add_argument(
        "--time-increment",
        type=str,
        choices=["Over_Period", "Per_Day", "Per_Week", "Per_Month", "Per_Year", "Per_Weekday", "Per_Weekend"],
        required=True,
    )
    ptc.add_argument("--table36-values", type=_parse_float_list, help="Comma-separated Table 36 vector.")
    ptc.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    ptc.set_defaults(func=cmd_travel_claim_calculation)

    pv = sub.add_parser("vehicle-calc", help="Run vehicle future loss calculation.")
    pv.add_argument("--claimant-age", type=float, required=True)
    pv.add_argument("--age-at-start", type=float, required=True)
    pv.add_argument("--age-at-end", type=float, required=True)
    pv.add_argument("--required-vehicle-cost", type=float, required=True)
    pv.add_argument("--existing-vehicle-credit", type=float, default=0.0)
    pv.add_argument("--trade-in-value", type=float, default=0.0)
    pv.add_argument("--replacement-every-value", type=float, required=True)
    pv.add_argument("--replacement-every-unit", type=str, choices=["Days", "Weeks", "Months", "Years"], required=True)
    pv.add_argument("--replacement-start-age", type=float, help="Optional override for replacement stream start age.")
    pv.add_argument("--increased-insurance", type=float, default=0.0)
    pv.add_argument("--increased-running-costs", type=float, default=0.0)
    pv.add_argument("--life-expectancy-years", type=float)
    pv.add_argument("--life-expectancy-end-age", type=float)
    pv.add_argument("--life-multiplier", type=float)
    pv.add_argument("--gender", type=str, choices=["male", "female"])
    pv.add_argument("--male-whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pv.add_argument("--female-whole-life-csv", type=str, default="data/ogden8table2dr05.csv")
    pv.add_argument("--additional-tables-zero-csv-male", type=str, default="data/ogden8_additional_males_0.csv")
    pv.add_argument("--additional-tables-point5-csv-male", type=str, default="data/ogden8_additional_males_05.csv")
    pv.add_argument("--additional-tables-zero-csv-female", type=str, default="data/ogden8_additional_females_0.csv")
    pv.add_argument("--additional-tables-point5-csv-female", type=str, default="data/ogden8_additional_females_05.csv")
    pv.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pv.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pv.add_argument(
        "--purchase-mortality-mode",
        type=str,
        choices=["no_mortality", "use_mortality"],
        default="no_mortality",
    )
    pv.set_defaults(func=cmd_vehicle_calculation)

    ploe = sub.add_parser(
        "loe-interp-compare",
        help="Compare manual retirement-age interpolation with Additional Tables multiplier.",
    )
    ploe.add_argument("--retirement-age-actual", type=float, required=True)
    ploe.add_argument("--retirement-age-lower", type=float, required=True)
    ploe.add_argument("--retirement-age-upper", type=float, required=True)
    ploe.add_argument("--multiplier-lower", type=float)
    ploe.add_argument("--multiplier-upper", type=float)
    ploe.add_argument("--multiplier-lower-csv", type=str, help="Retirement-age lower table CSV path.")
    ploe.add_argument("--multiplier-upper-csv", type=str, help="Retirement-age upper table CSV path.")
    ploe.add_argument("--discount-rate-for-manual", type=float, default=0.5)
    ploe.add_argument(
        "--additional-tables-multiplier",
        type=float,
        help="Optional Additional Tables result for side-by-side delta reporting.",
    )
    ploe.add_argument("--additional-tables-csv", type=str, help="Optional Additional Tables CSV (male/female) path.")
    ploe.add_argument("--age-at-trial", type=float, help="Required with --additional-tables-csv.")
    ploe.add_argument("--target-end-age", type=float, help="Required with --additional-tables-csv.")
    ploe.set_defaults(func=cmd_loe_interpolation_compare)

    ploe2 = sub.add_parser(
        "loe-period-compare",
        help="Compare term-certain period method vs Additional Tables period method.",
    )
    ploe2.add_argument("--age-at-trial", type=float, required=True)
    ploe2.add_argument("--start-years-from-trial", type=float, required=True)
    ploe2.add_argument("--end-years-from-trial", type=float, required=True)
    ploe2.add_argument("--start-age", type=float, required=True)
    ploe2.add_argument("--end-age", type=float, required=True)
    ploe2.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    ploe2.add_argument("--additional-tables-csv", type=str, required=True)
    ploe2.add_argument("--contingency-factor", type=float, default=1.0)
    ploe2.set_defaults(func=cmd_loe_period_compare)

    pbook = sub.add_parser(
        "loe-book-compare",
        help="Run Ogden book para 33/34 manual interpolation vs Additional Tables.",
    )
    pbook.add_argument("--claimant-age", type=float, required=True)
    pbook.add_argument("--retirement-age-actual", type=float, required=True)
    pbook.add_argument("--retirement-age-lower", type=float, required=True)
    pbook.add_argument("--retirement-age-upper", type=float, required=True)
    pbook.add_argument("--lower-table-csv", type=str, required=True)
    pbook.add_argument("--upper-table-csv", type=str, required=True)
    pbook.add_argument("--additional-tables-csv", type=str, required=True)
    pbook.add_argument("--discount-rate", type=float, default=0.5)
    pbook.set_defaults(func=cmd_loe_book_compare)

    pearn = sub.add_parser("earnings-calc", help="Run earnings calculation.")
    pearn.add_argument("--claimant-age", type=float, required=True)
    pearn.add_argument("--age-at-start", type=float, required=True)
    pearn.add_argument("--age-at-end", type=float, required=True)
    pearn.add_argument("--but-for-amount", type=float, required=True)
    pearn.add_argument("--but-for-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week"], default="Per_Year")
    pearn.add_argument("--but-for-is-net", action=argparse.BooleanOptionalAction, default=False)
    pearn.add_argument("--residual-amount", type=float, required=True)
    pearn.add_argument("--residual-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week"], default="Per_Year")
    pearn.add_argument("--residual-is-net", action=argparse.BooleanOptionalAction, default=False)
    pearn.add_argument("--employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    pearn.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    pearn.add_argument("--contingency-factor", type=float, default=0.87)
    pearn.add_argument("--multiplier-mode", type=str, choices=["auto", "manual", "additional"], default="auto")
    pearn.add_argument("--additional-tables-csv", type=str, help="Required when --multiplier-mode additional.")
    pearn.add_argument("--impairment-end-age", type=float, help="Optional impaired life end age (years old).")
    pearn.add_argument(
        "--impaired-multiplier-method",
        type=str,
        choices=["find_appropriate_age", "term_certain"],
        default="find_appropriate_age",
    )
    pearn.add_argument("--additional-tables-zero-csv", type=str, default="data/ogden8_additional_males_0.csv")
    pearn.add_argument("--additional-tables-point5-csv", type=str, default="data/ogden8_additional_males_05.csv")
    pearn.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pearn.add_argument("--discount-rate", type=float, default=0.5)
    pearn.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pearn.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    pearn.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pearn.set_defaults(func=cmd_earnings_calculation)

    pashe = sub.add_parser("earnings-ashe-calc", help="Run earnings calculation with ASHE lookup context.")
    pashe.add_argument("--claimant-age", type=float, required=True)
    pashe.add_argument("--age-at-start", type=float, required=True)
    pashe.add_argument("--age-at-end", type=float, required=True)
    pashe.add_argument("--ashe-workbook-path", type=str, required=True)
    pashe.add_argument(
        "--ashe-dataset",
        type=str,
        choices=[
            "all_workers",
            "all_male_workers",
            "all_female_workers",
            "all_full_time_workers",
            "all_part_time_workers",
            "male_full_time_workers",
            "male_part_time_workers",
            "female_full_time_workers",
            "female_part_time_workers",
        ],
        default="all_workers",
    )
    pashe.add_argument("--ashe-code", type=str, required=True, help="SOC code as shown in ASHE workbook (e.g. 111 or 9265).")
    pashe.add_argument("--ashe-region-prefix", type=str, help="Optional row prefix filter (e.g. 'North East').")
    pashe.add_argument("--but-for-amount", type=float, help="Explicit but-for earnings amount.")
    pashe.add_argument("--but-for-ashe-field", type=str, help="Use ASHE value when amount omitted: median, mean, or pXX.")
    pashe.add_argument("--but-for-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week"], default="Per_Year")
    pashe.add_argument("--but-for-is-net", action=argparse.BooleanOptionalAction, default=False)
    pashe.add_argument("--residual-amount", type=float, help="Explicit residual earnings amount.")
    pashe.add_argument("--residual-ashe-field", type=str, help="Use ASHE value when amount omitted: median, mean, or pXX.")
    pashe.add_argument("--residual-frequency", type=str, choices=["Per_Year", "Per_Month", "Per_Week"], default="Per_Year")
    pashe.add_argument("--residual-is-net", action=argparse.BooleanOptionalAction, default=False)
    pashe.add_argument("--employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    pashe.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    pashe.add_argument("--contingency-factor", type=float, default=0.87)
    pashe.add_argument("--multiplier-mode", type=str, choices=["auto", "manual", "additional"], default="auto")
    pashe.add_argument(
        "--round-final-multiplier-dp",
        type=int,
        default=2,
        help="Optional rounding precision for final multiplier before total calculation (PI-parity helper).",
    )
    pashe.add_argument(
        "--pi-round-intermediates-2dp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Round key multiplier intermediates to 2dp to mimic PI trace behavior.",
    )
    pashe.add_argument("--additional-tables-csv", type=str, help="Required when --multiplier-mode additional.")
    pashe.add_argument("--life-expectancy-end-age", type=float, help="Optional cap; age_at_end is capped to this value when lower.")
    pashe.add_argument("--discount-rate", type=float, default=0.5)
    pashe.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pashe.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    pashe.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pashe.set_defaults(func=cmd_earnings_ashe_calculation)

    pearns = sub.add_parser("earnings-split-calc", help="Run split earnings calculation.")
    pearns.add_argument("--claimant-age", type=float, required=True)
    pearns.add_argument("--period-json", default=[], action="append")
    pearns.add_argument("--period-file", type=str)
    pearns.add_argument("--employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    pearns.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    pearns.add_argument("--contingency-factor", type=float, default=0.87)
    pearns.add_argument("--multiplier-mode", type=str, choices=["auto", "manual", "additional"], default="auto")
    pearns.add_argument("--additional-tables-csv", type=str, help="Required when --multiplier-mode additional.")
    pearns.add_argument("--impairment-end-age", type=float, help="Optional impaired life end age (years old).")
    pearns.add_argument(
        "--impaired-multiplier-method",
        type=str,
        choices=["find_appropriate_age", "term_certain"],
        default="find_appropriate_age",
    )
    pearns.add_argument("--additional-tables-zero-csv", type=str, default="data/ogden8_additional_males_0.csv")
    pearns.add_argument("--additional-tables-point5-csv", type=str, default="data/ogden8_additional_males_05.csv")
    pearns.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pearns.add_argument("--discount-rate", type=float, default=0.5)
    pearns.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pearns.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    pearns.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pearns.add_argument("--require-contiguous", action=argparse.BooleanOptionalAction, default=True)
    pearns.set_defaults(func=cmd_earnings_split_calculation)

    pawa = sub.add_parser("earnings-award-calc", help="Run one-off earnings award calculation.")
    pawa.add_argument("--award-amount", type=float, required=True)
    pawa.set_defaults(func=cmd_earnings_award_calculation)

    ply = sub.add_parser("lostyears-calc", help="Run lost years multipliers calculation.")
    ply.add_argument("--claimant-age", type=float, required=True)
    ply.add_argument("--current-life-end-age", type=float, required=True)
    ply.add_argument("--but-for-remaining-life-years", type=float, required=True)
    ply.add_argument("--but-for-multiplier-method", type=str, choices=["term_certain", "find_appropriate_age"], default="term_certain")
    ply.add_argument("--but-for-age", type=float, help="Optional age lookup for FAA method. Defaults to claimant age.")
    ply.add_argument("--lost-years-rate", type=float, required=True, help="Fraction, e.g. 0.50 for 50%.")
    ply.add_argument("--contingency-factor", type=float, default=0.77)
    ply.add_argument("--earnings-period-json", default=[], action="append")
    ply.add_argument("--earnings-period-file", type=str)
    ply.add_argument("--pension-lump-sum-amount", type=float, default=0.0)
    ply.add_argument("--pension-lump-sum-age", type=float)
    ply.add_argument("--pension-annual-amount", type=float, default=0.0)
    ply.add_argument("--pension-annual-start-age", type=float)
    ply.add_argument("--pension-annual-end-age", type=float)
    ply.add_argument("--employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    ply.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    ply.add_argument("--values-are-net", action=argparse.BooleanOptionalAction, default=False)
    ply.add_argument("--discount-rate", type=float, default=0.5)
    ply.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    ply.add_argument("--additional-tables-zero-csv", type=str, default="data/ogden8_additional_males_0.csv")
    ply.add_argument("--additional-tables-point5-csv", type=str, default="data/ogden8_additional_males_05.csv")
    ply.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    ply.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    ply.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    ply.set_defaults(func=cmd_lost_years_calculation)

    ppen = sub.add_parser("pension-calc", help="Run pension multiplier calculation.")
    ppen.add_argument("--claimant-age", type=float, required=True)
    ppen.add_argument("--impairment-end-age", type=float, required=True)
    ppen.add_argument("--but-for-amount", type=float, required=True)
    ppen.add_argument("--but-for-is-net", action=argparse.BooleanOptionalAction, default=False)
    ppen.add_argument("--but-for-employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    ppen.add_argument("--residual-amount", type=float, required=True)
    ppen.add_argument("--residual-is-net", action=argparse.BooleanOptionalAction, default=False)
    ppen.add_argument("--residual-employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    ppen.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    ppen.add_argument("--multiplier-method", type=str, choices=["term_certain", "find_appropriate_age"], default="term_certain")
    ppen.add_argument("--additional-tables-zero-csv", type=str, default="data/ogden8_additional_males_0.csv")
    ppen.add_argument("--additional-tables-point5-csv", type=str, default="data/ogden8_additional_males_05.csv")
    ppen.add_argument("--discount-rate", type=float, default=0.5)
    ppen.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    ppen.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    ppen.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    ppen.set_defaults(func=cmd_pension_calculation)

    pper = sub.add_parser("pension-early-receipt-calc", help="Run pension early receipt calculation.")
    pper.add_argument("--claimant-age", type=float, required=True)
    pper.add_argument("--age-at-receipt", type=float, required=True)
    pper.add_argument("--retirement-age", type=float, default=68.0)
    pper.add_argument("--impairment-end-age", type=float, required=True)
    pper.add_argument("--expected-lump-sum", type=float, required=True)
    pper.add_argument("--actual-lump-sum", type=float, required=True)
    pper.add_argument("--expected-annual-rate", type=float, required=True)
    pper.add_argument("--expected-annual-is-net", action=argparse.BooleanOptionalAction, default=True)
    pper.add_argument("--expected-annual-employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    pper.add_argument("--actual-annual-rate", type=float, required=True)
    pper.add_argument("--actual-annual-is-net", action=argparse.BooleanOptionalAction, default=True)
    pper.add_argument("--actual-annual-employment-type", type=str, choices=["employed", "self_employed"], default="employed")
    pper.add_argument("--region", type=str, choices=["England_Wales_NI", "Scotland"], default="England_Wales_NI")
    pper.add_argument("--multiplier-method", type=str, choices=["term_certain", "find_appropriate_age"], default="term_certain")
    pper.add_argument("--additional-tables-zero-csv", type=str, default="data/ogden8_additional_males_0.csv")
    pper.add_argument("--additional-tables-point5-csv", type=str, default="data/ogden8_additional_males_05.csv")
    pper.add_argument("--discount-rate", type=float, default=0.5)
    pper.add_argument("--table35-csv", type=str, default="data/ogden8table35dr05.csv")
    pper.add_argument("--table36-csv", type=str, default="data/ogden8table36dr05.csv")
    pper.add_argument("--retirement-table-csv", type=str, default="data/tables_3-18/table_11_male_ra68.csv")
    pper.add_argument("--whole-life-csv", type=str, default="data/ogden8table1dr05.csv")
    pper.set_defaults(func=cmd_pension_early_receipt_calculation)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

