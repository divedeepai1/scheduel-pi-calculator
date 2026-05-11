from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedOgdenPaths:
    whole_life_csv: str
    retirement_table_csv: str
    table35_csv: str
    table36_csv: str
    additional_tables_csv: str
    additional_tables_zero_csv: str
    additional_tables_point5_csv: str
    retirement_age_requested: float
    retirement_age_effective: float
    retirement_table_csv_lower: str
    retirement_table_csv_upper: str
    retirement_interpolation_weight: float
    # Optional informational warnings for the caller (UI/CLI) to surface.
    warning: str | None = None


def resolve_ogden_paths(
    *,
    gender: str,
    discount_rate: float,
    retirement_age: int = 68,
) -> ResolvedOgdenPaths:
    g = "male" if str(gender).lower() == "male" else "female"

    warning: str | None = None
    if abs(float(discount_rate) - 0.5) > 1e-9:
        warning = "Only 0.5% table files are bundled right now. Falling back to 0.5% table files."

    whole_life_csv = "data/ogden8table1dr05.csv" if g == "male" else "data/ogden8table2dr05.csv"

    retirement_table_map = {
        ("male", 50): "data/tables_3-18/table_3_male_ra50.csv",
        ("female", 50): "data/tables_3-18/table_4_female_ra50.csv",
        ("male", 55): "data/tables_3-18/table_5_male_ra55.csv",
        ("female", 55): "data/tables_3-18/table_6_female_ra55.csv",
        ("male", 60): "data/tables_3-18/table_7_male_ra60.csv",
        ("female", 60): "data/tables_3-18/table_8_female_ra60.csv",
        ("male", 65): "data/tables_3-18/table_9_male_ra65.csv",
        ("female", 65): "data/tables_3-18/table_10_female_ra65.csv",
        ("male", 68): "data/tables_3-18/table_11_male_ra68.csv",
        ("female", 68): "data/tables_3-18/table_12_female_ra68.csv",
        ("male", 70): "data/tables_3-18/table_13_male_ra70.csv",
        ("female", 70): "data/tables_3-18/table_14_female_ra70.csv",
        ("male", 75): "data/tables_3-18/table_15_male_ra75.csv",
        ("female", 75): "data/tables_3-18/table_16_female_ra75.csv",
        ("male", 80): "data/tables_3-18/table_17_male_ra80.csv",
        ("female", 80): "data/tables_3-18/table_18_female_ra80.csv",
    }
    supported = [50, 55, 60, 65, 68, 70, 75, 80]
    requested_ra = float(retirement_age)
    key_exact = (g, int(round(requested_ra)))
    if abs(requested_ra - round(requested_ra)) < 1e-9 and key_exact in retirement_table_map:
        retirement_table_csv = retirement_table_map[key_exact]
        lower_ra = upper_ra = float(int(round(requested_ra)))
        lower_csv = upper_csv = retirement_table_csv
        interp_weight = 0.0
        effective_ra = requested_ra
    else:
        lower = max([x for x in supported if x <= requested_ra], default=None)
        upper = min([x for x in supported if x >= requested_ra], default=None)
        if lower is None or upper is None:
            nearest = min(supported, key=lambda x: abs(x - requested_ra))
            msg = (
                f"Retirement age {retirement_age} is outside supported range "
                f"({supported[0]}-{supported[-1]}). Falling back to nearest supported table: {nearest}."
            )
            warning = f"{warning}\n{msg}" if warning else msg
            retirement_table_csv = retirement_table_map[(g, nearest)]
            lower_ra = upper_ra = float(nearest)
            lower_csv = upper_csv = retirement_table_csv
            interp_weight = 0.0
            effective_ra = float(nearest)
        elif lower == upper:
            retirement_table_csv = retirement_table_map[(g, lower)]
            lower_ra = upper_ra = float(lower)
            lower_csv = upper_csv = retirement_table_csv
            interp_weight = 0.0
            effective_ra = requested_ra
        else:
            lower_csv = retirement_table_map[(g, lower)]
            upper_csv = retirement_table_map[(g, upper)]
            retirement_table_csv = lower_csv
            interp_weight = (requested_ra - float(lower)) / (float(upper) - float(lower))
            lower_ra = float(lower)
            upper_ra = float(upper)
            effective_ra = requested_ra
            msg = (
                f"Retirement age {retirement_age} does not have a bundled table. "
                f"Using interpolated retirement table between {lower} and {upper} (weight={interp_weight:.6f})."
            )
            warning = f"{warning}\n{msg}" if warning else msg

    return ResolvedOgdenPaths(
        whole_life_csv=whole_life_csv,
        retirement_table_csv=retirement_table_csv,
        table35_csv="data/ogden8table35dr05.csv",
        table36_csv="data/ogden8table36dr05.csv",
        additional_tables_csv="data/additional_male05.csv" if g == "male" else "data/additional_female05.csv",
        additional_tables_zero_csv="data/ogden8_additional_males_0.csv" if g == "male" else "data/ogden8_additional_females_0.csv",
        additional_tables_point5_csv="data/ogden8_additional_males_05.csv" if g == "male" else "data/ogden8_additional_females_05.csv",
        retirement_age_requested=requested_ra,
        retirement_age_effective=effective_ra,
        retirement_table_csv_lower=lower_csv,
        retirement_table_csv_upper=upper_csv,
        retirement_interpolation_weight=interp_weight,
        warning=warning,
    )

