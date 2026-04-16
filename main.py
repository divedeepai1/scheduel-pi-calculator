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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone schedule calculators.")
    sub = parser.add_subparsers(dest="command", required=True)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

