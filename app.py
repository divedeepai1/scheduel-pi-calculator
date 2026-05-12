import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st
from formulas.ashe_loader import load_ashe_row, load_ashe_row_by_prefix

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
    EarningsCalculation,
    EarningsAsheCalculation,
    ashe_table_labels,
    resolve_ashe_workbook_path,
    EarningsSplitCalculation,
    EarningsAwardCalculation,
    LostYearsCalculation,
    PensionCalculation,
    PensionEarlyReceiptCalculation,
    AccommodationRvJCalculation,
    AccommodationSwiftCarpenterCalculation,
)
from formulas.table_resolver import resolve_ogden_paths
from formulas.contingency_lookup import lookup_contingency
from formulas.loss_of_earnings_interpolation import LossOfEarningsInterpolation

SUCCESS_MSG = "Calculated successfully."
DATE_MIN = date(1900, 1, 1)
DATE_MAX = date(2100, 12, 31)


def _decimal_age_years(dob: date, as_of: date) -> float:
    if as_of < dob:
        raise ValueError("Calculation date cannot be earlier than DOB.")
    # PI-like decimal age behavior aligns closely with an ACT/365.25 basis.
    return (as_of - dob).days / 365.25


def _load_table36_vector(csv_path: str) -> List[float]:
    vector: List[float] = []
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
        raise ValueError(f"No numeric Table 36 values found in {csv_path}.")
    return vector


def _load_whole_life_table(csv_path: str) -> List[Tuple[float, float]]:
    table: List[Tuple[float, float]] = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            try:
                table.append((float(row[0]), float(row[1])))
            except (TypeError, ValueError, IndexError):
                continue
    if not table:
        raise ValueError(f"No usable [age, multiplier] rows found in {csv_path}.")
    return table


def _load_retirement_table_for_paths(paths, discount_rate: float) -> List[Tuple[float, float]]:
    lower_csv = getattr(paths, "retirement_table_csv_lower", paths.retirement_table_csv)
    upper_csv = getattr(paths, "retirement_table_csv_upper", paths.retirement_table_csv)
    w = float(getattr(paths, "retirement_interpolation_weight", 0.0))
    if lower_csv == upper_csv or w <= 1e-12:
        return EarningsCalculation.load_retirement_table(paths.retirement_table_csv, discount_rate)
    requested_ra = float(getattr(paths, "retirement_age_requested"))
    lower_ra = float(getattr(paths, "retirement_age_effective"))  # fallback value
    upper_ra = float(getattr(paths, "retirement_age_effective"))  # fallback value
    # Derive bracket retirement ages from filenames if present in resolver metadata.
    try:
        lower_ra = float(str(lower_csv).split("_ra")[-1].split(".")[0])
        upper_ra = float(str(upper_csv).split("_ra")[-1].split(".")[0])
    except Exception:
        pass
    if abs(upper_ra - lower_ra) < 1e-9:
        return EarningsCalculation.load_retirement_table(paths.retirement_table_csv, discount_rate)

    interp = LossOfEarningsInterpolation()
    lower_tbl = EarningsCalculation.load_retirement_table(lower_csv, discount_rate)
    upper_tbl = EarningsCalculation.load_retirement_table(upper_csv, discount_rate)
    min_age = int(max(lower_tbl[0][0], upper_tbl[0][0]))
    max_age = int(round(requested_ra)) - 1
    if max_age < min_age:
        max_age = min_age

    blended: List[Tuple[float, float]] = []
    for age in range(min_age, max_age + 1):
        age_for_lower = float(age) + lower_ra - requested_ra
        age_for_upper = float(age) + upper_ra - requested_ra
        m = interp.multiplier_from_retirement_table_csv(lower_csv, age_for_lower, discount_rate)
        n = interp.multiplier_from_retirement_table_csv(upper_csv, age_for_upper, discount_rate)
        mult = (((upper_ra - requested_ra) * m) + ((requested_ra - lower_ra) * n)) / (upper_ra - lower_ra)
        blended.append((float(age), float(mult)))
    return blended


def _show_tables_used(title: str, paths) -> None:
    with st.expander(title, expanded=False):
        st.write(f"Whole life: `{paths.whole_life_csv}`")
        st.write(f"Retirement table: `{paths.retirement_table_csv}`")
        lower_csv = getattr(paths, "retirement_table_csv_lower", paths.retirement_table_csv)
        upper_csv = getattr(paths, "retirement_table_csv_upper", paths.retirement_table_csv)
        w = float(getattr(paths, "retirement_interpolation_weight", 0.0))
        if lower_csv != upper_csv and w > 1e-12:
            st.write(f"Retirement interpolation lower: `{lower_csv}`")
            st.write(f"Retirement interpolation upper: `{upper_csv}`")
            st.write(f"Retirement interpolation weight: `{w:.6f}`")
        st.write(f"Table35: `{paths.table35_csv}`")
        st.write(f"Table36: `{paths.table36_csv}`")
        st.write(f"Additional tables (+0.5): `{paths.additional_tables_csv}`")
        st.write(f"Additional tables (0%): `{paths.additional_tables_zero_csv}`")
        st.write(f"Additional tables (+0.5 full): `{paths.additional_tables_point5_csv}`")


def _resolve_ashe_table14_workbook_path(year: int, table_label: str, cv_variant: bool = False) -> str:
    if int(year) != 2025:
        raise ValueError("Only ASHE year 2025 is currently bundled in local data.")
    labels = ashe_table_labels()
    idx = {lbl.strip().lower(): i + 1 for i, lbl in enumerate(labels)}
    code_num = idx.get(str(table_label).strip().lower())
    if code_num is None:
        raise ValueError(f"Unsupported ASHE table '{table_label}'.")
    suffix = "b" if cv_variant else "a"
    cv_part = " CV" if cv_variant else ""
    file_name = f"PROV - Occupation SOC20 (4) Table 14.{code_num}{suffix}   {table_label} 2025{cv_part}.xlsx"
    path = Path("data") / "ashetable142025provisional" / file_name
    if not path.exists():
        raise ValueError(f"Resolved ASHE Table 14 workbook was not found: {path}")
    return str(path).replace("\\", "/")


def _base_inputs(key_prefix: str) -> Dict[str, float]:
    is_claim_defaults = key_prefix == "claim"
    default_rate_value = 16.62 if is_claim_defaults else 12.69
    default_rate_index = 0 if is_claim_defaults else 1
    col1, col2, col3 = st.columns(3)
    with col1:
        number_of_hours = st.number_input(
            "Time (Hrs)", value=20.0, min_value=0.0, step=1.0, key=f"{key_prefix}_hours"
        )
        percentage_less = st.number_input(
            "Less (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f"{key_prefix}_less"
        )
    with col2:
        time_increment_display = {
            "Over_Period": "Over period",
            "Per_Day": "per Day",
            "Per_Week": "per Week",
            "Per_Month": "per Month",
            "Per_Year": "per Year",
            "Per_Weekday": "per Weekday",
            "Per_Weekend": "per Weekend",
            "Per_Monday": "per Monday",
            "Per_Tuesday": "per Tuesday",
            "Per_Wednesday": "per Wednesday",
            "Per_Thursday": "per Thursday",
            "Per_Friday": "per Friday",
            "Per_Saturday": "per Saturday",
            "Per_Sunday": "per Sunday",
            "Per_Day_Specify": "per Day (specify)",
            "Per_Week_Specify": "per Week (specify)",
            "Per_Month_Specify": "per Month (specify)",
            "Per_Weekday_Specify": "per Weekday (specify)",
            "Per_Weekend_Specify": "per Weekend (specify)",
        }
        time_increment = st.selectbox(
            "Time frequency",
            list(time_increment_display.keys()),
            index=2,  # default to Per_Week
            key=f"{key_prefix}_time_increment",
            format_func=lambda v: time_increment_display.get(v, v),
        )
        rate_type_display = {
            "Aggregate_Rate": "Aggregate Rate",
            "Basic_Rate": "Basic Rate",
            "Evening_Rate": "Evening Rate",
            "Weekend_Rate": "Weekend Rate",
            "Saturday_Rate": "Saturday Rate",
            "Sunday_Rate": "Sunday Rate",
            "Aggregate_Day_Rate": "Aggregate Day Rate",
            "Specify_Rate": "Specify Own Rate",
        }
        care_rate_type = st.selectbox(
            "Rate to Use",
            list(rate_type_display.keys()),
            index=default_rate_index,
            key=f"{key_prefix}_care_rate_type",
            format_func=lambda v: rate_type_display.get(v, v),
        )
    with col3:
        rate_value = st.number_input(
            "Rate to Use", value=default_rate_value, min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_rate_value"
        )
        include_public_holidays = st.checkbox(
            "Include Public Holidays", value=True, key=f"{key_prefix}_include_holidays"
        )
        public_holidays_per_year = st.number_input(
            "Public Holidays / Year",
            value=8.0,
            min_value=0.0,
            step=1.0,
            format="%.1f",
            key=f"{key_prefix}_holidays_per_year",
        )

    specify_increment = None
    number_days_specify = None
    number_weeks_specify = None
    number_months_specify = None

    if "Specify" in time_increment:
        specify_increment = st.selectbox(
            "Frequency for Periods",
            ["Over_Period_Specify", "Per_Week_Specify", "Per_Month_Specify", "Per_Year_Specify"],
            key=f"{key_prefix}_specify_increment",
            format_func=lambda v: {
                "Over_Period_Specify": "Over period",
                "Per_Week_Specify": "Per Week",
                "Per_Month_Specify": "Per Month",
                "Per_Year_Specify": "Per Year",
            }.get(v, v),
        )
        if time_increment == "Per_Day_Specify":
            number_days_specify = st.number_input(
                "Periods: Days",
                value=1.0,
                min_value=0.0,
                step=1.0,
                key=f"{key_prefix}_days_specify",
            )
        if time_increment in {"Per_Week_Specify", "Per_Weekday_Specify", "Per_Weekend_Specify"}:
            number_weeks_specify = st.number_input(
                "Periods: Weeks",
                value=1.0,
                min_value=0.0,
                step=1.0,
                key=f"{key_prefix}_weeks_specify",
            )
        if time_increment == "Per_Month_Specify":
            number_months_specify = st.number_input(
                "Periods: Months",
                value=1.0,
                min_value=0.0,
                step=1.0,
                key=f"{key_prefix}_months_specify",
            )

    rate_values: Dict[str, float] = {}
    manual_rate = None
    if care_rate_type == "Specify_Rate":
        manual_rate = rate_value
    else:
        rate_values[care_rate_type] = rate_value

    return {
        "number_of_hours": number_of_hours,
        "time_increment": time_increment,
        "care_rate_type": care_rate_type,
        "rate_values": rate_values,
        "manual_rate": manual_rate,
        "percentage_less": percentage_less,
        "specify_increment": specify_increment,
        "number_days_specify": number_days_specify,
        "number_weeks_specify": number_weeks_specify,
        "number_months_specify": number_months_specify,
        "include_public_holidays": include_public_holidays,
        "public_holidays_per_year": public_holidays_per_year,
    }


def _render_trace(trace: List[str]) -> None:
    if not trace:
        return
    st.subheader("Calculation Trace")
    st.code("\n".join(trace))


def _date_input(label: str, **kwargs):
    if "min_value" not in kwargs:
        kwargs["min_value"] = DATE_MIN
    if "max_value" not in kwargs:
        kwargs["max_value"] = DATE_MAX
    return st.date_input(label, **kwargs)


@st.cache_data(show_spinner=False)
def _load_ashe_code_options(json_path: str) -> List[Dict[str, str]]:
    with open(json_path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError("ASHE code JSON must contain a list.")
    out: List[Dict[str, str]] = []
    for row in rows:
        code = str(row.get("code", "")).strip()
        profession = str(row.get("profession", "")).strip()
        label = str(row.get("label", "")).strip() or f"{code} - {profession}"
        if code and profession:
            out.append({"code": code, "profession": profession, "label": label})
    if not out:
        raise ValueError("No usable ASHE code options found in JSON.")
    return out


@st.cache_data(show_spinner=False)
def _load_ashe_pi_code_options(json_path: str) -> List[Dict[str, str]]:
    unit_rows = _load_ashe_code_options(json_path)
    major_labels = {
        "1": "Managers, directors and senior officials",
        "2": "Professional occupations",
        "3": "Associate professional occupations",
        "4": "Administrative and secretarial occupations",
        "5": "Skilled trades occupations",
        "6": "Caring, leisure and other service occupations",
        "7": "Sales and customer service occupations",
        "8": "Process, plant and machine operatives",
        "9": "Elementary occupations",
    }
    sub_major_labels = {
        "11": "Corporate managers and directors",
        "12": "Other managers and proprietors",
        "21": "Science, research, engineering and technology professionals",
        "22": "Health professionals",
        "23": "Teaching and educational professionals",
        "24": "Business, media and public service professionals",
        "31": "Science, engineering and technology associate professionals",
        "32": "Health and social care associate professionals",
        "33": "Protective service occupations",
        "34": "Culture, media and sports occupations",
        "35": "Business and public service associate professionals",
    }

    out: List[Dict[str, str]] = []
    for code, label in major_labels.items():
        out.append({"code": code, "profession": label, "label": f"{code} - {label}"})

    existing_units = {str(r["code"]).strip() for r in unit_rows}
    for code, label in sub_major_labels.items():
        if any(u.startswith(code) for u in existing_units):
            out.append({"code": code, "profession": label, "label": f"{code} - {label}"})

    for row in unit_rows:
        out.append({"code": row["code"], "profession": row["profession"], "label": row["label"]})
    return out


st.set_page_config(page_title="Scheduel Calculator", layout="wide")
st.title("Scheduel Calculator")
st.caption("Streamlit interface for implemented PI-style calculation functions.")

selected_function = st.sidebar.selectbox(
    "Select Function",
    [
        "Continuous Multiplier (CM)",
        "General Continuous (GC)",
        "General Continuous (But For) (GCBF)",
        "General One Off (GOF)",
        "General Periodical (GP)",
        "Lifetime (Split) (LS)",
        "Periodical Multiplier (PM)",
        "Care Annualisation",
        "Care Claim (Full)",
        "Care (Split)",
        "Equipment",
        "Travel Claim (Full)",
        "Vehicle",
        "Employment Settings (Test)",
        "Earnings",
        "Earnings (ASHE)",
        "ASHE Lookup (Test)",
        "Earnings (Split)",
        "Earnings Award",
        "Lost Years",
        "Pension",
        "Pension (Early receipt)",
        "Accommodation (RvJ)",
        "Accommodation (Swift v Carpenter)",
    ],
    index=0,
    key="function_selector",
)

if selected_function == "Employment Settings (Test)":
    st.subheader("Employment Settings (Test)")
    st.caption("PI-style before/after employment profile inputs for contingency testing.")

    st.markdown("#### Global Context")
    g1, g2 = st.columns(2)
    with g1:
        dob = _date_input("DOB", value=date(1980, 4, 23), key="est_dob")
        calculation_date = _date_input("Calculation Date", value=date(2025, 9, 16), key="est_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="est_gender")
        st.caption("Gender is included for future parity but does not currently affect contingency lookup.")

    claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
    st.caption(f"Derived Claimant Age: {claimant_age:.2f}")

    st.markdown("#### Employment Settings")
    bcol, acol = st.columns(2)
    with bcol:
        st.markdown("**Before injury**")
        ws_before = st.selectbox(
            "Working Status",
            ["Working Employed", "Working Unemployed", "Not Started Career", "Retired"],
            index=0,
            key="est_ws_before",
        )
        age_start_before = None
        if ws_before == "Not Started Career":
            age_start_before = st.number_input(
                "Age to Start Working",
                value=max(16.0, float(claimant_age + 2.0)),
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="est_age_start_before",
            )
        retirement_mode_before = st.selectbox(
            "Retirement Age",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="est_ret_mode_before",
        )
        retirement_age_before = 68.0
        if retirement_mode_before == "Specify retirement age":
            retirement_age_before = st.number_input(
                "Specified Retirement Age",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="est_ret_age_before",
            )
        edu_before = st.selectbox("Education Level", ["Level 3", "Level 2", "Level 1"], index=1, key="est_edu_before")
        dis_before = st.selectbox("Disability", ["Not Disabled", "Disabled"], index=0, key="est_dis_before")

    with acol:
        st.markdown("**As a result of injury**")
        ws_after = st.selectbox(
            "Working Status",
            ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"],
            index=1,
            key="est_ws_after",
        )
        age_start_after = None
        if ws_after == "Not Started Career":
            age_start_after = st.number_input(
                "Age to Start Working",
                value=max(16.0, float(claimant_age + 2.0)),
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="est_age_start_after",
            )
        retirement_mode_after = st.selectbox(
            "Retirement Age",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="est_ret_mode_after",
        )
        retirement_age_after = 68.0
        if retirement_mode_after == "Specify retirement age":
            retirement_age_after = st.number_input(
                "Specified Retirement Age",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="est_ret_age_after",
            )
        edu_after = st.selectbox("Education Level", ["Level 3", "Level 2", "Level 1"], index=1, key="est_edu_after")
        dis_after = st.selectbox("Disability", ["Not Disabled", "Disabled"], index=0, key="est_dis_after")

    cont_before = lookup_contingency(
        working_status=str(ws_before),
        education_level=str(edu_before),
        disability=str(dis_before),
        age_to_start_working=age_start_before,
        claimant_age=float(claimant_age),
        gender=str(gender),
        retirement_age=float(retirement_age_before),
    )
    cont_after = lookup_contingency(
        working_status=str(ws_after),
        education_level=str(edu_after),
        disability=str(dis_after),
        age_to_start_working=age_start_after,
        claimant_age=float(claimant_age),
        gender=str(gender),
        retirement_age=float(retirement_age_after),
    )

    st.markdown("#### Contingency Outputs")
    o1, o2 = st.columns(2)
    with o1:
        st.write(f"Calculated Contingency (Before Injury): {cont_before:.4f}")
        cont_before_override = st.number_input(
            "Override Contingency (Before Injury)",
            value=float(cont_before),
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="est_cont_before_override",
        )
    with o2:
        st.write(f"Calculated Contingency (As Result): {cont_after:.4f}")
        cont_after_override = st.number_input(
            "Override Contingency (As Result)",
            value=float(cont_after),
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="est_cont_after_override",
        )

    st.markdown("#### Snapshot")
    st.json(
        {
            "claimant_age": round(float(claimant_age), 8),
            "before_injury": {
                "working_status": ws_before,
                "age_to_start_working": age_start_before,
                "retirement_mode": retirement_mode_before,
                "retirement_age_effective": retirement_age_before,
                "education_level": edu_before,
                "disability": dis_before,
                "contingency_calculated": round(float(cont_before), 8),
                "contingency_override": round(float(cont_before_override), 8),
            },
            "as_result_of_injury": {
                "working_status": ws_after,
                "age_to_start_working": age_start_after,
                "retirement_mode": retirement_mode_after,
                "retirement_age_effective": retirement_age_after,
                "education_level": edu_after,
                "disability": dis_after,
                "contingency_calculated": round(float(cont_after), 8),
                "contingency_override": round(float(cont_after_override), 8),
            },
        }
    )

elif selected_function == "Continuous Multiplier (CM)":
    st.subheader("Continuous Multiplier (CM)")
    st.caption("PI-style CM using Table 36 apportionment.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    impaired_end_age = None
    years_reduction = None
    derived_life_expectancy_end_age = None
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="cm_le_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input(
                "Claimant Age",
                value=65.68,
                step=0.01,
                format="%.2f",
                key="cm_claimant_age",
            )
        else:
            dob = _date_input(
                "DOB",
                value=date(1960, 7, 7),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="cm_dob",
            )
            calculation_date = _date_input(
                "Calculation Date",
                value=date(2026, 3, 13),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="cm_calc_date",
            )

    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="cm_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="cm_le_basis",
            )
            if life_expectancy_basis != "standard":
                impairment_input_type = st.selectbox(
                    "Impairment Input Type",
                    ["end_age", "years_reduction"],
                    index=0,
                    key="cm_impairment_type",
                )
                if impairment_input_type == "end_age":
                    impaired_end_age = st.number_input(
                        "Impaired End Age",
                        value=80.00,
                        step=0.01,
                        format="%.2f",
                        key="cm_impaired_end_age",
                    )
                else:
                    years_reduction = st.number_input(
                        "Years Reduction",
                        value=4.69,
                        step=0.01,
                        format="%.2f",
                        key="cm_years_reduction",
                    )
        else:
            life_expectancy_years = st.number_input(
                "Life Expectancy Years",
                value=19.67,
                step=0.01,
                format="%.2f",
                key="cm_le_years",
            )

    with g3:
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)",
            value=0.0,
            step=0.0001,
            format="%.4f",
            key="cm_life_mult_override",
        )

    st.markdown("#### Loss Configuration")
    c1, c2 = st.columns(2)
    with c1:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="cm_start_mode")
        start_age = st.number_input("Start Age", value=66.00, step=0.01, format="%.2f", key="cm_start_age", disabled=(start_mode == "Age at Calculation"))
    with c2:
        end_mode = st.selectbox("End Date / Age of Loss", ["Rest of Life", "Specific Age"], index=0, key="cm_end_mode")
        end_age = st.number_input("End Age", value=80.00, step=0.01, format="%.2f", key="cm_end_age", disabled=(end_mode == "Rest of Life"))

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="cm_table36_csv")
    male_whole_life_csv = st.text_input("Male Whole Life CSV", value=str(paths.whole_life_csv), key="cm_male_whole_csv")
    female_paths = resolve_ogden_paths(gender="female", discount_rate=0.5, retirement_age=68)
    female_whole_life_csv = st.text_input("Female Whole Life CSV", value=str(female_paths.whole_life_csv), key="cm_female_whole_csv")

    if st.button("Compute Continuous Multiplier", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    effective_life_expectancy_years = float(standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if impaired_end_age is not None:
                        effective_life_expectancy_years = float(impaired_end_age) - float(calculation_age)
                    else:
                        effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction or 0.0)
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Impaired life expectancy years must be greater than 0.")
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=effective_life_expectancy_years,
                    )
                derived_life_expectancy_end_age = float(calculation_age + effective_life_expectancy_years)
                life_expectancy_age = float(derived_life_expectancy_end_age)
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table(male_whole_life_csv),
                        female_table=_load_whole_life_table(female_whole_life_csv),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            calc = ContinuousMultiplierCalculation(table36_vector=_load_table36_vector(table36_csv))
            result = calc.calculate(
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                end_age=(None if end_mode == "Rest of Life" else float(end_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
                end_at_rest_of_life=(end_mode == "Rest of Life"),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Life Multiplier: {result['life_multiplier']:.8f}")
            st.write(f"Term Multiplier Start: {result['term_multiplier_start']:.8f}")
            st.write(f"Term Multiplier End: {result['term_multiplier_end']:.8f}")
            st.write(f"Life Term Multiplier: {result['term_multiplier_life_expectancy']:.8f}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Calculation Age (derived): {result['calculation_age']:.8f}")
            st.write(f"Life Expectancy Age (derived): {result['life_expectancy_age']:.8f}")
            if le_input_mode == "derived_from_dates":
                st.write(f"Life Expectancy Years (derived): {result['life_expectancy_years']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Care Annualisation":
    st.subheader("Care Annualisation")
    mode = st.radio("Period Input Mode", ["Age", "Date"], horizontal=True)
    if mode == "Age":
        c1, c2 = st.columns(2)
        with c1:
            age_at_start = st.number_input("Age at Start", value=67.0, step=0.01, format="%.2f")
        with c2:
            age_at_end = st.number_input("Age at End", value=80.0, step=0.01, format="%.2f")
        start_date = None
        end_date = None
    else:
        c1, c2 = st.columns(2)
        with c1:
            start_date = str(_date_input("Start Date"))
        with c2:
            end_date = str(_date_input("End Date"))
        age_at_start = None
        age_at_end = None

    payload = _base_inputs("annual")
    if st.button("Compute Care Annualisation", use_container_width=True):
        try:
            calc = CareCalculation()
            result = calc.calculate(
                age_at_start=age_at_start,
                age_at_end=age_at_end,
                start_date=start_date,
                end_date=end_date,
                number_of_hours=float(payload["number_of_hours"]),
                time_increment=str(payload["time_increment"]),
                care_rate_type=str(payload["care_rate_type"]),
                rate_values=payload["rate_values"],
                percentage_less=float(payload["percentage_less"]),
                manual_rate=payload["manual_rate"],
                specify_increment=payload["specify_increment"],
                number_days_specify=payload["number_days_specify"],
                number_weeks_specify=payload["number_weeks_specify"],
                number_months_specify=payload["number_months_specify"],
                include_public_holidays=bool(payload["include_public_holidays"]),
                public_holidays_per_year=float(payload["public_holidays_per_year"]),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Period Years: {result['period_years']:.8f}")
            st.write(f"Annualised Hours: {result['annualised_hours']:.8f}")
            st.write(f"Effective Rate: {result['effective_rate']:.8f}")
            st.write(f"Annualised Cost: {result['annualised_cost']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "General Continuous (GC)":
    st.subheader("General Continuous (GC)")
    st.caption("Annualised loss multiplied by CM period multiplier.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    impaired_end_age = None
    years_reduction = None
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="gc_le_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="gc_claimant_age")
        else:
            dob = _date_input(
                "DOB",
                value=date(1960, 7, 7),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gc_dob",
            )
            calculation_date = _date_input(
                "Calculation Date",
                value=date(2026, 3, 13),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gc_calc_date",
            )
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="gc_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="gc_le_basis")
            if life_expectancy_basis != "standard":
                impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="gc_imp_type")
                if impairment_input_type == "end_age":
                    impaired_end_age = st.number_input("Impaired End Age", value=80.00, step=0.01, format="%.2f", key="gc_imp_end")
                else:
                    years_reduction = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="gc_years_reduction")
        else:
            life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f", key="gc_le_years")
    with g3:
        life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="gc_lm_override")

    st.markdown("#### Loss Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        loss_amount = st.number_input("Loss Amount", value=1000.0, min_value=0.0, step=100.0, key="gc_loss")
        loss_frequency = st.selectbox("Loss Frequency", ["Per_Year", "Per_Month", "Per_Week", "Per_Day"], index=0, key="gc_freq")
    with c2:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="gc_start_mode")
        start_age = st.number_input("Start Age", value=67.0, step=0.01, format="%.2f", key="gc_start_age", disabled=(start_mode == "Age at Calculation"))
    with c3:
        end_mode = st.selectbox("End Date / Age of Loss", ["Rest of Life", "Specific Age"], index=0, key="gc_end_mode")
        end_age = st.number_input("End Age", value=85.0, step=0.01, format="%.2f", key="gc_end_age", disabled=(end_mode == "Rest of Life"))

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="gc_table36_csv")
    male_whole_life_csv = st.text_input("Male Whole Life CSV", value=str(paths.whole_life_csv), key="gc_male_whole_csv")
    female_paths = resolve_ogden_paths(gender="female", discount_rate=0.5, retirement_age=68)
    female_whole_life_csv = st.text_input("Female Whole Life CSV", value=str(female_paths.whole_life_csv), key="gc_female_whole_csv")

    if st.button("Compute General Continuous", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    effective_life_expectancy_years = float(standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if impaired_end_age is not None:
                        effective_life_expectancy_years = float(impaired_end_age) - float(calculation_age)
                    else:
                        effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction or 0.0)
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Impaired life expectancy years must be greater than 0.")
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=effective_life_expectancy_years,
                    )
                life_expectancy_age = float(calculation_age + effective_life_expectancy_years)
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table(male_whole_life_csv),
                        female_table=_load_whole_life_table(female_whole_life_csv),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            cm_calc = ContinuousMultiplierCalculation(table36_vector=_load_table36_vector(table36_csv))
            gc_calc = GeneralContinuousCalculation(cm_calculation=cm_calc)
            result = gc_calc.calculate(
                loss_amount=float(loss_amount),
                loss_frequency=str(loss_frequency),
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                end_age=(None if end_mode == "Rest of Life" else float(end_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
                end_at_rest_of_life=(end_mode == "Rest of Life"),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Annual Loss: {result['annual_loss']:.8f}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Total: {result['total']:.8f}")
            st.write(f"Calculation Age (derived): {calculation_age:.8f}")
            st.write(f"Life Expectancy Age (derived): {life_expectancy_age:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "General Continuous (But For) (GCBF)":
    st.subheader("General Continuous (But For) (GCBF)")
    st.caption("Net annual differential (result - prior) multiplied by CM period multiplier.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    impaired_end_age = None
    years_reduction = None
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="gcbf_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="gcbf_claimant_age")
        else:
            dob = _date_input(
                "DOB",
                value=date(1960, 7, 7),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gcbf_dob",
            )
            calculation_date = _date_input(
                "Calculation Date",
                value=date(2026, 3, 13),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gcbf_calc_date",
            )
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="gcbf_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="gcbf_le_basis")
            if life_expectancy_basis != "standard":
                impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="gcbf_imp_type")
                if impairment_input_type == "end_age":
                    impaired_end_age = st.number_input("Impaired End Age", value=80.00, step=0.01, format="%.2f", key="gcbf_imp_end")
                else:
                    years_reduction = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="gcbf_years_reduction")
        else:
            life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f", key="gcbf_le_years")
    with g3:
        life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="gcbf_lm_override")

    st.markdown("#### Loss Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        cost_prior = st.number_input("Cost Prior", value=500.0, min_value=0.0, step=100.0, key="gcbf_prior")
        cost_prior_freq = st.selectbox("Cost Prior Frequency", ["Per_Year", "Per_Month", "Per_Week", "Per_Day"], index=1, key="gcbf_prior_freq")
    with c2:
        cost_result = st.number_input("Cost As Result", value=1000.0, min_value=0.0, step=100.0, key="gcbf_result")
        cost_result_freq = st.selectbox("Cost As Result Frequency", ["Per_Year", "Per_Month", "Per_Week", "Per_Day"], index=1, key="gcbf_result_freq")
    with c3:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="gcbf_start_mode")
        start_age = st.number_input("Start Age", value=67.0, step=0.01, format="%.2f", key="gcbf_start_age", disabled=(start_mode == "Age at Calculation"))
        end_mode = st.selectbox("End Date / Age of Loss", ["Rest of Life", "Specific Age"], index=0, key="gcbf_end_mode")
        end_age = st.number_input("End Age", value=80.0, step=0.01, format="%.2f", key="gcbf_end_age", disabled=(end_mode == "Rest of Life"))

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="gcbf_table36_csv")
    male_whole_life_csv = st.text_input("Male Whole Life CSV", value=str(paths.whole_life_csv), key="gcbf_male_whole_csv")
    female_paths = resolve_ogden_paths(gender="female", discount_rate=0.5, retirement_age=68)
    female_whole_life_csv = st.text_input("Female Whole Life CSV", value=str(female_paths.whole_life_csv), key="gcbf_female_whole_csv")

    if st.button("Compute General Continuous (But For)", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    effective_life_expectancy_years = float(standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if impaired_end_age is not None:
                        effective_life_expectancy_years = float(impaired_end_age) - float(calculation_age)
                    else:
                        effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction or 0.0)
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Impaired life expectancy years must be greater than 0.")
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=effective_life_expectancy_years,
                    )
                life_expectancy_age = float(calculation_age + effective_life_expectancy_years)
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table(male_whole_life_csv),
                        female_table=_load_whole_life_table(female_whole_life_csv),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            cm_calc = ContinuousMultiplierCalculation(table36_vector=_load_table36_vector(table36_csv))
            gcbf_calc = GeneralContinuousButForCalculation(cm_calculation=cm_calc)
            result = gcbf_calc.calculate(
                cost_prior=float(cost_prior),
                cost_prior_frequency=str(cost_prior_freq),
                cost_result=float(cost_result),
                cost_result_frequency=str(cost_result_freq),
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                end_age=(None if end_mode == "Rest of Life" else float(end_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
                end_at_rest_of_life=(end_mode == "Rest of Life"),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Annual Prior: {result['annual_prior']:.8f}")
            st.write(f"Annual Result: {result['annual_result']:.8f}")
            st.write(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Total: {result['total']:.8f}")
            st.write(f"Calculation Age (derived): {calculation_age:.8f}")
            st.write(f"Life Expectancy Age (derived): {life_expectancy_age:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "General One Off (GOF)":
    st.subheader("General One Off (GOF)")
    st.caption("Single future loss discounted using Table 35.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="gof_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="gof_claimant_age")
        else:
            dob = _date_input(
                "DOB",
                value=date(1960, 7, 7),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gof_dob",
            )
            calculation_date = _date_input(
                "Calculation Date",
                value=date(2026, 3, 13),
                min_value=date(1900, 1, 1),
                max_value=date(2100, 12, 31),
                key="gof_calc_date",
            )
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="gof_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="gof_le_basis")
            if life_expectancy_basis == "impaired":
                impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="gof_imp_type")
                if impairment_input_type == "end_age":
                    _ = st.number_input("Impaired End Age", value=80.00, step=0.01, format="%.2f", key="gof_imp_end")
                else:
                    _ = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="gof_years_reduction")

    st.markdown("#### Loss Configuration")
    c1, c2 = st.columns(2)
    with c1:
        loss_amount = st.number_input("Loss Amount", value=1000.0, min_value=0.0, step=100.0, key="gof_loss")
    with c2:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="gof_start_mode")
        start_age = st.number_input("Start Age", value=75.0, step=0.01, format="%.2f", key="gof_start_age", disabled=(start_mode == "Age at Calculation"))

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table35_csv = st.text_input("Table35 CSV Path", value=str(paths.table35_csv), key="gof_table35_csv")

    if st.button("Compute General One Off", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
            else:
                calculation_age = float(claimant_age)
            calc = GeneralOneOffCalculation(table35_vector=_load_table36_vector(table35_csv))
            result = calc.calculate(
                loss_amount=float(loss_amount),
                calculation_age=float(calculation_age),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Multiplier: {result['multiplier']:.8f}")
            st.write(f"Total: {result['total']:.8f}")
            st.write(f"Calculation Age (derived): {result['calculation_age']:.8f}")
            st.write(f"Start Years: {result['start_years']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "General Periodical (GP)":
    st.subheader("General Periodical (GP)")
    st.caption("Recurring discrete losses discounted purchase-by-purchase via Table 35.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="gp_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="gp_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1960, 7, 7), key="gp_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="gp_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="gp_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="gp_le_basis")
            if life_expectancy_basis == "impaired":
                imp_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="gp_imp_type")
                if imp_type == "end_age":
                    gp_imp_end = st.number_input("Impaired End Age", value=80.00, step=0.01, format="%.2f", key="gp_imp_end")
                    gp_years_red = None
                else:
                    gp_years_red = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="gp_years_red")
                    gp_imp_end = None
            else:
                gp_imp_end = None
                gp_years_red = None
        else:
            life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f", key="gp_le_years")
            gp_imp_end = None
            gp_years_red = None
    with g3:
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)",
            value=0.0,
            step=0.0001,
            format="%.4f",
            key="gp_lm_override",
        )

    st.markdown("#### Loss Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        loss_amount = st.number_input("Loss Amount", value=1000.0, min_value=0.0, step=100.0, key="gp_loss")
        recurrence_every = st.number_input("Recurs Every", value=1.0, min_value=0.0001, step=1.0, key="gp_every")
        recurrence_unit = st.selectbox("Recurrence Unit", ["Years", "Months", "Weeks", "Days"], index=0, key="gp_unit")
    with c2:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="gp_start_mode")
        start_age = st.number_input("Start Age", value=67.0, step=0.01, format="%.2f", key="gp_start_age", disabled=(start_mode == "Age at Calculation"))
    with c3:
        end_mode = st.selectbox("End Date / Age of Loss", ["Rest of Life", "Specific Age"], index=0, key="gp_end_mode")
        end_age = st.number_input("End Age", value=80.0, step=0.01, format="%.2f", key="gp_end_age", disabled=(end_mode == "Rest of Life"))

    if recurrence_unit in {"Months", "Weeks", "Days"}:
        st.warning("Please use General Continuous for losses occurring less than once per year.")
    gp_pi_parity = st.checkbox("PI parity mode", value=True, key="gp_pi_parity")

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table35_csv = st.text_input("Table35 CSV Path", value=str(paths.table35_csv), key="gp_table35_csv")
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="gp_table36_csv")

    if st.button("Compute General Periodical", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    life_expectancy_age = float(calculation_age + standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if gp_imp_end is not None:
                        life_expectancy_age = float(gp_imp_end)
                        remaining_life = float(life_expectancy_age - calculation_age)
                    else:
                        remaining_life = float(standard_remaining_life - float(gp_years_red or 0.0))
                        life_expectancy_age = float(calculation_age + remaining_life)
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=float(remaining_life),
                    )
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                        female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            calc = GeneralPeriodicalCalculation(
                table35_vector=_load_table36_vector(table35_csv),
                table36_vector=_load_table36_vector(table36_csv),
            )
            result = calc.calculate(
                loss_amount=float(loss_amount),
                recurrence_every=float(recurrence_every),
                recurrence_unit=str(recurrence_unit),
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                end_age=(None if end_mode == "Rest of Life" else float(end_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
                end_at_rest_of_life=(end_mode == "Rest of Life"),
                pi_parity_mode=bool(gp_pi_parity),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Purchase Count: {result['purchase_count']}")
            st.write(f"Raw Multiplier: {result['raw_multiplier']:.8f}")
            st.write(f"Life Term Multiplier: {result['life_term_multiplier']:.8f}")
            st.write(f"Life Multiplier: {result['life_multiplier']:.8f}")
            st.write(f"Multiplier: {result['multiplier']:.8f}")
            st.write(f"Total: {result['total']:.8f}")
            st.write(f"Calculation Age (derived): {result['calculation_age']:.8f}")
            st.write(f"Life Expectancy Age (derived): {result['life_expectancy_age']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Lifetime (Split) (LS)":
    st.subheader("Lifetime (Split) (LS)")
    st.caption("Split lifetime into contiguous periods; each period uses CM apportionment.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="ls_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="ls_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1960, 7, 7), key="ls_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="ls_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="ls_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="ls_le_basis")
            if life_expectancy_basis == "impaired":
                ls_imp_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="ls_imp_type")
                if ls_imp_type == "end_age":
                    ls_imp_end = st.number_input("Impaired End Age", value=80.0, step=0.01, format="%.2f", key="ls_imp_end")
                    ls_years_red = None
                else:
                    ls_years_red = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="ls_years_red")
                    ls_imp_end = None
            else:
                ls_imp_end = None
                ls_years_red = None
        else:
            life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f", key="ls_le_years")
            ls_imp_end = None
            ls_years_red = None
    with g3:
        life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="ls_lm_override")

    st.markdown("#### Loss Configuration")
    ls_start_mode = st.selectbox(
        "Start Date / Age of Loss",
        ["Age at Calculation", "Specific Age"],
        index=0,
        key="ls_start_mode",
    )
    ls_start_age = st.number_input(
        "Start Age",
        value=65.68,
        step=0.01,
        format="%.2f",
        key="ls_start_age",
        disabled=(ls_start_mode == "Age at Calculation"),
    )
    period_count = int(st.number_input("Loss Count", min_value=1, max_value=10, value=3, step=1, key="ls_count"))
    period_rows: List[Dict[str, float | str | bool]] = []
    for i in range(period_count):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            desc = st.text_input(f"Description (P{i+1})", value=f"P{i+1}", key=f"ls_desc_{i}")
        with c2:
            rest = st.checkbox(f"Period Until: Rest of Life (P{i+1})", value=(i == period_count - 1), key=f"ls_rest_{i}")
            end_age = st.number_input(
                f"Period Until Age (P{i+1})",
                value=67.0 + i * 3.0,
                step=0.01,
                format="%.2f",
                key=f"ls_end_{i}",
                disabled=rest,
            )
        with c3:
            amount = st.number_input(f"Loss Value (P{i+1})", value=2000.0 + i * 1000.0, min_value=0.0, step=100.0, key=f"ls_amt_{i}")
        with c4:
            freq = st.selectbox(f"Rate Period (P{i+1})", ["Per_Year", "Per_Month", "Per_Week", "Per_Day"], index=0, key=f"ls_freq_{i}")
        period_rows.append(
            {
                "description": str(desc),
                "rest_of_life": bool(rest),
                "end_age": float(end_age),
                "amount": float(amount),
                "frequency": str(freq),
            }
        )

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="ls_table36_csv")
    male_whole_life_csv = st.text_input("Male Whole Life CSV", value=str(paths.whole_life_csv), key="ls_male_whole_csv")
    female_paths = resolve_ogden_paths(gender="female", discount_rate=0.5, retirement_age=68)
    female_whole_life_csv = st.text_input("Female Whole Life CSV", value=str(female_paths.whole_life_csv), key="ls_female_whole_csv")

    if st.button("Compute Lifetime (Split)", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    life_expectancy_age = float(calculation_age + standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if ls_imp_end is not None:
                        life_expectancy_age = float(ls_imp_end)
                        remaining_life = float(life_expectancy_age - calculation_age)
                    else:
                        remaining_life = float(standard_remaining_life - float(ls_years_red or 0.0))
                        life_expectancy_age = float(calculation_age + remaining_life)
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=float(remaining_life),
                    )
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table(male_whole_life_csv),
                        female_table=_load_whole_life_table(female_whole_life_csv),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            periods_payload: List[Dict[str, Any]] = []
            for p in period_rows:
                entry: Dict[str, Any] = {
                    "amount": float(p["amount"]),
                    "frequency": str(p["frequency"]),
                    "rest_of_life": bool(p["rest_of_life"]),
                }
                if not bool(p["rest_of_life"]):
                    entry["end_age"] = float(p["end_age"])
                periods_payload.append(entry)

            calc = LifetimeSplitCalculation(
                cm_calculation=ContinuousMultiplierCalculation(table36_vector=_load_table36_vector(table36_csv))
            )
            result = calc.calculate(
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                periods=periods_payload,
                start_at_calculation_age=(ls_start_mode == "Age at Calculation"),
                start_age=(None if ls_start_mode == "Age at Calculation" else float(ls_start_age)),
            )
            st.success(SUCCESS_MSG)
            for p in result["periods"]:
                st.write(
                    f"Period {p['index']}: Annual {p['annualised_amount']:.8f} | "
                    f"Multiplier {p['period_multiplier']:.8f} | Total {p['period_total']:.8f}"
                )
            st.write(f"Total: {result['total']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Periodical Multiplier (PM)":
    st.subheader("Periodical Multiplier (PM)")
    st.caption("Recurring multiplier calculation; total optional if amount is provided.")

    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="pm_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f", key="pm_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1960, 7, 7), key="pm_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="pm_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="pm_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="pm_le_basis")
            if life_expectancy_basis == "impaired":
                pm_imp_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="pm_imp_type")
                if pm_imp_type == "end_age":
                    pm_imp_end = st.number_input("Impaired End Age", value=80.0, step=0.01, format="%.2f", key="pm_imp_end")
                    pm_years_red = None
                else:
                    pm_years_red = st.number_input("Years Reduction", value=4.69, step=0.01, format="%.2f", key="pm_years_red")
                    pm_imp_end = None
            else:
                pm_imp_end = None
                pm_years_red = None
        else:
            life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f", key="pm_le_years")
            pm_imp_end = None
            pm_years_red = None
    with g3:
        life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="pm_lm_override")

    st.markdown("#### Loss Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        recurrence_every = st.number_input("Recurs every", value=1.0, min_value=0.0001, step=1.0, key="pm_every")
        recurrence_unit = st.selectbox("Recurrence Unit", ["Years", "Months", "Weeks", "Days"], index=0, key="pm_unit")
        loss_amount = st.number_input("Optional Amount (for total)", value=0.0, min_value=0.0, step=100.0, key="pm_amount")
    with c2:
        start_mode = st.selectbox("Start Date / Age of Loss", ["Age at Calculation", "Specific Age"], index=0, key="pm_start_mode")
        start_age = st.number_input("Start Age", value=67.0, step=0.01, format="%.2f", key="pm_start_age", disabled=(start_mode == "Age at Calculation"))
    with c3:
        end_mode = st.selectbox("End Date / Age of Loss", ["Rest of Life", "Specific Age"], index=0, key="pm_end_mode")
        end_age = st.number_input("End Age", value=90.0, step=0.01, format="%.2f", key="pm_end_age", disabled=(end_mode == "Rest of Life"))
    pm_pi_parity = st.checkbox("PI parity mode", value=True, key="pm_pi_parity")

    st.markdown("#### Data Sources")
    paths = resolve_ogden_paths(gender="male", discount_rate=0.5, retirement_age=68)
    table35_csv = st.text_input("Table35 CSV Path", value=str(paths.table35_csv), key="pm_table35_csv")
    table36_csv = st.text_input("Table36 CSV Path", value=str(paths.table36_csv), key="pm_table36_csv")

    if st.button("Compute Periodical Multiplier", use_container_width=True):
        try:
            if le_input_mode == "derived_from_dates":
                calculation_age = _decimal_age_years(dob, calculation_date)
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(calculation_age),
                )
                if life_expectancy_basis == "standard":
                    life_expectancy_age = float(calculation_age + standard_remaining_life)
                    derived_anchor = float(standard_anchor)
                else:
                    if pm_imp_end is not None:
                        life_expectancy_age = float(pm_imp_end)
                        remaining_life = float(life_expectancy_age - calculation_age)
                    else:
                        remaining_life = float(standard_remaining_life - float(pm_years_red or 0.0))
                        life_expectancy_age = float(calculation_age + remaining_life)
                    _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        remaining_life_years=float(remaining_life),
                    )
            else:
                calculation_age = float(claimant_age)
                life_expectancy_age = float(calculation_age + life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                if le_input_mode == "derived_from_dates":
                    life_multiplier = float(derived_anchor)
                else:
                    wl = CareWholeLifeCalculation(
                        male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                        female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                    )
                    life_multiplier = wl.multiplier(claimant_age=float(calculation_age), gender=str(gender))

            gp = GeneralPeriodicalCalculation(
                table35_vector=_load_table36_vector(table35_csv),
                table36_vector=_load_table36_vector(table36_csv),
            )
            pm = PeriodicalMultiplierCalculation(gp_calculation=gp)
            result = pm.calculate(
                recurrence_every=float(recurrence_every),
                recurrence_unit=str(recurrence_unit),
                calculation_age=float(calculation_age),
                life_expectancy_age=float(life_expectancy_age),
                life_multiplier=float(life_multiplier),
                start_age=(None if start_mode == "Age at Calculation" else float(start_age)),
                end_age=(None if end_mode == "Rest of Life" else float(end_age)),
                start_at_calculation_age=(start_mode == "Age at Calculation"),
                end_at_rest_of_life=(end_mode == "Rest of Life"),
                loss_amount=float(loss_amount),
                pi_parity_mode=bool(pm_pi_parity),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Purchase Count: {result['purchase_count']}")
            st.write(f"Raw Multiplier: {result['raw_multiplier']:.8f}")
            st.write(f"Life Term Multiplier: {result['life_term_multiplier']:.8f}")
            st.write(f"Life Multiplier: {result['life_multiplier']:.8f}")
            st.write(f"Multiplier: {result['multiplier']:.8f}")
            st.write(f"Total: {result['total']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Care Claim (Full)":
    st.subheader("Care Claim (Annualisation + Multiplier)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    life_expectancy_end_age = None
    impaired_end_age = None
    years_reduction = None
    derived_life_expectancy_end_age = None
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="claim_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input(
                "Claimant Age",
                value=46.19,
                step=0.01,
                format="%.2f",
                key="claim_claimant_age",
            )
        else:
            dob = _date_input("DOB", value=date(1980, 4, 23), key="claim_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="claim_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="claim_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="claim_le_basis",
            )
        else:
            life_expectancy_basis = "standard"
    with g3:
        if le_input_mode == "manual_years":
            life_expectancy_years = st.number_input(
                "Life Expectancy Years",
                value=38.40,
                step=0.01,
                format="%.2f",
                key="claim_life_expectancy_years",
            )
            impairment_input_type = "end_age"
        else:
            life_expectancy_years = None
            if life_expectancy_basis == "impaired":
                impairment_input_type = st.selectbox(
                    "Impairment Input Type",
                    ["end_age", "years_reduction"],
                    index=0,
                    key="claim_impairment_input_type",
                )
                if impairment_input_type == "end_age":
                    impaired_end_age = st.number_input(
                        "Impaired End Age",
                        value=72.00,
                        min_value=0.01,
                        step=0.01,
                        format="%.2f",
                        key="claim_impaired_end_age",
                    )
                else:
                    years_reduction = st.number_input(
                        "Years Reduction from Standard",
                        value=0.0,
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key="claim_years_reduction",
                    )
            else:
                impairment_input_type = "end_age"

    st.markdown("#### Care Settings")
    s1, s2 = st.columns(2)
    with s1:
        start_mode = st.selectbox(
            "Start Date / Age of Loss",
            ["Age at Calculation", "Specific Age"],
            index=0,
            key="claim_start_mode",
        )
        age_at_start_input = st.number_input(
            "Start Age",
            value=46.19,
            step=0.01,
            format="%.2f",
            key="claim_age_start",
            disabled=(start_mode == "Age at Calculation"),
        )
    with s2:
        end_mode = st.selectbox(
            "End Date / Age of Loss",
            ["Rest of Life", "Specific Age"],
            index=0,
            key="claim_end_mode",
        )
        age_at_end_input = st.number_input(
            "End Age",
            value=84.59,
            step=0.01,
            format="%.2f",
            key="claim_age_end",
            disabled=(end_mode == "Rest of Life"),
        )

    payload = _base_inputs("claim")

    st.markdown("#### Manual Overrides")
    m1, m2 = st.columns(2)
    with m1:
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)",
            value=0.0,
            step=0.0001,
            format="%.4f",
            key="claim_life_multiplier_override",
        )
        use_life_end_age_override = False
        if le_input_mode == "derived_from_dates":
            use_life_end_age_override = st.checkbox(
                "Override Life Expectancy End Age",
                value=False,
                key="claim_use_life_end_override",
            )
            if use_life_end_age_override:
                life_expectancy_end_age = st.number_input(
                    "Life Expectancy End Age (Override)",
                    value=84.59,
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key="claim_life_end_age",
                )
        term_start_override = st.number_input(
            "Term Start Override (optional)",
            value=0.0,
            step=0.01,
            format="%.2f",
            key="claim_term_start_override",
        )
    with m2:
        term_end_override = st.number_input(
            "Term End Override (optional)",
            value=0.0,
            step=0.01,
            format="%.2f",
            key="claim_term_end_override",
        )

    st.markdown("#### CSV Used")
    table36_csv = st.text_input("Table36 CSV Path", value="data/ogden8table36dr05.csv", key="claim_table36_csv")

    if st.button("Compute Care Claim", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None or life_expectancy_years is None:
                    raise ValueError("Claimant Age and Life Expectancy Years are required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
                effective_life_expectancy_years = float(life_expectancy_years)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
                if life_expectancy_end_age is not None:
                    effective_life_expectancy_years = float(life_expectancy_end_age) - effective_claimant_age
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Derived life expectancy years must be greater than 0.")
                else:
                    add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                    add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                    standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        claimant_age=float(effective_claimant_age),
                    )
                    if life_expectancy_basis == "standard":
                        effective_life_expectancy_years = float(standard_remaining_life)
                        derived_anchor = float(standard_anchor)
                    else:
                        if impairment_input_type == "end_age":
                            effective_life_expectancy_years = float(impaired_end_age) - effective_claimant_age
                        else:
                            effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction)
                        if effective_life_expectancy_years <= 0:
                            raise ValueError("Impaired life expectancy years must be greater than 0.")
                        _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                            zero_csv=add_zero,
                            point5_csv=add_p5,
                            remaining_life_years=effective_life_expectancy_years,
                        )
                    if life_multiplier_override <= 0:
                        life_multiplier = float(derived_anchor)
                    derived_life_expectancy_end_age = effective_claimant_age + effective_life_expectancy_years
                    st.caption(
                        f"Derived LE End Age (Additional Tables): {derived_life_expectancy_end_age:.2f} | "
                        f"Derived LE Years: {effective_life_expectancy_years:.2f}"
                    )

            if start_mode == "Age at Calculation":
                age_at_start = float(effective_claimant_age)
            else:
                age_at_start = float(age_at_start_input)

            if end_mode == "Rest of Life":
                age_at_end = float(effective_claimant_age + effective_life_expectancy_years)
            else:
                age_at_end = float(age_at_end_input)

            term_start_years = term_start_override if term_start_override > 0 else (age_at_start - effective_claimant_age)
            term_end_years = term_end_override if term_end_override > 0 else (age_at_end - effective_claimant_age)

            if life_multiplier_override > 0:
                life_multiplier = life_multiplier_override
            elif le_input_mode == "manual_years" or life_expectancy_end_age is not None:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=effective_claimant_age, gender=gender)

            claim_calc = CareClaimCalculation(
                care_calculation=CareCalculation(),
                care_multiplier_calculation=CareMultiplierCalculation(
                    table36_vector=_load_table36_vector(table36_csv)
                ),
            )
            result = claim_calc.calculate(
                age_at_start=age_at_start,
                age_at_end=age_at_end,
                number_of_hours=float(payload["number_of_hours"]),
                time_increment=str(payload["time_increment"]),
                care_rate_type=str(payload["care_rate_type"]),
                rate_values=payload["rate_values"],
                percentage_less=float(payload["percentage_less"]),
                manual_rate=payload["manual_rate"],
                specify_increment=payload["specify_increment"],
                number_days_specify=payload["number_days_specify"],
                number_weeks_specify=payload["number_weeks_specify"],
                number_months_specify=payload["number_months_specify"],
                term_start_years=term_start_years,
                term_end_years=term_end_years,
                life_expectancy_years=effective_life_expectancy_years,
                life_multiplier=life_multiplier,
            )

            st.success(SUCCESS_MSG)
            st.write(f"Annualised Cost: {result['annualised_cost']:.8f}")
            st.write(f"Life Multiplier: {life_multiplier:.8f}")
            st.write(f"Term Start Years: {term_start_years:.8f}")
            st.write(f"Term End Years: {term_end_years:.8f}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Total Award: {result['total_award']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Care (Split)":
    st.subheader("Care (Split) - PI style")
    st.caption("Single entry for split rows with shared rate/less, then compute all phases together.")
    st.markdown("#### Global Settings")
    c1, c2, c3 = st.columns(3)
    with c1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="split_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input(
                "Loss Age(s) Start (Age at Calculation)",
                value=65.68,
                step=0.01,
                format="%.2f",
                key="split_claimant_age",
            )
        else:
            dob = _date_input("DOB", value=date(1980, 1, 3), key="split_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="split_calc_date")
    with c2:
        gender = st.selectbox("Gender", ["male", "female"], key="split_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="split_le_basis",
            )
        else:
            life_expectancy_basis = "standard"
    with c3:
        if le_input_mode == "manual_years":
            life_expectancy_years = st.number_input(
                "Life Expectancy Years",
                value=19.67,
                step=0.01,
                format="%.2f",
                key="split_life_expectancy_years",
            )
            impairment_input_type = "end_age"
        else:
            life_expectancy_years = None
            impaired_end_age = None
            years_reduction = None
            if life_expectancy_basis == "impaired":
                impairment_input_type = st.selectbox(
                    "Impairment Input Type",
                    ["end_age", "years_reduction"],
                    index=0,
                    key="split_impairment_input_type",
                )
                if impairment_input_type == "end_age":
                    impaired_end_age = st.number_input(
                        "Impaired End Age",
                        value=72.00,
                        min_value=0.01,
                        step=0.01,
                        format="%.2f",
                        key="split_impaired_end_age",
                    )
                else:
                    years_reduction = st.number_input(
                        "Years Reduction from Standard",
                        value=0.0,
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key="split_years_reduction",
                    )
            else:
                impairment_input_type = "end_age"

    st.markdown("#### Split Settings")
    loss_count = st.number_input("Loss Count", min_value=1, max_value=20, value=3, step=1, key="split_loss_count")

    # Shared rate/less fields for split set
    rate_type_display = {
        "Aggregate_Rate": "Aggregate Rate",
        "Basic_Rate": "Basic Rate",
        "Evening_Rate": "Evening Rate",
        "Weekend_Rate": "Weekend Rate",
        "Saturday_Rate": "Saturday Rate",
        "Sunday_Rate": "Sunday Rate",
        "Aggregate_Day_Rate": "Aggregate Day Rate",
        "Specify_Rate": "Specify Own Rate",
    }
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        care_rate_type = st.selectbox(
            "Rate to Use",
            list(rate_type_display.keys()),
            index=0,
            key="split_care_rate_type",
            format_func=lambda v: rate_type_display.get(v, v),
        )
    with rc2:
        rate_value = st.number_input("Rate Value", value=16.62, min_value=0.0, step=0.01, format="%.4f", key="split_rate_value")
    with rc3:
        percentage_less = st.number_input("Less (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key="split_less")

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    with o1:
        table36_csv = st.text_input("Table36 CSV Path", value="data/ogden8table36dr05.csv", key="split_table36_csv")
    with o2:
        require_contiguous = st.checkbox("Require contiguous periods", value=True, key="split_require_contig")

    effective_claimant_age = float(claimant_age) if claimant_age is not None else None
    effective_life_expectancy_years = float(life_expectancy_years) if life_expectancy_years is not None else None
    life_end_age = None
    if le_input_mode == "derived_from_dates":
        effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
        add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
        add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
        standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
            zero_csv=add_zero,
            point5_csv=add_p5,
            claimant_age=float(effective_claimant_age),
        )
        if life_expectancy_basis == "standard":
            effective_life_expectancy_years = float(standard_remaining_life)
        else:
            if impairment_input_type == "end_age":
                effective_life_expectancy_years = float(impaired_end_age) - float(effective_claimant_age)
            else:
                effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction)
        if effective_life_expectancy_years > 0:
            life_end_age = float(effective_claimant_age + effective_life_expectancy_years)
            st.caption(
                f"Derived Claimant Age: {effective_claimant_age:.2f} | "
                f"Derived LE End Age: {life_end_age:.2f} | "
                f"Derived LE Years: {effective_life_expectancy_years:.2f}"
            )
        else:
            life_end_age = None
            st.warning("Derived life expectancy years must be greater than 0.")
    else:
        if effective_claimant_age is not None and effective_life_expectancy_years is not None:
            life_end_age = float(effective_claimant_age + effective_life_expectancy_years)
        else:
            life_end_age = None

    periods = []
    current_start = float(effective_claimant_age)
    for i in range(int(loss_count)):
        st.markdown(f"#### Row {i + 1}")
        p1, p2, p3 = st.columns(3)
        with p1:
            period_until_age = st.number_input(
                "Period Until Age",
                value=float(current_start + 1.0),
                step=0.01,
                format="%.2f",
                key=f"split_row_{i}_until_age",
            )
        with p2:
            number_of_hours = st.number_input(
                "Hours",
                value=float(20 + (10 * i)),
                min_value=0.0,
                step=1.0,
                key=f"split_row_{i}_hours",
            )
        with p3:
            time_increment = st.selectbox(
                "Frequency",
                ["Per_Week", "Per_Day", "Per_Month", "Per_Year", "Per_Weekday", "Per_Weekend"],
                index=0,
                key=f"split_row_{i}_freq",
            )

        is_rest_of_life = st.checkbox("Rest of Life", value=(i == int(loss_count) - 1), key=f"split_row_{i}_rol")
        end_age = float(life_end_age) if is_rest_of_life else float(period_until_age)
        period_obj = {
            "age_at_start": float(current_start),
            "age_at_end": end_age,
            "number_of_hours": float(number_of_hours),
            "time_increment": str(time_increment),
            "care_rate_type": str(care_rate_type),
            "percentage_less": float(percentage_less),
        }
        if care_rate_type == "Specify_Rate":
            period_obj["manual_rate"] = float(rate_value)
            period_obj["rate_values"] = {}
        else:
            period_obj["manual_rate"] = None
            period_obj["rate_values"] = {care_rate_type: float(rate_value)}
        periods.append(period_obj)
        current_start = end_age
        st.divider()

    if st.button("Compute Care Split Claim", use_container_width=True):
        try:
            if effective_claimant_age is None:
                raise ValueError("Claimant age could not be determined.")
            if effective_life_expectancy_years is None or effective_life_expectancy_years <= 0:
                raise ValueError("Life expectancy years must be greater than 0.")
            if life_end_age is None:
                raise ValueError("Life end age could not be determined.")
            wl = CareWholeLifeCalculation(
                male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
            )
            life_multiplier = wl.multiplier(claimant_age=float(effective_claimant_age), gender=gender)
            claim_split_calc = CareClaimCalculation(
                care_calculation=CareCalculation(),
                care_multiplier_calculation=CareMultiplierCalculation(
                    table36_vector=_load_table36_vector(table36_csv)
                ),
            )
            result = claim_split_calc.calculate_split(
                periods=periods,
                claimant_age=float(effective_claimant_age),
                life_expectancy_years=float(effective_life_expectancy_years),
                life_multiplier=life_multiplier,
                require_contiguous=require_contiguous,
            )
            st.success(SUCCESS_MSG)
            st.write(f"Life Multiplier: {life_multiplier:.8f}")
            for phase in result["phase_results"]:
                st.write(
                    f"Phase {phase['phase']}: Age {phase['age_at_start']:.2f} -> {phase['age_at_end']:.2f} | "
                    f"Annual {phase['annualised_cost']:.2f} | Multiplier {phase['period_multiplier']:.4f} | Total {phase['total_award']:.2f}"
                )
            st.write(f"Split Claim Total Award: {result['total_award']:.2f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Equipment":
    st.subheader("Equipment")
    st.caption("Capital replacement stream plus annual insurance and maintenance.")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="eq_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="eq_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="eq_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="eq_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="eq_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="eq_le_basis",
            )
        else:
            life_expectancy_basis = "standard"
    with g3:
        purchase_mortality_mode = st.selectbox(
            "Purchase Mortality Mode",
            ["no_mortality", "use_mortality", "use_mortality_pi_mm"],
            index=1,
            key="eq_purchase_mortality_mode",
        )
        life_expectancy_end_age = None
        impaired_end_age = None
        years_reduction = None
        if le_input_mode == "derived_from_dates" and life_expectancy_basis == "impaired":
            impairment_input_type = st.selectbox(
                "Impairment Input Type",
                ["end_age", "years_reduction"],
                index=0,
                key="eq_impairment_input_type",
            )
            if impairment_input_type == "end_age":
                impaired_end_age = st.number_input(
                    "Impaired End Age",
                    value=72.00,
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key="eq_impaired_end_age",
                )
            else:
                years_reduction = st.number_input(
                    "Years Reduction from Standard",
                    value=0.0,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="eq_years_reduction",
                )
        else:
            impairment_input_type = "end_age"

    st.markdown("#### Equipment Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        start_mode = st.selectbox(
            "Start Date / Age of Loss",
            ["Age at Calculation", "Specific Age"],
            index=0,
            key="eq_start_mode",
        )
        age_at_start_input = st.number_input(
            "Start Age",
            value=50.00,
            step=0.01,
            format="%.2f",
            key="eq_age_start",
            disabled=(start_mode == "Age at Calculation"),
        )
        end_mode = st.selectbox(
            "End Date / Age of Loss",
            ["Rest of Life", "Specific Age"],
            index=1,
            key="eq_end_mode",
        )
        age_at_end_input = st.number_input(
            "End Age",
            value=80.00,
            step=0.01,
            format="%.2f",
            key="eq_age_end",
            disabled=(end_mode == "Rest of Life"),
        )
        cost_of_equipment = st.number_input("Cost of Equipment", value=5000.0, min_value=0.0, step=100.0, key="eq_cost")
    with s2:
        replacement_every_value = st.number_input(
            "Replacement every (Value)",
            value=3.0,
            min_value=0.01,
            step=1.0,
            key="eq_replace_value",
        )
        replacement_every_unit = st.selectbox(
            "Replacement Unit",
            ["Days", "Weeks", "Months", "Years"],
            index=3,
            key="eq_replace_unit",
        )
        annual_insurance = st.number_input("Annual Insurance", value=400.0, min_value=0.0, step=10.0, key="eq_insurance")
        annual_maintenance = st.number_input(
            "Annual Maintenance", value=200.0, min_value=0.0, step=10.0, key="eq_maintenance"
        )
    with s3:
        st.caption("PI dynamic behavior is used by default.")

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    purchase_boundary_mode_override = None
    recurring_life_basis_override = None
    with o1:
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)",
            value=0.0,
            step=0.0001,
            format="%.4f",
            key="eq_life_multiplier_override",
        )
        use_behavior_overrides = st.checkbox(
            "Override purchase/recurring behavior",
            value=False,
            key="eq_use_behavior_overrides",
        )
        if use_behavior_overrides:
            purchase_boundary_mode_override = st.selectbox(
                "Purchase Boundary Mode (override)",
                ["future_only", "include_start"],
                index=0,
                key="eq_purchase_boundary_mode",
            )
            recurring_life_basis_override = st.selectbox(
                "Recurring Life Basis (override)",
                ["period", "full_life"],
                index=1,
                key="eq_recurring_life_basis",
            )
        life_expectancy_years = None
        if le_input_mode == "manual_years":
            life_expectancy_years = st.number_input(
                "Life Expectancy Years",
                value=41.93,
                min_value=0.01,
                step=0.01,
                format="%.2f",
                key="eq_life_expectancy_years",
            )
    with o2:
        manual_life_expectancy_end_age = st.number_input(
            "Life Expectancy End Age (manual override helper)",
            value=0.0,
            step=0.01,
            format="%.2f",
            key="eq_life_expectancy_end_age",
        )
        use_life_end_age_override = False
        if le_input_mode == "derived_from_dates":
            use_life_end_age_override = st.checkbox(
                "Override Life Expectancy End Age",
                value=False,
                key="eq_use_life_end_override",
            )
            if use_life_end_age_override:
                life_expectancy_end_age = st.number_input(
                    "Life Expectancy End Age (Override)",
                    value=84.61,
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key="eq_life_end_age",
                )

    st.markdown("#### CSV Used")
    c1, c2 = st.columns(2)
    with c1:
        table35_csv = st.text_input("Table35 CSV Path", value="data/ogden8table35dr05.csv", key="eq_table35_csv")
    with c2:
        table36_csv = st.text_input("Table36 CSV Path", value="data/ogden8table36dr05.csv", key="eq_table36_csv")

    if st.button("Compute Equipment", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
            derived_life_expectancy_end_age = None
            if le_input_mode == "derived_from_dates":
                if life_expectancy_end_age is not None:
                    effective_life_expectancy_years = float(life_expectancy_end_age) - effective_claimant_age
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Derived life expectancy years must be greater than 0.")
                    st.caption(
                        f"Derived LE Years (Override): {effective_life_expectancy_years:.2f}"
                    )
                else:
                    add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                    add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                    standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        claimant_age=float(effective_claimant_age),
                    )
                    if life_expectancy_basis == "standard":
                        effective_life_expectancy_years = float(standard_remaining_life)
                        derived_anchor = float(standard_anchor)
                    else:
                        if impairment_input_type == "end_age":
                            effective_life_expectancy_years = float(impaired_end_age) - effective_claimant_age
                        else:
                            effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction)
                        if effective_life_expectancy_years <= 0:
                            raise ValueError("Impaired life expectancy years must be greater than 0.")
                        _, derived_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                            zero_csv=add_zero,
                            point5_csv=add_p5,
                            remaining_life_years=effective_life_expectancy_years,
                        )
                    if life_multiplier_override <= 0:
                        life_multiplier = float(derived_anchor)
                    derived_life_expectancy_end_age = effective_claimant_age + effective_life_expectancy_years
                    st.caption(
                        f"Derived LE End Age (Additional Tables): {derived_life_expectancy_end_age:.2f} | "
                        f"Derived LE Years: {effective_life_expectancy_years:.2f}"
                    )
            else:
                if life_expectancy_years is None:
                    raise ValueError("Life Expectancy Years is required in manual_years mode.")
                effective_life_expectancy_years = float(life_expectancy_years)

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            elif le_input_mode != "derived_from_dates" or life_expectancy_end_age is not None:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=float(effective_claimant_age), gender=str(gender))

            calc = EquipmentCalculation(
                table35_vector=_load_table36_vector(table35_csv),
                table36_vector=_load_table36_vector(table36_csv),
            )
            if start_mode == "Age at Calculation":
                age_at_start = float(effective_claimant_age)
            else:
                age_at_start = float(age_at_start_input)

            if end_mode == "Rest of Life":
                age_at_end = float(effective_claimant_age + effective_life_expectancy_years)
            else:
                age_at_end = float(age_at_end_input)

            if recurring_life_basis_override == "period":
                # Keep recurring stream basis aligned with the selected loss end age.
                effective_life_expectancy_years = float(age_at_end - effective_claimant_age)
            elif recurring_life_basis_override == "full_life":
                if le_input_mode == "derived_from_dates":
                    if life_expectancy_end_age is not None:
                        effective_life_expectancy_years = float(life_expectancy_end_age - effective_claimant_age)
                    else:
                        effective_life_expectancy_years = float(
                            (derived_life_expectancy_end_age or (effective_claimant_age + effective_life_expectancy_years))
                            - effective_claimant_age
                        )
                else:
                    if float(manual_life_expectancy_end_age) <= float(effective_claimant_age):
                        raise ValueError(
                            "Life Expectancy End Age (manual override helper) must be greater than claimant age when full_life override is used."
                        )
                    effective_life_expectancy_years = float(manual_life_expectancy_end_age - effective_claimant_age)

            result = calc.calculate(
                age_at_start=float(age_at_start),
                age_at_end=float(age_at_end),
                cost_of_equipment=float(cost_of_equipment),
                replacement_every_value=float(replacement_every_value),
                replacement_every_unit=str(replacement_every_unit),
                claimant_age=float(effective_claimant_age),
                life_expectancy_years=effective_life_expectancy_years,
                life_multiplier=float(life_multiplier),
                annual_insurance=float(annual_insurance),
                annual_maintenance=float(annual_maintenance),
                purchase_mortality_mode=str(purchase_mortality_mode),
                purchase_boundary_mode=purchase_boundary_mode_override,
            )
            st.success(SUCCESS_MSG)
            unit_label = replacement_every_unit.lower()
            if unit_label.endswith("s"):
                unit_label = unit_label[:-1]
            st.write(
                f"Equipment Loss: {result['capital_total']:.8f} "
                f"(calculated as {result['annual_equipment_cost_display']:.8f} every {replacement_every_value:.8f} {unit_label} "
                f"for {result['purchase_count']} purchases; Multiplier: {result['equipment_multiplier']:.8f})"
            )
            st.write(
                f"Insurance Costs: {result['insurance_total']:.8f} "
                f"(at {annual_insurance:.8f} per year; Multiplier: {result['recurring_multiplier']:.8f})"
            )
            st.write(
                f"Maintenance Costs: {result['maintenance_total']:.8f} "
                f"(at {annual_maintenance:.8f} per year; Multiplier: {result['recurring_multiplier']:.8f})"
            )
            st.write(f"Life Multiplier: {life_multiplier:.8f}")
            st.write(f"Life Expectancy Years: {effective_life_expectancy_years:.8f}")
            st.write(f"Total: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Travel Claim (Full)":
    st.subheader("Travel Claim (Annual + Multiplier)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="tr_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="tr_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="tr_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="tr_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="tr_gender")
        life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="tr_le_basis")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="tr_dr")
    with g3:
        impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="tr_imp_type", disabled=(life_expectancy_basis != "impaired"))
        impaired_end_age = st.number_input("Impaired End Age", value=72.00, min_value=0.01, step=0.01, format="%.2f", key="tr_imp_end", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "end_age"))
        years_reduction = st.number_input("Years Reduction from Standard", value=0.0, min_value=0.0, step=0.01, format="%.2f", key="tr_years_reduction", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "years_reduction"))

    st.markdown("#### Travel Claim Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        age_at_start_text = st.text_input("Loss Age(s) Start", value="", placeholder="Age at Calculation", key="tr_age_start_text")
        age_at_end_text = st.text_input("Loss Age(s) End", value="", placeholder="Rest of Life", key="tr_age_end_text")
        distance = st.number_input("Distance", value=20.0, min_value=0.0, step=1.0, key="tr_distance")
    with s2:
        distance_input_type = st.selectbox("Distance Type", ["Overall", "Each_Way"], index=1, key="tr_distance_type")
        mileage_rate = st.number_input("Rate", value=100.0, min_value=0.0, step=0.01, key="tr_mileage_rate")
        parking_cost = st.number_input("Parking Cost", value=20.0, min_value=0.0, step=1.0, key="tr_parking")
    with s3:
        journey_count = st.number_input("Recurring", value=1.0, min_value=0.0, step=1.0, key="tr_journey_count")
        time_increment = st.selectbox(
            "Recurring Frequency",
            ["Over_Period", "Per_Day", "Per_Week", "Per_Month", "Per_Year", "Per_Weekday", "Per_Weekend"],
            index=2,
            key="tr_time_increment",
        )

    st.markdown("#### Manual Overrides")
    m1, m2 = st.columns(2)
    with m1:
        use_life_end_age_override = st.checkbox("Override Life Expectancy End Age", value=False, key="tr_use_life_end_override")
        life_expectancy_end_age_override = None
        if use_life_end_age_override:
            life_expectancy_end_age_override = st.number_input(
                "Life Expectancy End Age (Override)",
                value=84.69,
                min_value=0.01,
                step=0.01,
                format="%.2f",
                key="tr_life_expectancy_end_age",
            )
    with m2:
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)",
            value=0.0,
            step=0.0001,
            format="%.4f",
            key="tr_life_mult_override",
        )

    if st.button("Compute Travel Claim", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")

            if str(age_at_start_text).strip() == "":
                age_at_start = float(effective_claimant_age)
            else:
                age_at_start = float(age_at_start_text)

            if life_expectancy_end_age_override is not None:
                effective_life_end_age = float(life_expectancy_end_age_override)
            else:
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(effective_claimant_age),
                )
                if life_expectancy_basis == "standard":
                    effective_life_end_age = float(effective_claimant_age + standard_remaining_life)
                else:
                    if impairment_input_type == "end_age":
                        effective_life_end_age = float(impaired_end_age)
                    else:
                        effective_life_end_age = float(effective_claimant_age + standard_remaining_life - float(years_reduction))

            if str(age_at_end_text).strip() == "" or str(age_at_end_text).strip().lower() == "rest of life":
                age_at_end = float(effective_life_end_age)
            else:
                age_at_end = float(age_at_end_text)

            effective_life_expectancy_years = float(effective_life_end_age - effective_claimant_age)
            if effective_life_expectancy_years <= 0:
                raise ValueError("Derived life expectancy years must be greater than 0.")

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=float(effective_claimant_age), gender=str(gender))

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=68)
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)

            calc = TravelClaimCalculation(
                travel_calculation=TravelCalculation(),
                care_multiplier_calculation=CareMultiplierCalculation(
                    table36_vector=_load_table36_vector(paths.table36_csv)
                ),
            )
            result = calc.calculate(
                age_at_start=float(age_at_start),
                age_at_end=float(age_at_end),
                claimant_age=float(effective_claimant_age),
                life_expectancy_years=float(effective_life_expectancy_years),
                life_multiplier=life_multiplier,
                distance=float(distance),
                distance_input_type=str(distance_input_type),
                mileage_rate=float(mileage_rate),
                parking_cost=float(parking_cost),
                journey_count=float(journey_count),
                time_increment=str(time_increment),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Derived Life Expectancy End Age: {effective_life_end_age:.8f}")
            st.write(f"Annual Loss: {result['annual_loss']:.8f}")
            st.write(f"Life Multiplier: {life_multiplier:.8f}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Total Loss: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Vehicle":
    st.subheader("Vehicle")
    st.caption("Initial vehicle need + replacement stream + annual insurance/running extras.")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="vh_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=45.40, step=0.01, format="%.2f", key="vh_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1980, 4, 23), key="vh_dob")
            calculation_date = _date_input("Calculation Date", value=date(2025, 9, 16), key="vh_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="vh_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="vh_le_basis",
            )
        else:
            life_expectancy_basis = "standard"
    with g3:
        life_expectancy_end_age = None
        impaired_end_age = None
        years_reduction = None
        purchase_mortality_mode = st.selectbox(
            "Purchase Mortality Mode",
            ["no_mortality", "use_mortality", "use_mortality_pi_mm"],
            index=1,
            key="vh_purchase_mortality_mode",
        )
        if le_input_mode == "derived_from_dates" and life_expectancy_basis == "impaired":
            impairment_input_type = st.selectbox(
                "Impairment Input Type",
                ["end_age", "years_reduction"],
                index=0,
                key="vh_impairment_input_type",
            )
            if impairment_input_type == "end_age":
                impaired_end_age = st.number_input(
                    "Impaired End Age",
                    value=72.00,
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key="vh_impaired_end_age",
                )
            else:
                years_reduction = st.number_input(
                    "Years Reduction from Standard",
                    value=0.0,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="vh_years_reduction",
                )
        else:
            impairment_input_type = "end_age"

    st.markdown("#### Vehicle Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        age_at_start = st.number_input("Age at Start", value=45.40, step=0.01, format="%.2f", key="vh_age_start")
        age_at_end = st.number_input("Age at End", value=50.00, step=0.01, format="%.2f", key="vh_age_end")
        required_vehicle_cost = st.number_input(
            "Cost of Required Vehicle", value=30000.0, min_value=0.0, step=100.0, key="vh_required_cost"
        )
    with s2:
        existing_vehicle_credit = st.number_input(
            "Credit for Existing Vehicle", value=5000.0, min_value=0.0, step=100.0, key="vh_existing_credit"
        )
        trade_in_value = st.number_input("Trade-In Value", value=1500.0, min_value=0.0, step=100.0, key="vh_trade_in")
        replacement_every_value = st.number_input(
            "Replacement every (Value)", value=1.0, min_value=0.01, step=1.0, key="vh_replace_value"
        )
        replacement_every_unit = st.selectbox(
            "Replacement Unit", ["Days", "Weeks", "Months", "Years"], index=3, key="vh_replace_unit"
        )
    with s3:
        increased_insurance = st.number_input(
            "Increased Insurance Costs", value=200.0, min_value=0.0, step=10.0, key="vh_insurance"
        )
        increased_running_costs = st.number_input(
            "Increased Running Costs", value=750.0, min_value=0.0, step=10.0, key="vh_running"
        )

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    with o1:
        replacement_start_age = st.number_input(
            "Replacement Start Age (optional override, 0 = auto)",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.2f",
            key="vh_replace_start_age",
        )
        life_multiplier_override = st.number_input(
            "Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="vh_life_mult"
        )
    with o2:
        life_expectancy_years = None
        if le_input_mode == "manual_years":
            life_expectancy_years = st.number_input(
                "Life Expectancy Years",
                value=39.21,
                min_value=0.01,
                step=0.01,
                format="%.2f",
                key="vh_life_years",
            )
        use_life_end_age_override = False
        if le_input_mode == "derived_from_dates":
            use_life_end_age_override = st.checkbox(
                "Override Life Expectancy End Age",
                value=False,
                key="vh_use_life_end_override",
            )
            if use_life_end_age_override:
                life_expectancy_end_age = st.number_input(
                    "Life Expectancy End Age (Override)",
                    value=84.61,
                    min_value=0.01,
                    step=0.01,
                    format="%.2f",
                    key="vh_life_end_age",
                )

    st.markdown("#### CSV Used")
    c1, c2 = st.columns(2)
    with c1:
        table35_csv = st.text_input("Table35 CSV Path", value="data/ogden8table35dr05.csv", key="vh_table35_csv")
    with c2:
        table36_csv = st.text_input("Table36 CSV Path", value="data/ogden8table36dr05.csv", key="vh_table36_csv")

    if st.button("Compute Vehicle", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=effective_claimant_age, gender=str(gender))

            if le_input_mode == "derived_from_dates":
                if life_expectancy_end_age is not None:
                    effective_life_expectancy_years = float(life_expectancy_end_age) - effective_claimant_age
                    if effective_life_expectancy_years <= 0:
                        raise ValueError("Derived life expectancy years must be greater than 0.")
                    st.caption(
                        f"Derived LE Years (Override): {effective_life_expectancy_years:.2f}"
                    )
                else:
                    add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                    add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                    standard_remaining_life, standard_anchor = VehicleCalculation.derive_standard_from_additional_tables(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        claimant_age=float(effective_claimant_age),
                    )
                    if life_expectancy_basis == "standard":
                        effective_life_expectancy_years = float(standard_remaining_life)
                        add_anchor = float(standard_anchor)
                    else:
                        if impairment_input_type == "end_age":
                            effective_life_expectancy_years = float(impaired_end_age) - effective_claimant_age
                        else:
                            effective_life_expectancy_years = float(standard_remaining_life) - float(years_reduction)
                        if effective_life_expectancy_years <= 0:
                            raise ValueError("Impaired life expectancy years must be greater than 0.")
                        _, add_anchor = VehicleCalculation.derive_anchor_from_remaining_life(
                            zero_csv=add_zero,
                            point5_csv=add_p5,
                            remaining_life_years=effective_life_expectancy_years,
                        )
                    if life_multiplier_override <= 0:
                        life_multiplier = float(add_anchor)
                    life_expectancy_end_age = effective_claimant_age + effective_life_expectancy_years
                    st.caption(
                        f"Derived LE End Age (Additional Tables): {life_expectancy_end_age:.2f} | "
                        f"Derived LE Years: {effective_life_expectancy_years:.2f} | "
                        f"Life Multiplier Anchor(+0.5): {life_multiplier:.4f}"
                    )
            else:
                if life_expectancy_years is None:
                    raise ValueError("Life Expectancy Years is required in manual_years mode.")
                effective_life_expectancy_years = float(life_expectancy_years)
                life_expectancy_end_age = effective_claimant_age + effective_life_expectancy_years

            calc = VehicleCalculation(
                table35_vector=_load_table36_vector(table35_csv),
                table36_vector=_load_table36_vector(table36_csv),
            )
            result = calc.calculate(
                claimant_age=effective_claimant_age,
                age_at_start=float(age_at_start),
                age_at_end=float(age_at_end),
                life_expectancy_end_age=float(life_expectancy_end_age),
                life_expectancy_years=effective_life_expectancy_years,
                life_multiplier=float(life_multiplier),
                required_vehicle_cost=float(required_vehicle_cost),
                existing_vehicle_credit=float(existing_vehicle_credit),
                trade_in_value=float(trade_in_value),
                replacement_every_value=float(replacement_every_value),
                replacement_every_unit=str(replacement_every_unit),
                replacement_start_age=(None if float(replacement_start_age) <= 0 else float(replacement_start_age)),
                increased_insurance=float(increased_insurance),
                increased_running_costs=float(increased_running_costs),
                purchase_mortality_mode=str(purchase_mortality_mode),
            )
            unit_label = replacement_every_unit.lower()
            if unit_label.endswith("s"):
                unit_label = unit_label[:-1]
            st.success(SUCCESS_MSG)
            st.write(f"Initial Cost: {result['initial_total']:.8f} (Multiplier: {result['initial_multiplier']:.8f})")
            st.write(
                f"Future Replacements: {result['replacements_total']:.8f} "
                f"(calculated as {result['replacement_net_cost']:.8f} every {replacement_every_value:.8f} {unit_label} "
                f"for {result['replacement_count']} purchases; Multiplier: {result['replacements_multiplier']:.8f})"
            )
            st.write(
                f"Insurance Costs: {result['insurance_total']:.8f} "
                f"(at {increased_insurance:.8f} per year; Multiplier: {result['annual_multiplier']:.8f})"
            )
            st.write(
                f"Running Costs: {result['running_total']:.8f} "
                f"(at {increased_running_costs:.8f} per year; Multiplier: {result['annual_multiplier']:.8f})"
            )
            st.write(f"Total: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Earnings":
    st.subheader("Earnings")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="er_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="er_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="er_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="er_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="er_gender")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="er_le_basis",
            )
        else:
            life_expectancy_basis = "standard"
    with g3:
        impairment_live_until_age = 0.0
        years_reduction = 0.0
        impaired_multiplier_method = "find_appropriate_age"
        if le_input_mode == "derived_from_dates" and life_expectancy_basis == "impaired":
            impairment_input_type = st.selectbox(
                "Impairment Input Type",
                ["live_until_age", "years_reduction"],
                index=0,
                key="er_impairment_input_type",
                format_func=lambda v: "Live Until (Years Old)" if v == "live_until_age" else "Years Reduction from Standard",
            )
            if impairment_input_type == "live_until_age":
                impairment_live_until_age = st.number_input(
                    "Impairment (Live Until Age)",
                    value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="er_imp_live_until_age",
                )
            else:
                years_reduction = st.number_input(
                    "Years Reduction from Standard",
                    value=0.0,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="er_years_reduction",
                )
            impaired_multiplier_method = st.selectbox(
                "Impaired Multiplier Method",
                ["find_appropriate_age", "term_certain"],
                key="er_imp_method",
            )
        else:
            impairment_input_type = "live_until_age"

    st.markdown("#### Earnings Settings")
    rate_type_options = ["Net", "Gross (Employed)", "Gross (Self-employed)"]
    frequency_options = ["Per_Year", "Per_Month", "Per_Week", "Per_Day"]
    lbl_col, in_left, in_right = st.columns([1.15, 1.5, 1.5])

    # Loss Age(s)
    with lbl_col:
        st.markdown("**Loss Age(s)**")
    with in_left:
        age_at_start_text = st.text_input(
            "Start Date/Age of Loss",
            value="",
            placeholder="Age at Calculation",
            key="er_age_start_text",
            label_visibility="collapsed",
        )
    with in_right:
        age_at_end_text = st.text_input(
            "End Date/Age of Loss",
            value="",
            placeholder="Until Retirement",
            key="er_age_end_text",
            label_visibility="collapsed",
        )

    # But For row
    lbl_col, in_left, in_right = st.columns([1.15, 1.5, 1.5])
    with lbl_col:
        st.markdown("**Earnings (but for)**")
    with in_left:
        but_for_amount = st.number_input(
            "But For Amount",
            value=50000.0,
            min_value=0.0,
            step=100.0,
            key="er_but_for",
            label_visibility="collapsed",
        )
    with in_right:
        but_for_frequency = st.selectbox(
            "But For Frequency",
            frequency_options,
            index=0,
            key="er_bf_freq",
            label_visibility="collapsed",
        )

    # But For rate row
    lbl_col, in_left, in_right = st.columns([1.15, 1.5, 1.5])
    with lbl_col:
        st.markdown("**Rate**")
    with in_left:
        but_for_rate_type = st.selectbox(
            "But For Rate",
            rate_type_options,
            index=1,
            key="er_bf_rate_type",
            label_visibility="collapsed",
        )

    # Residual row
    lbl_col, in_left, in_right = st.columns([1.15, 1.5, 1.5])
    with lbl_col:
        st.markdown("**Earnings (residual)**")
    with in_left:
        residual_amount = st.number_input(
            "Residual Amount",
            value=15000.0,
            min_value=0.0,
            step=100.0,
            key="er_residual",
            label_visibility="collapsed",
        )
    with in_right:
        residual_frequency = st.selectbox(
            "Residual Frequency",
            frequency_options,
            index=0,
            key="er_res_freq",
            label_visibility="collapsed",
        )

    # Residual rate row
    lbl_col, in_left, in_right = st.columns([1.15, 1.5, 1.5])
    with lbl_col:
        st.markdown("**Rate**")
    with in_left:
        residual_rate_type = st.selectbox(
            "Residual Rate",
            rate_type_options,
            index=1,
            key="er_res_rate_type",
            label_visibility="collapsed",
        )

    # Employment + contingency section
    st.markdown("#### Contingency Factor")
    c1, c2, c3 = st.columns(3)
    preview_claimant_age = float(claimant_age) if claimant_age is not None else _decimal_age_years(dob=dob, as_of=calculation_date)
    working_status_options_before = ["Working Employed", "Working Unemployed", "Not Started Career", "Retired"]
    working_status_options_after = ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"]
    education_options = ["Level 3", "Level 2", "Level 1"]
    disability_options = ["Not Disabled", "Disabled"]
    with c1:
        region = st.selectbox("Region", ["England_Wales_NI"], key="er_region")
        ws_before = st.selectbox("Working Status (Before Injury)", working_status_options_before, index=0, key="er_ws_before")
        age_start_work_before = None
        if ws_before == "Not Started Career":
            age_start_work_before = st.number_input(
                "Age to Start Working (Before Injury)",
                value=48.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="er_age_start_before",
            )
        edu_before = st.selectbox("Education Level (Before Injury)", education_options, index=1, key="er_edu_before")
        dis_before = st.selectbox("Disability (Before Injury)", disability_options, index=0, key="er_dis_before")
        ret_mode_before = st.selectbox(
            "Retirement Age (Before Injury)",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="er_ret_mode_before",
        )
        ret_age_before = 68.0
        if ret_mode_before == "Specify retirement age":
            ret_age_before = st.number_input(
                "Specified Retirement Age (Before Injury)",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="er_ret_age_before",
            )
    with c2:
        ws_after = st.selectbox("Working Status (As Result)", working_status_options_after, index=1, key="er_ws_after")
        age_start_work_after = None
        if ws_after == "Not Started Career":
            age_start_work_after = st.number_input(
                "Age to Start Working (As Result)",
                value=55.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="er_age_start_after",
            )
        edu_after = st.selectbox("Education Level (As Result)", education_options, index=1, key="er_edu_after")
        dis_after = st.selectbox("Disability (As Result)", disability_options, index=0, key="er_dis_after")
        ret_mode_after = st.selectbox(
            "Retirement Age (As Result)",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="er_ret_mode_after",
        )
        ret_age_after = 68.0
        if ret_mode_after == "Specify retirement age":
            ret_age_after = st.number_input(
                "Specified Retirement Age (As Result)",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="er_ret_age_after",
            )
    with c3:
        calc_before = lookup_contingency(
            working_status=str(ws_before),
            education_level=str(edu_before),
            disability=str(dis_before),
            age_to_start_working=age_start_work_before,
            claimant_age=float(preview_claimant_age),
            gender=str(gender),
            retirement_age=float(ret_age_before),
        )
        calc_after = lookup_contingency(
            working_status=str(ws_after),
            education_level=str(edu_after),
            disability=str(dis_after),
            age_to_start_working=age_start_work_after,
            claimant_age=float(preview_claimant_age),
            gender=str(gender),
            retirement_age=float(ret_age_after),
        )
        st.caption(f"Calculated contingency (Before): {calc_before:.2f}")
        st.caption(f"Calculated contingency (As Result): {calc_after:.2f}")
        manual_cont_override = st.checkbox("Manual contingency override", value=False, key="er_manual_cont_override")
    if not manual_cont_override:
        st.session_state["er_cont_before"] = 0.0
        st.session_state["er_cont_after"] = 0.0
    c4, c5 = st.columns(2)
    with c4:
        contingency_before_injury = st.number_input(
            "Override Contingency Before Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="er_cont_before",
            disabled=(not manual_cont_override),
        )
    with c5:
        contingency_as_result = st.number_input(
            "Override Contingency As Result Of Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="er_cont_after",
            disabled=(not manual_cont_override),
        )

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    with o1:
        multiplier_mode = st.selectbox(
            "Multiplier Mode",
            ["auto", "manual", "additional"],
            index=0,
            key="er_multiplier_mode",
        )
    with o2:
        retirement_age = st.number_input("Retirement Age (table mapping)", value=68, min_value=50, max_value=80, step=1, key="er_ra")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="er_dr")

    if st.button("Compute Earnings", use_container_width=True):
        try:
            # Map PI-style loss-age inputs to age bounds (blank = default).
            start_raw = (age_at_start_text or "").strip()
            end_raw = (age_at_end_text or "").strip()
            age_at_start = float(start_raw) if start_raw else None
            age_at_end = float(end_raw) if end_raw else None
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
                effective_impairment_end_age = float(impairment_live_until_age) if float(impairment_live_until_age) > 0 else None
                effective_life_end_age = None
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(effective_claimant_age),
                )
                effective_life_end_age = float(effective_claimant_age + standard_remaining_life)
                st.caption(f"Derived LE End Age (Additional Tables): {effective_life_end_age:.2f}")
                if life_expectancy_basis == "impaired":
                    if impairment_input_type == "live_until_age":
                        effective_impairment_end_age = float(impairment_live_until_age) if float(impairment_live_until_age) > 0 else None
                    else:
                        derived_remaining_life = float(standard_remaining_life) - float(years_reduction)
                        if derived_remaining_life <= 0:
                            raise ValueError("Derived impaired life expectancy years must be greater than 0.")
                        effective_impairment_end_age = float(effective_claimant_age + derived_remaining_life)
                    if effective_impairment_end_age is not None:
                        st.caption(f"Derived Impairment End Age: {effective_impairment_end_age:.2f}")
                else:
                    effective_impairment_end_age = None

            if age_at_start is None:
                age_at_start = float(effective_claimant_age)
            # Stream-specific dynamic anchors:
            # 1) Build a shared base anchor from claimant/calculation start, delayed by
            #    before-injury start-working age when applicable.
            # 2) Residual stream inherits that base by default.
            # 3) Residual only diverges when as-result has explicit start-working age.
            base_start_anchor = float(age_at_start)
            if str(ws_before) == "Not Started Career" and age_start_work_before is not None:
                base_start_anchor = max(float(base_start_anchor), float(age_start_work_before))
            age_at_start_bf = float(base_start_anchor)
            age_at_start_res = float(base_start_anchor)
            if str(ws_after) == "Not Started Career" and age_start_work_after is not None:
                age_at_start_res = max(float(base_start_anchor), float(age_start_work_after))
            if age_at_end is None:
                age_at_end = float(retirement_age)
            if age_at_end <= age_at_start_bf and age_at_end <= age_at_start_res:
                raise ValueError("End age must be greater than start age.")

            # Map PI-style rate fields to existing calculation flags.
            but_for_is_net = but_for_rate_type == "Net"
            residual_is_net = residual_rate_type == "Net"
            gross_types = {but_for_rate_type, residual_rate_type}
            gross_types.discard("Net")
            if len(gross_types) > 1:
                raise ValueError("But For and Residual gross rate types must match (both employed or both self-employed).")
            if "Gross (Self-employed)" in gross_types:
                employment_type = "self_employed"
            else:
                employment_type = "employed"

            # PI-style dual-stream contingency:
            # - but-for stream uses before-injury contingency
            # - residual stream uses as-result contingency
            if manual_cont_override:
                contingency_before = float(contingency_before_injury)
                contingency_after = float(contingency_as_result)
            else:
                contingency_before = float(calc_before)
                contingency_after = float(calc_after)

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=int(retirement_age))
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            calc = EarningsCalculation(
                table36_vector=_load_table36_vector(paths.table36_csv),
                retirement_table=_load_retirement_table_for_paths(paths, discount_rate),
                whole_life_table=_load_whole_life_table(paths.whole_life_csv),
            )
            result_bf = calc.calculate(
                claimant_age=float(effective_claimant_age),
                age_at_start=float(age_at_start_bf),
                age_at_end=float(age_at_end),
                but_for_amount=float(but_for_amount),
                but_for_frequency=str(but_for_frequency),
                but_for_is_net=bool(but_for_is_net),
                residual_amount=0.0,
                residual_frequency=str(residual_frequency),
                residual_is_net=bool(residual_is_net),
                employment_type=str(employment_type),
                region=str(region),
                contingency_factor=float(contingency_before),
                multiplier_mode=str(multiplier_mode),
                additional_tables_csv=paths.additional_tables_csv,
                impairment_end_age=effective_impairment_end_age,
                impaired_multiplier_method=str(impaired_multiplier_method),
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                table35_csv=paths.table35_csv,
                retirement_table_full_csv=paths.retirement_table_csv,
                life_expectancy_end_age=effective_life_end_age,
            )
            result_res = calc.calculate(
                claimant_age=float(effective_claimant_age),
                age_at_start=float(age_at_start_res),
                age_at_end=float(age_at_end),
                but_for_amount=0.0,
                but_for_frequency=str(but_for_frequency),
                but_for_is_net=bool(but_for_is_net),
                residual_amount=float(residual_amount),
                residual_frequency=str(residual_frequency),
                residual_is_net=bool(residual_is_net),
                employment_type=str(employment_type),
                region=str(region),
                contingency_factor=float(contingency_after),
                multiplier_mode=str(multiplier_mode),
                additional_tables_csv=paths.additional_tables_csv,
                impairment_end_age=effective_impairment_end_age,
                impaired_multiplier_method=str(impaired_multiplier_method),
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                table35_csv=paths.table35_csv,
                retirement_table_full_csv=paths.retirement_table_csv,
                life_expectancy_end_age=effective_life_end_age,
            )
            total_loss = float(result_bf["total_loss"]) + float(result_res["total_loss"])
            result = {
                "period_years": float(result_bf["period_years"]),
                "but_for_annual_net": float(result_bf["but_for_annual_net"]),
                "residual_annual_net": float(result_res["residual_annual_net"]),
                "net_annual_loss": float(result_bf["but_for_annual_net"]) - float(result_res["residual_annual_net"]),
                "period_multiplier": float(result_bf["period_multiplier"]),
                "final_multiplier": float(result_bf["final_multiplier"]),
                "total_loss": float(total_loss),
                "multiplier_mode_used": str(result_bf["multiplier_mode_used"]),
                "trace": (
                    [
                        f"DEBUG: Dual-stream contingencies -> before={contingency_before:.8f}, after={contingency_after:.8f}",
                        f"DEBUG: Dual-stream starts -> but_for_start_age={age_at_start_bf:.8f}, residual_start_age={age_at_start_res:.8f}",
                    ]
                    + [f"DEBUG: BUT_FOR {line}" for line in result_bf.get("trace", [])]
                    + [f"DEBUG: RESIDUAL {line}" for line in result_res.get("trace", [])]
                    + [f"DEBUG: Dual-stream total = {result_bf['total_loss']:.8f} + ({result_res['total_loss']:.8f}) = {total_loss:.8f}"]
                ),
                "dual_stream": {
                    "but_for": result_bf,
                    "residual": result_res,
                },
            }
            st.success(SUCCESS_MSG)
            st.write(f"Duration Years: {result['period_years']:.8f}")
            st.write(f"But For Net Annual: {result['but_for_annual_net']:.8f}")
            st.write(f"Residual Net Annual: {result['residual_annual_net']:.8f}")
            st.write(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
            st.write(f"Multiplier Mode Used: {result['multiplier_mode_used']}")
            st.write(f"Period Multiplier: {result['period_multiplier']:.8f}")
            st.write(f"Final Multiplier: {result['final_multiplier']:.8f}")
            st.write(f"Total Loss: {result['total_loss']:.8f}")
            if "dual_stream" in result:
                bf = result["dual_stream"]["but_for"]
                rs = result["dual_stream"]["residual"]
                st.markdown("**Dual Stream Breakdown**")
                st.write(
                    f"But For -> Annual: {bf['but_for_annual_net']:.8f}, Multiplier: {bf['final_multiplier']:.8f}, "
                    f"Total: {bf['total_loss']:.8f}"
                )
                st.write(
                    f"Residual -> Annual: ({rs['residual_annual_net']:.8f}), Multiplier: {rs['final_multiplier']:.8f}, "
                    f"Total: ({abs(rs['total_loss']):.8f})"
                )
            if "phase_results" in result:
                st.markdown("**Auto-Split Phases**")
                for phase in result["phase_results"]:
                    st.write(
                        f"Phase {int(phase['phase'])}: Age {phase['age_at_start']:.2f}->{phase['age_at_end']:.2f} | "
                        f"Net {phase['net_annual_loss']:.8f} | Mult {phase['final_multiplier']:.8f} | Total {phase['total_loss']:.8f}"
                    )
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Earnings (Split)":
    st.subheader("Earnings (Split)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="ers_le_input_mode",
        )
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="ers_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="ers_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="ers_calc_date")
            claimant_age = None
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="ers_gender")
        region = st.selectbox("Region", ["England_Wales_NI"], key="ers_region")
    with g3:
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="ers_le_basis")
            if life_expectancy_basis == "impaired":
                impairment_input_type = st.selectbox(
                    "Impairment Input Type",
                    ["live_until_age", "years_reduction"],
                    index=0,
                    key="ers_imp_type",
                )
                if impairment_input_type == "live_until_age":
                    impairment_live_until_age = st.number_input(
                        "Impairment (Live Until Age)", value=66.0, step=0.01, format="%.2f", key="ers_imp_live_until"
                    )
                    years_reduction = 0.0
                else:
                    years_reduction = st.number_input(
                        "Impairment (Years Reduction)", value=5.0, step=0.01, format="%.2f", key="ers_imp_years_reduction"
                    )
                    impairment_live_until_age = 0.0
                impaired_multiplier_method = st.selectbox(
                    "Impaired Multiplier Method",
                    ["find_appropriate_age", "term_certain"],
                    key="ers_imp_method",
                )
            else:
                impairment_input_type = "live_until_age"
                impairment_live_until_age = 0.0
                years_reduction = 0.0
                impaired_multiplier_method = st.selectbox(
                    "Impaired Multiplier Method",
                    ["find_appropriate_age", "term_certain"],
                    key="ers_imp_method",
                    disabled=True,
                )
        else:
            life_expectancy_basis = "standard"
            impairment_input_type = "live_until_age"
            impairment_live_until_age = 0.0
            years_reduction = 0.0
            impaired_multiplier_method = st.selectbox(
                "Impaired Multiplier Method",
                ["find_appropriate_age", "term_certain"],
                key="ers_imp_method",
            )

    st.markdown("#### Earnings Split Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.text_input("Loss Age(s)", value="", placeholder="Age at Calculation", key="ers_loss_age_anchor")
        period_count = st.number_input("Loss Count", min_value=1, max_value=20, value=3, step=1, key="ers_count")
    with s2:
        earning_values = st.selectbox(
            "Earning Values",
            ["Net", "Gross (Employed)", "Gross (Self-employed)"],
            index=0,
            key="ers_earning_values",
        )
    with s3:
        residual_mode = st.selectbox("Residual Mode", ["Hide Residual", "Show Residual"], index=0, key="ers_residual_mode")

    frequency_options = ["Per_Year", "Per_Month", "Per_Week", "Per_Day"]
    periods = []
    current_start_age = None
    for i in range(int(period_count)):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 1.2, 1.0])
        with c1:
            description = st.text_input("Description" if i == 0 else "Description", value="", key=f"ers_desc_{i}", label_visibility="visible" if i == 0 else "collapsed")
        with c2:
            default_until = "" if i < int(period_count) - 1 else "Until Retirement"
            period_until_raw = st.text_input(
                "Period Until" if i == 0 else "Period Until",
                value=default_until,
                placeholder="Enter Age/Date",
                key=f"ers_until_{i}",
                label_visibility="visible" if i == 0 else "collapsed",
            )
        with c3:
            amount = st.number_input(
                "Earnings" if i == 0 else "Earnings",
                value=100000.0,
                min_value=0.0,
                step=100.0,
                key=f"ers_bf_{i}",
                label_visibility="visible" if i == 0 else "collapsed",
            )
        with c4:
            residual_amount = st.number_input(
                "Residual" if i == 0 else "Residual",
                value=0.0,
                min_value=0.0,
                step=100.0,
                key=f"ers_res_{i}",
                label_visibility="visible" if i == 0 else "collapsed",
                disabled=(residual_mode == "Hide Residual"),
            )
        with c5:
            freq = st.selectbox(
                "Frequency" if i == 0 else "Frequency",
                frequency_options,
                index=0,
                key=f"ers_freq_{i}",
                label_visibility="visible" if i == 0 else "collapsed",
            )

        periods.append(
            {
                "description": description,
                "period_until_raw": period_until_raw,
                "but_for_amount": float(amount),
                "but_for_frequency": str(freq),
                "residual_amount": (0.0 if residual_mode == "Hide Residual" else float(residual_amount)),
                "residual_frequency": str(freq),
            }
        )

    st.markdown("#### Contingency Factor")
    c1, c2 = st.columns(2)
    working_status_options = ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"]
    education_options = ["Level 3", "Level 2", "Level 1"]
    disability_options = ["Not Disabled", "Disabled"]
    claimant_age_for_cont = (float(claimant_age) if claimant_age is not None else _decimal_age_years(dob=dob, as_of=calculation_date))
    with c1:
        st.markdown("Before Injury")
        ws_before = st.selectbox("Working Status (Before Injury)", working_status_options, index=1, key="ers_ws_before")
        age_start_work_before = None
        if ws_before == "Not Started Career":
            age_start_work_before = st.number_input(
                "Age to Start Working (Before Injury)",
                value=48.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="ers_age_start_work_before",
            )
        edu_before = st.selectbox("Education Level (Before Injury)", education_options, index=1, key="ers_edu_before")
        dis_before = st.selectbox("Disability (Before Injury)", disability_options, index=0, key="ers_dis_before")
        calc_cont_before = lookup_contingency(
            working_status=str(ws_before),
            education_level=str(edu_before),
            disability=str(dis_before),
            age_to_start_working=age_start_work_before,
            claimant_age=claimant_age_for_cont,
            gender=str(gender),
        )
        st.caption(f"Calculated contingency (Before): {calc_cont_before:.2f}")
    with c2:
        st.markdown("As Result Of Injury")
        ws_after = st.selectbox("Working Status (As Result)", working_status_options, index=1, key="ers_ws_after")
        age_start_work_after = None
        if ws_after == "Not Started Career":
            age_start_work_after = st.number_input(
                "Age to Start Working (As Result)",
                value=55.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="ers_age_start_work_after",
            )
        edu_after = st.selectbox("Education Level (As Result)", education_options, index=1, key="ers_edu_after")
        dis_after = st.selectbox("Disability (As Result)", disability_options, index=0, key="ers_dis_after")
        calc_cont_after = lookup_contingency(
            working_status=str(ws_after),
            education_level=str(edu_after),
            disability=str(dis_after),
            age_to_start_working=age_start_work_after,
            claimant_age=claimant_age_for_cont,
            gender=str(gender),
        )
        st.caption(f"Calculated contingency (As Result): {calc_cont_after:.2f}")

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    with o1:
        manual_split_cont_override = st.checkbox("Manual contingency override", value=False, key="ers_manual_cont_override")
        if not manual_split_cont_override:
            st.session_state["ers_cont_before"] = 0.0
            st.session_state["ers_cont_after"] = 0.0
        multiplier_mode = st.selectbox(
            "Multiplier Mode",
            ["auto", "manual", "additional"],
            index=0,
            key="ers_multiplier_mode",
        )
    with o2:
        contingency_before_injury = st.number_input(
            "Override Contingency Before Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="ers_cont_before",
            disabled=(not manual_split_cont_override),
        )
        contingency_as_result = st.number_input(
            "Override Contingency As Result Of Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="ers_cont_after",
            disabled=(not manual_split_cont_override),
        )
        retirement_age = st.number_input("Retirement Age (table mapping)", value=68, min_value=50, max_value=80, step=1, key="ers_ra")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="ers_dr")
        require_contiguous = st.checkbox("Require contiguous periods", value=True, key="ers_contig")

    if st.button("Compute Earnings Split", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(effective_claimant_age),
                )
                effective_life_end_age = float(effective_claimant_age + standard_remaining_life)
                st.caption(f"Derived LE End Age (Additional Tables): {effective_life_end_age:.2f}")

            if le_input_mode == "derived_from_dates" and life_expectancy_basis == "impaired":
                if impairment_input_type == "live_until_age":
                    effective_impairment_end_age = float(impairment_live_until_age) if float(impairment_live_until_age) > 0 else None
                else:
                    add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                    add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                    standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                        zero_csv=add_zero,
                        point5_csv=add_p5,
                        claimant_age=float(effective_claimant_age),
                    )
                    derived_remaining_life = float(standard_remaining_life) - float(years_reduction)
                    if derived_remaining_life <= 0:
                        raise ValueError("Derived impaired life expectancy years must be greater than 0.")
                    effective_impairment_end_age = float(effective_claimant_age + derived_remaining_life)
                if effective_impairment_end_age is not None:
                    st.caption(f"Derived Impairment End Age: {effective_impairment_end_age:.2f}")
            else:
                effective_impairment_end_age = None

            if earning_values == "Gross (Self-employed)":
                employment_type = "self_employed"
                earnings_are_net = False
            elif earning_values == "Gross (Employed)":
                employment_type = "employed"
                earnings_are_net = False
            else:
                employment_type = "employed"
                earnings_are_net = True
            contingency_before = float(contingency_before_injury) if manual_split_cont_override else float(calc_cont_before)
            contingency_after = float(contingency_as_result) if manual_split_cont_override else float(calc_cont_after)

            parsed_periods = []
            loss_age_anchor_raw = str(st.session_state.get("ers_loss_age_anchor", "")).strip()
            if loss_age_anchor_raw == "" or loss_age_anchor_raw.lower() == "age at calculation":
                running_start_age = float(effective_claimant_age)
            else:
                try:
                    running_start_age = float(loss_age_anchor_raw)
                except ValueError as exc:
                    raise ValueError("Loss Age(s) start must be a numeric age or blank for Age at Calculation.") from exc
            for i, row in enumerate(periods):
                until_text = str(row["period_until_raw"]).strip()
                if until_text == "" or until_text.lower() == "until retirement":
                    end_age = float(retirement_age)
                else:
                    try:
                        end_age = float(until_text)
                    except ValueError as exc:
                        raise ValueError(f"Period {i + 1}: Period Until must be a numeric age or 'Until Retirement'.") from exc
                parsed_periods.append(
                    {
                        "age_at_start": running_start_age,
                        "age_at_end": float(end_age),
                        "but_for_amount": float(row["but_for_amount"]),
                        "but_for_frequency": str(row["but_for_frequency"]),
                        "but_for_is_net": bool(earnings_are_net),
                        "residual_amount": float(row["residual_amount"]),
                        "residual_frequency": str(row["residual_frequency"]),
                        "residual_is_net": bool(earnings_are_net),
                    }
                )
                running_start_age = float(end_age)

            # Stream-specific dynamic anchors:
            # 1) base start uses period start delayed by before-injury start-working age.
            # 2) residual inherits base start unless as-result has its own delayed start.
            parsed_periods_bf = []
            parsed_periods_res = []
            for phase in parsed_periods:
                base_start = float(phase["age_at_start"])
                if str(ws_before) == "Not Started Career" and age_start_work_before is not None:
                    base_start = max(base_start, float(age_start_work_before))
                residual_start = float(base_start)
                if str(ws_after) == "Not Started Career" and age_start_work_after is not None:
                    residual_start = max(float(base_start), float(age_start_work_after))

                phase_end = float(phase["age_at_end"])
                if phase_end <= base_start and phase_end <= residual_start:
                    continue

                if phase_end > base_start:
                    parsed_periods_bf.append(
                        {
                            "age_at_start": float(base_start),
                            "age_at_end": phase_end,
                            "but_for_amount": float(phase["but_for_amount"]),
                            "but_for_frequency": str(phase["but_for_frequency"]),
                            "but_for_is_net": bool(phase["but_for_is_net"]),
                            "residual_amount": 0.0,
                            "residual_frequency": str(phase["residual_frequency"]),
                            "residual_is_net": bool(phase["residual_is_net"]),
                        }
                    )
                if phase_end > residual_start:
                    parsed_periods_res.append(
                        {
                            "age_at_start": float(residual_start),
                            "age_at_end": phase_end,
                            "but_for_amount": 0.0,
                            "but_for_frequency": str(phase["but_for_frequency"]),
                            "but_for_is_net": bool(phase["but_for_is_net"]),
                            "residual_amount": float(phase["residual_amount"]),
                            "residual_frequency": str(phase["residual_frequency"]),
                            "residual_is_net": bool(phase["residual_is_net"]),
                        }
                    )

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=int(retirement_age))
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            base = EarningsCalculation(
                table36_vector=_load_table36_vector(paths.table36_csv),
                retirement_table=_load_retirement_table_for_paths(paths, discount_rate),
                whole_life_table=_load_whole_life_table(paths.whole_life_csv),
            )
            calc = EarningsSplitCalculation(earnings_calculation=base)
            result_bf = calc.calculate_split(
                claimant_age=float(effective_claimant_age),
                periods=parsed_periods_bf,
                employment_type=str(employment_type),
                region=str(region),
                contingency_factor=float(contingency_before),
                require_contiguous=bool(require_contiguous),
                multiplier_mode=str(multiplier_mode),
                additional_tables_csv=paths.additional_tables_csv,
                impairment_end_age=effective_impairment_end_age,
                impaired_multiplier_method=str(impaired_multiplier_method),
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                table35_csv=paths.table35_csv,
                retirement_table_full_csv=paths.retirement_table_csv,
            )
            result_res = calc.calculate_split(
                claimant_age=float(effective_claimant_age),
                periods=parsed_periods_res,
                employment_type=str(employment_type),
                region=str(region),
                contingency_factor=float(contingency_after),
                require_contiguous=bool(require_contiguous),
                multiplier_mode=str(multiplier_mode),
                additional_tables_csv=paths.additional_tables_csv,
                impairment_end_age=effective_impairment_end_age,
                impaired_multiplier_method=str(impaired_multiplier_method),
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                table35_csv=paths.table35_csv,
                retirement_table_full_csv=paths.retirement_table_csv,
            )
            merged_phases = []
            for phase in result_bf.get("phase_results", []):
                p = dict(phase)
                p["stream"] = "but_for"
                merged_phases.append(p)
            for phase in result_res.get("phase_results", []):
                p = dict(phase)
                p["stream"] = "residual"
                merged_phases.append(p)
            merged_phases.sort(key=lambda p: (float(p.get("age_at_start", 0.0)), 0 if p.get("stream") == "but_for" else 1))
            total_loss = float(result_bf.get("total_loss", 0.0)) + float(result_res.get("total_loss", 0.0))
            result = {
                "phase_results": merged_phases,
                "total_loss": total_loss,
                "trace": (
                    [
                        f"DEBUG: Dual-stream contingencies -> before={contingency_before:.8f}, after={contingency_after:.8f}",
                    ]
                    + [f"DEBUG: BUT_FOR {line}" for line in result_bf.get("trace", [])]
                    + [f"DEBUG: RESIDUAL {line}" for line in result_res.get("trace", [])]
                    + [f"DEBUG: Dual-stream total = {result_bf.get('total_loss', 0.0):.8f} + ({result_res.get('total_loss', 0.0):.8f}) = {total_loss:.8f}"]
                ),
            }
            st.success(SUCCESS_MSG)
            for phase in result["phase_results"]:
                st.write(
                    f"Phase {int(phase['phase'])} ({phase.get('stream', 'combined')}): "
                    f"Age {phase['age_at_start']:.2f}->{phase['age_at_end']:.2f} | "
                    f"Net {phase['net_annual_loss']:.8f} | Mult {phase['final_multiplier']:.8f} | Total {phase['total_loss']:.8f}"
                )
            st.write(f"Split Total Loss: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Earnings Award":
    st.subheader("Earnings Award")
    award_amount = st.number_input("Award Amount", value=10000.0, min_value=0.0, step=100.0, key="era_amount")
    if st.button("Compute Earnings Award", use_container_width=True):
        try:
            calc = EarningsAwardCalculation()
            result = calc.calculate(float(award_amount))
            st.success(SUCCESS_MSG)
            st.write(f"Total Award: {result['total_award']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Earnings (ASHE)":
    st.subheader("Earnings (ASHE)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="eas_le_input_mode",
        )
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="eas_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="eas_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="eas_calc_date")

    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="eas_gender")
        region = st.selectbox("Region", ["England_Wales_NI"], key="eas_calc_region")
        employment_type = st.selectbox("Employment Type", ["employed", "self_employed"], key="eas_employment_type")
        if le_input_mode == "derived_from_dates":
            life_expectancy_basis = st.selectbox(
                "Life Expectancy Basis",
                ["standard", "impaired"],
                index=0,
                key="eas_le_basis",
            )
        else:
            life_expectancy_basis = "standard"

    with g3:
        multiplier_mode = st.selectbox("Multiplier Mode", ["auto", "manual", "additional"], key="eas_multiplier_mode")
        if le_input_mode == "derived_from_dates" and life_expectancy_basis == "impaired":
            impairment_input_type = st.selectbox(
                "Impairment Input Type",
                ["end_age", "years_reduction"],
                index=0,
                key="eas_impairment_input_type",
            )
            if impairment_input_type == "end_age":
                impairment_end_age = st.number_input(
                    "Impairment End Age",
                    value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="eas_imp_end",
                )
                years_reduction = 0.0
            else:
                years_reduction = st.number_input(
                    "Years Reduction from Standard",
                    value=0.0,
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    key="eas_years_reduction",
                )
                impairment_end_age = 0.0
        else:
            impairment_input_type = "end_age"
            impairment_end_age = 0.0
            years_reduction = 0.0

    st.markdown("#### Contingency Factor")
    c1, c2 = st.columns(2)
    claimant_age_for_cont = (float(claimant_age) if claimant_age is not None else _decimal_age_years(dob=dob, as_of=calculation_date))
    with c1:
        st.markdown("Before Injury")
        ws_before = st.selectbox(
            "Working Status (Before Injury)",
            ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"],
            index=1,
            key="eas_ws_before",
        )
        age_start_work_before = None
        if ws_before == "Not Started Career":
            age_start_work_before = st.number_input(
                "Age to Start Working (Before Injury)",
                value=48.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="eas_age_start_work_before",
            )
        edu_before = st.selectbox("Education Level (Before Injury)", ["Level 3", "Level 2", "Level 1"], index=1, key="eas_edu_before")
        dis_before = st.selectbox("Disability (Before Injury)", ["Not Disabled", "Disabled"], index=0, key="eas_dis_before")
        ret_mode_before = st.selectbox(
            "Retirement Age (Before Injury)",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="eas_ret_mode_before",
        )
        ret_age_before = 68.0
        if ret_mode_before == "Specify retirement age":
            ret_age_before = st.number_input(
                "Specified Retirement Age (Before Injury)",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="eas_ret_age_before",
            )
        calc_cont_before = lookup_contingency(
            working_status=str(ws_before),
            education_level=str(edu_before),
            disability=str(dis_before),
            age_to_start_working=age_start_work_before,
            claimant_age=claimant_age_for_cont,
            gender=str(gender),
            retirement_age=float(ret_age_before),
        )
        st.caption(f"Calculated contingency (Before): {calc_cont_before:.2f}")
    with c2:
        st.markdown("As Result Of Injury")
        ws_after = st.selectbox(
            "Working Status (As Result)",
            ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"],
            index=1,
            key="eas_ws_after",
        )
        age_start_work_after = None
        if ws_after == "Not Started Career":
            age_start_work_after = st.number_input(
                "Age to Start Working (As Result)",
                value=55.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="eas_age_start_work_after",
            )
        edu_after = st.selectbox("Education Level (As Result)", ["Level 3", "Level 2", "Level 1"], index=1, key="eas_edu_after")
        dis_after = st.selectbox("Disability (As Result)", ["Not Disabled", "Disabled"], index=0, key="eas_dis_after")
        ret_mode_after = st.selectbox(
            "Retirement Age (As Result)",
            ["Use state retirement age", "Specify retirement age"],
            index=0,
            key="eas_ret_mode_after",
        )
        ret_age_after = 68.0
        if ret_mode_after == "Specify retirement age":
            ret_age_after = st.number_input(
                "Specified Retirement Age (As Result)",
                value=68.0,
                min_value=50.0,
                max_value=90.0,
                step=1.0,
                key="eas_ret_age_after",
            )
        calc_cont_after = lookup_contingency(
            working_status=str(ws_after),
            education_level=str(edu_after),
            disability=str(dis_after),
            age_to_start_working=age_start_work_after,
            claimant_age=claimant_age_for_cont,
            gender=str(gender),
            retirement_age=float(ret_age_after),
        )
        st.caption(f"Calculated contingency (As Result): {calc_cont_after:.2f}")
        manual_ashe_cont_override = st.checkbox("Manual contingency override", value=False, key="eas_manual_cont_override")
        if not manual_ashe_cont_override:
            st.session_state["eas_cont_before"] = 0.0
            st.session_state["eas_cont_after"] = 0.0
        cont_before = st.number_input(
            "Override Contingency Before Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="eas_cont_before",
            disabled=(not manual_ashe_cont_override),
        )
        cont_after = st.number_input(
            "Override Contingency As Result Of Injury",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="eas_cont_after",
            disabled=(not manual_ashe_cont_override),
        )

    st.markdown("#### Loss Configuration")
    l1, l2 = st.columns(2)
    with l1:
        age_at_start_text = st.text_input(
            "Loss Age(s) Start",
            value="",
            placeholder="Age at Calculation",
            key="eas_age_start_text",
        )
    with l2:
        age_at_end_text = st.text_input(
            "Loss Age(s) End",
            value="",
            placeholder="Until Retirement",
            key="eas_age_end_text",
        )
        retirement_age_mapping = st.number_input(
            "Retirement Age (table mapping)",
            value=68.0,
            min_value=50.0,
            max_value=90.0,
            step=1.0,
            key="eas_ret_age_map",
        )
    l3, _ = st.columns(2)
    with l3:
        life_expectancy_end_age = st.number_input(
            "Life Expectancy End Age (optional cap)",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.2f",
            key="eas_life_expectancy_end_age",
        )

    st.markdown("#### ASHE Selection")
    s1, s2 = st.columns(2)
    ashe_code_json_path = "tmp_ashe_codes.json"
    dataset_display = {
        "all_workers": "All workers",
        "all_male_workers": "All male workers",
        "all_female_workers": "All female workers",
        "all_full_time_workers": "All full-time workers",
        "all_part_time_workers": "All part-time workers",
        "male_full_time_workers": "Male full-time workers",
        "male_part_time_workers": "Male part-time workers",
        "female_full_time_workers": "Female full-time workers",
        "female_part_time_workers": "Female part-time workers",
    }
    with s1:
        ashe_year = st.selectbox("ASHE Year", [2025], key="eas_year")
        ashe_table_label = st.selectbox("ASHE Table", ashe_table_labels(), index=6, key="eas_table_label")
        ashe_dataset = st.selectbox(
            "ASHE Dataset",
            [
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
            key="eas_dataset",
            format_func=lambda v: dataset_display.get(v, v),
        )
        ashe_code_json_path = st.text_input(
            "ASHE Code JSON Path",
            value="tmp_ashe_codes.json",
            key="eas_code_json_path",
        )
    with s2:
        code_options = _load_ashe_pi_code_options(ashe_code_json_path)
        default_idx = 0
        for i, o in enumerate(code_options):
            if o["code"] == "1":
                default_idx = i
                break
        ashe_code_label = st.selectbox(
            "ASHE Code",
            [o["label"] for o in code_options],
            index=default_idx,
            key="eas_code_label",
        )
        selected_option = next(o for o in code_options if o["label"] == ashe_code_label)
        ashe_code = selected_option["code"]
        st.caption(f"Selected profession: {selected_option['profession']}")

    st.caption("Using employment profile for calculated scenario contingency.")

    with st.expander("ASHE Row Preview", expanded=True):
        ashe_preview_workbook = _resolve_ashe_table14_workbook_path(
            year=int(ashe_year),
            table_label=str(ashe_table_label),
            cv_variant=False,
        )
        ashe_preview_row = load_ashe_row(
            workbook_path=str(ashe_preview_workbook),
            dataset=str(ashe_dataset),
            code=str(ashe_code),
            region_prefix=None,
        )
        st.write(f"Description: {ashe_preview_row.description}")
        st.write(f"Jobs (thousands): {ashe_preview_row.jobs_thousands}")
        st.write(f"Median: {ashe_preview_row.median}")
        st.write(f"Mean: {ashe_preview_row.mean}")
        percentile_items = sorted(
            [(int(k), v) for k, v in ashe_preview_row.percentiles.items() if v is not None],
            key=lambda x: x[0],
        )
        if percentile_items:
            preview_row: Dict[str, float | int | None] = {
                "Job Numbers (thousands)": ashe_preview_row.jobs_thousands,
                "Median": ashe_preview_row.median,
                "Mean": ashe_preview_row.mean,
            }
            for p, v in percentile_items:
                preview_row[str(p)] = v
            st.markdown("**ASHE Row Values**")
            st.table([preview_row])
        ashe_mean_value = float(ashe_preview_row.mean) if ashe_preview_row.mean is not None else None
        ashe_median_value = float(ashe_preview_row.median) if ashe_preview_row.median is not None else None

    st.markdown("#### Earnings Inputs")
    e1, e2 = st.columns(2)
    with e1:
        but_for_source = st.selectbox(
            "But For Amount Source",
            ["Manual", "Mean", "Median"],
            index=0,
            key="eas_bf_source",
        )
        if but_for_source == "Manual":
            but_for_amount_manual = st.number_input(
                "Earnings (but for) Amount",
                value=0.0,
                min_value=0.0,
                step=100.0,
                key="eas_bf_amount_manual",
            )
        elif but_for_source == "Mean":
            if ashe_mean_value is None:
                st.warning("ASHE Mean is unavailable for current selection; falling back to 0.")
                but_for_amount_manual = 0.0
            else:
                but_for_amount_manual = float(ashe_mean_value)
            st.number_input(
                "Earnings (but for) Amount",
                value=float(but_for_amount_manual),
                min_value=0.0,
                step=100.0,
                key="eas_bf_amount_auto",
                disabled=True,
            )
        else:
            if ashe_median_value is None:
                st.warning("ASHE Median is unavailable for current selection; falling back to 0.")
                but_for_amount_manual = 0.0
            else:
                but_for_amount_manual = float(ashe_median_value)
            st.number_input(
                "Earnings (but for) Amount",
                value=float(but_for_amount_manual),
                min_value=0.0,
                step=100.0,
                key="eas_bf_amount_auto",
                disabled=True,
            )
        but_for_frequency = st.selectbox(
            "But For Frequency",
            ["Per_Year", "Per_Month", "Per_Week"],
            index=0,
            key="eas_bf_frequency",
        )
        but_for_rate = st.selectbox(
            "But For Rate",
            ["Gross (Employed)", "Gross (Self-employed)", "Net"],
            index=0,
            key="eas_bf_rate",
        )
    with e2:
        residual_source = st.selectbox(
            "Residual Amount Source",
            ["Manual", "Mean", "Median"],
            index=0,
            key="eas_res_source",
        )
        if residual_source == "Manual":
            residual_amount_manual = st.number_input(
                "Earnings (residual) Amount",
                value=0.0,
                min_value=0.0,
                step=100.0,
                key="eas_res_amount_manual",
            )
        elif residual_source == "Mean":
            if ashe_mean_value is None:
                st.warning("ASHE Mean is unavailable for current selection; falling back to 0.")
                residual_amount_manual = 0.0
            else:
                residual_amount_manual = float(ashe_mean_value)
            st.number_input(
                "Earnings (residual) Amount",
                value=float(residual_amount_manual),
                min_value=0.0,
                step=100.0,
                key="eas_res_amount_auto",
                disabled=True,
            )
        else:
            if ashe_median_value is None:
                st.warning("ASHE Median is unavailable for current selection; falling back to 0.")
                residual_amount_manual = 0.0
            else:
                residual_amount_manual = float(ashe_median_value)
            st.number_input(
                "Earnings (residual) Amount",
                value=float(residual_amount_manual),
                min_value=0.0,
                step=100.0,
                key="eas_res_amount_auto",
                disabled=True,
            )
        residual_frequency = st.selectbox(
            "Residual Frequency",
            ["Per_Year", "Per_Month", "Per_Week"],
            index=0,
            key="eas_res_frequency",
        )
        residual_rate = st.selectbox(
            "Residual Rate",
            ["Gross (Employed)", "Gross (Self-employed)", "Net"],
            index=0,
            key="eas_res_rate",
        )

    st.markdown("#### Data Sources")
    d1, d2 = st.columns(2)
    with d1:
        table36_csv = st.text_input("Table36 CSV", value="data/ogden8table36dr05.csv", key="eas_t36")
        retirement_table_csv = st.text_input("Retirement Table CSV", value="data/tables_3-18/table_11_male_ra68.csv", key="eas_ret")
        whole_life_csv = st.text_input("Whole Life CSV", value="data/ogden8table1dr05.csv", key="eas_whole")
    with d2:
        additional_tables_csv = st.text_input("Additional Tables CSV", value="data/additional_male05.csv", key="eas_additional_csv")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="eas_dr")

    with st.expander("Advanced Settings", expanded=False):
        use_manual_ashe_workbook = st.checkbox("Override ASHE Workbook Path", value=False, key="eas_manual_workbook_toggle")
        ashe_workbook_path_manual = st.text_input("ASHE Workbook Path (manual)", value="", key="eas_workbook_path")
        ashe_region_prefix = st.text_input("ASHE Region Prefix (optional)", value="", key="eas_region")
        round_final_multiplier_dp = st.number_input(
            "Round Final Multiplier (dp)",
            value=2,
            min_value=0,
            max_value=6,
            step=1,
            key="eas_round_mult_dp",
        )
        pi_round_intermediates_2dp = st.checkbox(
            "PI Intermediate Rounding (2dp)",
            value=True,
            key="eas_pi_intermediate_rounding",
        )

    if st.button("Compute Earnings (ASHE)", use_container_width=True):
        try:
            start_raw = (age_at_start_text or "").strip()
            end_raw = (age_at_end_text or "").strip()
            age_at_start = float(start_raw) if start_raw else None
            age_at_end = float(end_raw) if end_raw else None

            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
                if float(life_expectancy_end_age) > 0.0:
                    effective_life_end_age = float(life_expectancy_end_age)
                else:
                    effective_life_end_age = None
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(effective_claimant_age),
                )
                if life_expectancy_basis == "standard":
                    derived_life_end_age = float(effective_claimant_age + standard_remaining_life)
                else:
                    if impairment_input_type == "end_age":
                        if float(impairment_end_age) <= 0.0:
                            raise ValueError("Impairment End Age must be greater than 0.")
                        derived_life_end_age = float(impairment_end_age)
                    else:
                        derived_remaining_life = float(standard_remaining_life) - float(years_reduction)
                        if derived_remaining_life <= 0.0:
                            raise ValueError("Derived impaired life expectancy years must be greater than 0.")
                        derived_life_end_age = float(effective_claimant_age + derived_remaining_life)
                st.caption(f"Derived LE End Age: {derived_life_end_age:.2f}")
                if float(life_expectancy_end_age) > 0.0:
                    effective_life_end_age = float(life_expectancy_end_age)
                    st.caption(f"Manual LE End Age override applied: {effective_life_end_age:.2f}")
                else:
                    effective_life_end_age = float(derived_life_end_age)

            if age_at_start is None:
                age_at_start = float(effective_claimant_age)
            if age_at_end is None:
                age_at_end = float(retirement_age_mapping)

            ashe_workbook_path = (
                str(ashe_workbook_path_manual).strip()
                if use_manual_ashe_workbook
                else _resolve_ashe_table14_workbook_path(
                    year=int(ashe_year),
                    table_label=str(ashe_table_label),
                    cv_variant=False,
                )
            )
            but_for_source_map = {"Manual": None, "Mean": "mean", "Median": "median"}
            residual_source_map = {"Manual": None, "Mean": "mean", "Median": "median"}
            but_for_amount = float(but_for_amount_manual) if str(but_for_source) == "Manual" else None
            residual_amount = float(residual_amount_manual) if str(residual_source) == "Manual" else None
            but_for_ashe_field = but_for_source_map[str(but_for_source)] or "mean"
            residual_ashe_field = residual_source_map[str(residual_source)] or "mean"
            but_for_is_net = str(but_for_rate) == "Net"
            residual_is_net = str(residual_rate) == "Net"
            contingency_before = float(cont_before) if manual_ashe_cont_override else float(calc_cont_before)
            contingency_after = float(cont_after) if manual_ashe_cont_override else float(calc_cont_after)

            base = EarningsCalculation(
                table36_vector=_load_table36_vector(table36_csv),
                retirement_table=EarningsCalculation.load_retirement_table(retirement_table_csv, discount_rate),
                whole_life_table=_load_whole_life_table(whole_life_csv),
            )
            calc = EarningsAsheCalculation(earnings_calculation=base)
            # Match Earnings stream-start behavior for Not Started Career.
            base_start_anchor = float(age_at_start)
            if str(ws_before) == "Not Started Career" and age_start_work_before is not None:
                base_start_anchor = max(float(base_start_anchor), float(age_start_work_before))
            age_at_start_bf = float(base_start_anchor)
            age_at_start_res = float(base_start_anchor)
            if str(ws_after) == "Not Started Career" and age_start_work_after is not None:
                age_at_start_res = max(float(base_start_anchor), float(age_start_work_after))

            def _run_ashe_stream(
                *,
                stream_start_age: float,
                stream_label: str,
                bf_amount_value: float | None,
                res_amount_value: float | None,
                contingency_value: float,
            ) -> dict:
                phases = []
                stream_total = 0.0
                stream_trace = []

                def _calc_phase(phase_start: float, phase_end: float, phase_name: str):
                    return calc.calculate(
                        claimant_age=float(effective_claimant_age),
                        age_at_start=float(phase_start),
                        age_at_end=float(phase_end),
                        ashe_workbook_path=str(ashe_workbook_path),
                        ashe_dataset=str(ashe_dataset),
                        ashe_code=str(ashe_code),
                        ashe_region_prefix=(None if not str(ashe_region_prefix).strip() else str(ashe_region_prefix)),
                        but_for_amount=bf_amount_value,
                        but_for_ashe_field=str(but_for_ashe_field),
                        but_for_frequency=str(but_for_frequency),
                        but_for_is_net=bool(but_for_is_net),
                        residual_amount=res_amount_value,
                        residual_ashe_field=str(residual_ashe_field),
                        residual_frequency=str(residual_frequency),
                        residual_is_net=bool(residual_is_net),
                        employment_type=str(employment_type),
                        region=str(region),
                        contingency_factor=float(contingency_value),
                        multiplier_mode=str(multiplier_mode),
                        additional_tables_csv=str(additional_tables_csv),
                        life_expectancy_end_age=(None if effective_life_end_age is None else float(effective_life_end_age)),
                        round_final_multiplier_dp=int(round_final_multiplier_dp),
                        pi_round_intermediates_2dp=bool(pi_round_intermediates_2dp),
                    ), phase_name

                if stream_start_age > float(age_at_start):
                    pre_result, pre_name = _calc_phase(float(age_at_start), float(stream_start_age), "pre")
                    phases.append((pre_name, pre_result))
                    stream_total += float(pre_result["total_loss"])
                    stream_trace.extend([f"{pre_name.upper()} {line}" for line in pre_result.get("trace", [])])

                if float(age_at_end) > stream_start_age:
                    main_result, main_name = _calc_phase(float(stream_start_age), float(age_at_end), "main")
                    phases.append((main_name, main_result))
                    stream_total += float(main_result["total_loss"])
                    stream_trace.extend([f"{main_name.upper()} {line}" for line in main_result.get("trace", [])])

                if not phases:
                    raise ValueError(f"{stream_label} stream has no valid phase (start must be less than end).")

                return {
                    "stream": stream_label,
                    "phases": phases,
                    "trace": stream_trace,
                    "total_loss": stream_total,
                    "ashe_code_used": phases[-1][1].get("ashe_code_used"),
                    "but_for_amount_used": phases[-1][1].get("but_for_amount_used", 0.0),
                    "residual_amount_used": phases[-1][1].get("residual_amount_used", 0.0),
                    "period_multiplier": phases[-1][1].get("period_multiplier", 0.0),
                    "final_multiplier": phases[-1][1].get("final_multiplier", 0.0),
                }

            result_bf = _run_ashe_stream(
                stream_start_age=float(age_at_start_bf),
                stream_label="BUT_FOR",
                bf_amount_value=but_for_amount,
                res_amount_value=0.0,
                contingency_value=float(contingency_before),
            )
            result_res = _run_ashe_stream(
                stream_start_age=float(age_at_start_res),
                stream_label="RESIDUAL",
                bf_amount_value=0.0,
                res_amount_value=residual_amount,
                contingency_value=float(contingency_after),
            )
            total_loss = float(result_bf["total_loss"]) + float(result_res["total_loss"])
            st.success(SUCCESS_MSG)
            st.write(f"ASHE Workbook Used: {ashe_workbook_path}")
            st.write(f"ASHE Code Used: {result_bf['ashe_code_used']}")
            st.write(f"But For Amount Used: {result_bf['but_for_amount_used']:.8f}")
            st.write(f"Residual Amount Used: {result_res['residual_amount_used']:.8f}")
            for phase_name, phase_result in result_bf["phases"]:
                st.write(
                    f"But For {phase_name.title()} Multiplier: "
                    f"{float(phase_result.get('final_multiplier', 0.0)):.8f}"
                )
            for phase_name, phase_result in result_res["phases"]:
                st.write(
                    f"Residual {phase_name.title()} Multiplier: "
                    f"{float(phase_result.get('final_multiplier', 0.0)):.8f}"
                )
            st.write(f"Total Loss: {total_loss:.8f}")
            trace = (
                [f"DEBUG: Dual-stream contingencies -> before={contingency_before:.8f}, after={contingency_after:.8f}"]
                + [f"DEBUG: Dual-stream starts -> but_for_start_age={age_at_start_bf:.8f}, residual_start_age={age_at_start_res:.8f}"]
                + [f"DEBUG: BUT_FOR {line}" for line in result_bf.get("trace", [])]
                + [f"DEBUG: RESIDUAL {line}" for line in result_res.get("trace", [])]
                + [f"DEBUG: Dual-stream total = {result_bf['total_loss']:.8f} + ({result_res['total_loss']:.8f}) = {total_loss:.8f}"]
            )
            _render_trace(trace)
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "ASHE Lookup (Test)":
    st.subheader("ASHE Lookup (Test)")
    st.caption("PI-style ASHE lookup sandbox for code/table/dataset parity checks.")
    s1, s2 = st.columns(2)
    with s1:
        ashe_year = st.selectbox("Year", [2025], key="asht_year")
        ashe_table_label = st.selectbox("Table", ashe_table_labels(), index=6, key="asht_table_label")
        ashe_dataset = st.selectbox(
            "Dataset",
            [
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
            key="asht_dataset",
        )
        ashe_code_json_path = st.text_input("ASHE Code JSON Path", value="tmp_ashe_codes.json", key="asht_code_json_path")
    with s2:
        code_options = _load_ashe_pi_code_options(ashe_code_json_path)
        default_idx = 0
        for i, o in enumerate(code_options):
            if o["code"] == "1":
                default_idx = i
                break
        ashe_code_label = st.selectbox("ASHE Code", [o["label"] for o in code_options], index=default_idx, key="asht_code_label")
        selected_option = next(o for o in code_options if o["label"] == ashe_code_label)
        ashe_code = selected_option["code"]
        st.caption(f"Selected profession: {selected_option['profession']}")

    try:
        workbook_path = _resolve_ashe_table14_workbook_path(
            year=int(ashe_year),
            table_label=str(ashe_table_label),
            cv_variant=False,
        )
        # PI parity path: Table 14 direct code row (major/sub-major/unit).
        row = load_ashe_row(
            workbook_path=str(workbook_path),
            dataset=str(ashe_dataset),
            code=str(ashe_code),
            region_prefix=None,
        )
        source_used = "ASHE Table 14 (direct code row)"
    except Exception:
        # Fallback path: existing Table 15 prefix aggregation.
        workbook_path = resolve_ashe_workbook_path(
            year=int(ashe_year),
            table_label=str(ashe_table_label),
            soc_granularity=3,
            provisional=True,
            cv_variant=False,
        )
        row = load_ashe_row_by_prefix(
            workbook_path=str(workbook_path),
            dataset=str(ashe_dataset),
            code_prefix=str(ashe_code),
        )
        source_used = "ASHE Table 15 (prefix aggregation fallback)"
    try:
        st.markdown("#### Preview")
        st.write(f"Description: {row.description}")
        st.write(f"Job Numbers (thousands): {0.0 if row.jobs_thousands is None else row.jobs_thousands:.3f}")
        st.write(f"Median: {0.0 if row.median is None else row.median:.3f}")
        st.write(f"Mean: {0.0 if row.mean is None else row.mean:.3f}")
        preview = {
            "10": row.percentiles.get(10),
            "20": row.percentiles.get(20),
            "25": row.percentiles.get(25),
            "30": row.percentiles.get(30),
            "40": row.percentiles.get(40),
            "60": row.percentiles.get(60),
            "70": row.percentiles.get(70),
            "75": row.percentiles.get(75),
            "80": row.percentiles.get(80),
            "90": row.percentiles.get(90),
        }
        st.table([preview])
        st.caption(f"Workbook used: {workbook_path}")
        st.caption(f"Source mode: {source_used}")
    except Exception as exc:
        st.error(f"Error: {exc}")

elif selected_function == "Lost Years":
    st.subheader("Lost Years")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox(
            "Life Expectancy Input Mode",
            ["derived_from_dates", "manual_years"],
            index=0,
            key="ly_le_input_mode",
        )
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=45.4, step=0.01, format="%.2f", key="ly_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1980, 4, 23), key="ly_dob")
            calculation_date = _date_input("Calculation Date", value=date(2025, 9, 16), key="ly_calc_date")
            claimant_age = None
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="ly_gender")
        region = st.selectbox("Region", ["England_Wales_NI"], key="ly_region")
    with g3:
        current_life_expectancy_basis = st.selectbox(
            "Life Expectancy",
            ["Impaired", "Standard"],
            index=0,
            key="ly_current_basis",
        )
        impairment_end_age = st.number_input(
            "Impairment (Live Until Age)",
            value=54.0,
            step=0.01,
            format="%.2f",
            key="ly_impairment_end_age",
            disabled=(current_life_expectancy_basis != "Impaired"),
        )
        if current_life_expectancy_basis == "Impaired":
            current_multiplier_method = st.selectbox(
                "Current Multiplier",
                ["term_certain", "find_appropriate_age"],
                key="ly_current_method",
            )
            but_for_life_expectancy_basis = st.selectbox(
                "But For Life Expectancy",
                ["Standard", "Impaired"],
                index=0,
                key="ly_but_for_basis",
            )
            but_for_multiplier_method = st.selectbox(
                "But For Multiplier",
                ["term_certain", "find_appropriate_age"],
                key="ly_bf_method",
            )
        else:
            current_multiplier_method = "term_certain"
            but_for_life_expectancy_basis = "Standard"
            but_for_multiplier_method = "term_certain"
        retirement_age = st.number_input("Retirement Age (table mapping)", value=68, min_value=50, max_value=80, step=1, key="ly_ra")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="ly_dr")

    st.markdown("#### Lost Years Settings")
    s1, s2 = st.columns(2)
    with s1:
        loss_years_values = st.selectbox(
            "Loss Years Values",
            ["Net", "Gross (Employed)", "Gross (Self-employed)"],
            index=1,
            key="ly_values_type",
        )
    with s2:
        lost_years_rate_percent = st.number_input(
            "Loss Years Rate (%)", value=50.0, min_value=0.0, max_value=100.0, step=1.0, key="ly_rate"
        )

    tab_earnings, tab_pension = st.tabs(["Earnings", "Pension"])
    with tab_earnings:
        period_count = st.number_input("Loss Count", min_value=1, max_value=20, value=3, step=1, key="ly_count")
        earnings_rows: List[Dict[str, float | str]] = []
        for i in range(int(period_count)):
            c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.0])
            with c1:
                description = st.text_input(
                    "Description" if i == 0 else "Description",
                    value="",
                    key=f"ly_desc_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c2:
                default_until = "" if i < int(period_count) - 1 else "Until Retirement"
                if i == 0:
                    default_until = "55"
                elif i == 1:
                    default_until = "60"
                period_until = st.text_input(
                    "Period Until" if i == 0 else "Period Until",
                    value=default_until,
                    placeholder="Enter Age/Date",
                    key=f"ly_until_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c3:
                amount = st.number_input(
                    "Earnings" if i == 0 else "Earnings",
                    value=30000.0 if i == 0 else (35000.0 if i == 1 else 25000.0),
                    min_value=0.0,
                    step=100.0,
                    key=f"ly_amt_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c4:
                frequency = st.selectbox(
                    "Frequency" if i == 0 else "Frequency",
                    ["Per_Year", "Per_Month", "Per_Week", "Per_Day"],
                    index=0,
                    key=f"ly_freq_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            earnings_rows.append(
                {
                    "description": description,
                    "period_until": str(period_until),
                    "amount": float(amount),
                    "frequency": str(frequency),
                }
            )

    with tab_pension:
        pension_count = st.number_input("Pension Count", min_value=1, max_value=20, value=1, step=1, key="ly_pcount")
        pension_rows: List[Dict[str, float | str]] = []
        for i in range(int(pension_count)):
            c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.0, 1.0])
            with c1:
                pension_desc = st.text_input(
                    "Description" if i == 0 else "Description",
                    value="",
                    key=f"ly_pdesc_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c2:
                pension_start_raw = st.text_input(
                    "Pension Start" if i == 0 else "Pension Start",
                    value="From Retirement",
                    key=f"ly_pstart_raw_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c3:
                pension_lump = st.number_input(
                    "Lump Sum" if i == 0 else "Lump Sum",
                    value=2000000.0 if i == 0 else 0.0,
                    min_value=0.0,
                    step=1000.0,
                    key=f"ly_plump_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            with c4:
                pension_annual = st.number_input(
                    "Annual Value" if i == 0 else "Annual Value",
                    value=600000.0 if i == 0 else 0.0,
                    min_value=0.0,
                    step=1000.0,
                    key=f"ly_pannual_{i}",
                    label_visibility="visible" if i == 0 else "collapsed",
                )
            pension_rows.append(
                {
                    "description": pension_desc,
                    "start_raw": str(pension_start_raw),
                    "lump_sum": float(pension_lump),
                    "annual_value": float(pension_annual),
                }
            )

    st.markdown("#### Manual Overrides")
    o1, o2 = st.columns(2)
    with o1:
        use_manual_le_overrides = st.checkbox("Use Manual LE Overrides", value=False, key="ly_use_manual_le")
        if use_manual_le_overrides:
            current_life_end_age = st.number_input("Current Life End Age", value=54.0, step=0.01, format="%.2f", key="ly_current_end")
            but_for_remaining_life_years = st.number_input(
                "But For Remaining Life Years", value=39.208, step=0.001, format="%.3f", key="ly_bf_rem"
            )
        else:
            current_life_end_age = float(st.session_state.get("ly_current_end", 54.0))
            but_for_remaining_life_years = float(st.session_state.get("ly_bf_rem", 39.208))
            st.caption("Current Life End Age: derived from global life expectancy settings.")
            st.caption("But For Remaining Life Years: derived from global but-for life expectancy settings.")
    with o2:
        ws_ly = st.selectbox(
            "Working Status",
            ["Working Employed", "Working Unemployed", "Not Started Career", "Retired", "No return"],
            index=1,
            key="ly_ws",
        )
        age_start_work_ly = None
        if ws_ly == "Not Started Career":
            age_start_work_ly = st.number_input(
                "Age to Start Working",
                value=48.0,
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="ly_age_start_work",
            )
        edu_ly = st.selectbox("Education Level", ["Level 3", "Level 2", "Level 1"], index=1, key="ly_edu")
        dis_ly = st.selectbox("Disability", ["Not Disabled", "Disabled"], index=0, key="ly_dis")
        calc_cont_ly = lookup_contingency(
            working_status=str(ws_ly),
            education_level=str(edu_ly),
            disability=str(dis_ly),
            age_to_start_working=age_start_work_ly,
            claimant_age=(float(claimant_age) if claimant_age is not None else _decimal_age_years(dob=dob, as_of=calculation_date)),
            gender=str(gender),
        )
        st.caption(f"Calculated contingency: {calc_cont_ly:.2f}")
        manual_ly_cont_override = st.checkbox("Manual contingency override", value=False, key="ly_manual_cont_override")
        if not manual_ly_cont_override:
            st.session_state["ly_cont"] = 0.0
        contingency_factor = st.number_input(
            "Contingency Factor",
            value=0.0,
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key="ly_cont",
            disabled=(not manual_ly_cont_override),
        )
        use_manual_pension_end_age = st.checkbox("Override Pension Annual End Age", value=False, key="ly_override_pend")
        if use_manual_pension_end_age:
            pension_annual_end_age = st.number_input(
                "Pension Annual End Age",
                value=94.608,
                step=0.01,
                format="%.3f",
                key="ly_pend",
            )
        else:
            pension_annual_end_age = float(st.session_state.get("ly_pend", 94.608))
            st.caption("Pension Annual End Age: derived from claimant age + but-for remaining life years.")

    if st.button("Compute Lost Years", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")

            if not use_manual_le_overrides:
                add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
                add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
                standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                    zero_csv=add_zero,
                    point5_csv=add_p5,
                    claimant_age=float(effective_claimant_age),
                )
                if current_life_expectancy_basis == "Impaired":
                    current_life_end_age = float(impairment_end_age)
                else:
                    current_life_end_age = float(effective_claimant_age + standard_remaining_life)
                if but_for_life_expectancy_basis == "Standard":
                    but_for_remaining_life_years = float(standard_remaining_life)
                else:
                    but_for_remaining_life_years = max(0.0, float(current_life_end_age - effective_claimant_age))
                st.session_state["ly_current_end"] = float(current_life_end_age)
                st.session_state["ly_bf_rem"] = float(but_for_remaining_life_years)
                st.caption(
                    f"Derived Life Inputs: current_end_age={current_life_end_age:.2f} | "
                    f"but_for_remaining_years={but_for_remaining_life_years:.3f}"
                )
                st.caption("LE source: derived")
            else:
                st.caption("LE source: manual override")

            if not use_manual_pension_end_age:
                pension_annual_end_age = float(effective_claimant_age + float(but_for_remaining_life_years))
                st.session_state["ly_pend"] = float(pension_annual_end_age)
                st.caption(f"Derived Pension Annual End Age: {pension_annual_end_age:.3f}")
                st.caption("Pension end-age source: derived")
            else:
                st.caption("Pension end-age source: manual override")

            if loss_years_values == "Gross (Self-employed)":
                employment_type = "self_employed"
                values_are_net = False
            elif loss_years_values == "Gross (Employed)":
                employment_type = "employed"
                values_are_net = False
            else:
                employment_type = "employed"
                values_are_net = True

            earnings_periods: List[Dict[str, float | str | bool]] = []
            # PI Lost Years periods are anchored from current-life boundary, not claimant age.
            running_start_age = float(current_life_end_age)
            for i, row in enumerate(earnings_rows):
                until_raw = str(row["period_until"]).strip()
                if until_raw == "" or until_raw.lower() == "until retirement":
                    end_age = float(retirement_age)
                else:
                    try:
                        end_age = float(until_raw)
                    except ValueError as exc:
                        raise ValueError(f"Earnings row {i + 1}: Period Until must be a numeric age or 'Until Retirement'.") from exc
                earnings_periods.append(
                    {
                        "age_at_start": float(running_start_age),
                        "age_at_end": float(end_age),
                        "amount": float(row["amount"]),
                        "frequency": str(row["frequency"]),
                        "is_net": bool(values_are_net),
                    }
                )
                running_start_age = float(end_age)

            pension_starts: List[float] = []
            pension_lump_sum_amount = 0.0
            pension_annual_amount = 0.0
            for i, row in enumerate(pension_rows):
                start_raw = str(row["start_raw"]).strip().lower()
                if start_raw in {"", "from retirement", "retirement"}:
                    pstart = float(retirement_age)
                else:
                    try:
                        pstart = float(row["start_raw"])
                    except ValueError as exc:
                        raise ValueError(f"Pension row {i + 1}: Pension Start must be numeric age or 'From Retirement'.") from exc
                pension_starts.append(pstart)
                pension_lump_sum_amount += float(row["lump_sum"])
                pension_annual_amount += float(row["annual_value"])

            pension_lump_sum_age = float(min(pension_starts)) if pension_starts else float(retirement_age)
            pension_annual_start_age = float(min(pension_starts)) if pension_starts else float(retirement_age)
            effective_contingency_factor = float(contingency_factor) if manual_ly_cont_override else float(calc_cont_ly)

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=int(retirement_age))
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            base = EarningsCalculation(
                table36_vector=_load_table36_vector(paths.table36_csv),
                retirement_table=_load_retirement_table_for_paths(paths, discount_rate),
                whole_life_table=_load_whole_life_table(paths.whole_life_csv),
            )
            calc = LostYearsCalculation(earnings_calculation=base)
            result = calc.calculate(
                claimant_age=float(effective_claimant_age),
                current_life_end_age=float(current_life_end_age),
                but_for_remaining_life_years=float(but_for_remaining_life_years),
                but_for_multiplier_method=str(but_for_multiplier_method),
                current_multiplier_method=str(current_multiplier_method),
                lost_years_rate=float(lost_years_rate_percent) / 100.0,
                contingency_factor=float(effective_contingency_factor),
                earnings_periods=earnings_periods,
                pension_lump_sum_amount=float(pension_lump_sum_amount),
                pension_lump_sum_age=float(pension_lump_sum_age),
                pension_annual_amount=float(pension_annual_amount),
                pension_annual_start_age=float(pension_annual_start_age),
                pension_annual_end_age=float(pension_annual_end_age),
                employment_type=str(employment_type),
                region=str(region),
                values_are_net=bool(values_are_net),
                table35_csv=paths.table35_csv,
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
            )
            st.success(SUCCESS_MSG)
            st.write(f"But For Injury Life Multiplier: {result['but_for_injury_life_multiplier']:.8f}")
            st.write(f"Current Life Multiplier: {result['current_life_multiplier']:.8f}")
            st.write(f"Lost Years Multiplier: {result['lost_years_multiplier']:.8f}")
            st.write(f"Normalization Ratio: {result['normalization_ratio']:.8f}")
            for row in result["line_items"]:
                st.write(
                    f"Line {int(row['index'])}: annual_used={row['annual_used']:.8f}, "
                    f"multiplier={row['period_multiplier']:.8f}, total={row['total']:.8f}"
                )
            st.write(f"Total Future Loss: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Pension":
    st.subheader("Pension")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="pn_le_mode")
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=45.4, step=0.01, format="%.2f", key="pn_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1980, 4, 23), key="pn_dob")
            calculation_date = _date_input("Calculation Date", value=date(2025, 9, 16), key="pn_calc_date")
            claimant_age = None
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="pn_gender")
        region = st.selectbox("Region", ["England_Wales_NI"], key="pn_region")
        retirement_age = st.number_input("Retirement Age (table mapping)", value=68, min_value=50, max_value=80, step=1, key="pn_ra")
    with g3:
        life_expectancy_basis = st.selectbox("Life Expectancy", ["Impaired", "Standard"], index=0, key="pn_basis")
        impairment_end_age = st.number_input(
            "Impairment (Live Until Age)",
            value=72.0,
            step=0.01,
            format="%.2f",
            key="pn_imp_end",
            disabled=(life_expectancy_basis != "Impaired"),
        )
        pension_multiplier_method = "term_certain"
        but_for_life_expectancy = "Standard"
        but_for_multiplier_method = "term_certain"
        if life_expectancy_basis == "Impaired":
            pension_multiplier_method = st.selectbox(
                "Multiplier",
                ["term_certain", "find_appropriate_age"],
                index=0,
                key="pn_multiplier_global",
            )
            but_for_life_expectancy = st.selectbox(
                "But For Life Expectancy",
                ["Standard", "Impaired"],
                index=0,
                key="pn_but_for_le",
            )
            but_for_multiplier_method = st.selectbox(
                "But For Multiplier",
                ["term_certain", "find_appropriate_age"],
                index=0,
                key="pn_but_for_multiplier",
            )
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="pn_dr")

    st.markdown("#### Pension Settings")
    l1, l2 = st.columns(2)
    with l1:
        pension_loss_start_raw = st.text_input(
            "Loss Age(s) Start",
            value="From Retirement",
            key="pn_loss_start",
            help="Use 'From Retirement' (PI default) or a numeric age.",
        )
    with l2:
        pension_loss_end_raw = st.text_input(
            "Loss Age(s) End",
            value="Rest of Life",
            key="pn_loss_end",
            help="Use 'Rest of Life' (PI default) or a numeric age.",
        )
    freq_options = ["Per_Year", "Per_Month", "Per_Week", "Per_Day"]
    rate_type_options = ["Net", "Gross (Employed)", "Gross (Self-employed)"]

    p1, p2, p3 = st.columns([1.2, 1.2, 1.2])
    with p1:
        but_for_amount = st.number_input("Pension (but for)", value=500000.0, min_value=0.0, step=1000.0, key="pn_bf_amt")
    with p2:
        but_for_frequency = st.selectbox("Rate (But For Frequency)", freq_options, index=0, key="pn_bf_freq")
    with p3:
        but_for_rate_type = st.selectbox("Rate (But For Type)", rate_type_options, index=1, key="pn_bf_rate")

    p4, p5, p6 = st.columns([1.2, 1.2, 1.2])
    with p4:
        residual_amount = st.number_input("Pension (residual)", value=100000.0, min_value=0.0, step=1000.0, key="pn_res_amt")
    with p5:
        residual_frequency = st.selectbox("Rate (Residual Frequency)", freq_options, index=0, key="pn_res_freq")
    with p6:
        residual_rate_type = st.selectbox("Rate (Residual Type)", rate_type_options, index=2, key="pn_res_rate")

    st.markdown("#### Manual Overrides")
    st.caption("No pension-specific manual override is currently required.")

    if st.button("Compute Pension", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")
            # Keep editable Loss Age(s) for compatibility/testing.
            # PI default remains: From Retirement -> Rest of Life.
            start_raw = str(pension_loss_start_raw).strip().lower()
            end_raw = str(pension_loss_end_raw).strip().lower()
            if start_raw in {"", "from retirement", "retirement"}:
                effective_retirement_age = float(retirement_age)
            else:
                try:
                    effective_retirement_age = float(pension_loss_start_raw)
                except ValueError as exc:
                    raise ValueError("Loss Age(s) Start must be 'From Retirement' or numeric age.") from exc

            add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
            add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
            standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                zero_csv=add_zero,
                point5_csv=add_p5,
                claimant_age=float(effective_claimant_age),
            )
            standard_end_age = float(effective_claimant_age + float(standard_remaining_life))

            if life_expectancy_basis == "Impaired":
                basis_end_age = float(impairment_end_age)
            else:
                basis_end_age = float(standard_end_age)

            if end_raw in {"", "rest of life", "rol"}:
                effective_impairment_end_age = float(basis_end_age)
            else:
                try:
                    explicit_end = float(pension_loss_end_raw)
                except ValueError as exc:
                    raise ValueError("Loss Age(s) End must be 'Rest of Life' or numeric age.") from exc
                effective_impairment_end_age = min(float(explicit_end), float(basis_end_age))

            if effective_impairment_end_age <= effective_retirement_age:
                raise ValueError("Loss Age(s) End must be greater than Loss Age(s) Start.")

            freq_factor = {"Per_Year": 1.0, "Per_Month": 12.0, "Per_Week": 365.0 / 7.0, "Per_Day": 365.0}
            but_for_annual = float(but_for_amount) * float(freq_factor[str(but_for_frequency)])
            residual_annual = float(residual_amount) * float(freq_factor[str(residual_frequency)])

            but_for_is_net = str(but_for_rate_type) == "Net"
            residual_is_net = str(residual_rate_type) == "Net"
            but_for_employment_type = "self_employed" if str(but_for_rate_type) == "Gross (Self-employed)" else "employed"
            residual_employment_type = "self_employed" if str(residual_rate_type) == "Gross (Self-employed)" else "employed"

            paths = resolve_ogden_paths(
                gender=str(gender),
                discount_rate=float(discount_rate),
                retirement_age=int(round(float(effective_retirement_age))),
            )
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            base = EarningsCalculation(
                table36_vector=_load_table36_vector(paths.table36_csv),
                retirement_table=_load_retirement_table_for_paths(paths, discount_rate),
                whole_life_table=_load_whole_life_table(paths.whole_life_csv),
            )
            calc = PensionCalculation(earnings_calculation=base)
            active_multiplier_method = str(pension_multiplier_method)
            result = calc.calculate(
                claimant_age=float(effective_claimant_age),
                impairment_end_age=float(effective_impairment_end_age),
                but_for_amount=float(but_for_annual),
                but_for_is_net=bool(but_for_is_net),
                but_for_employment_type=str(but_for_employment_type),
                residual_amount=float(residual_annual),
                residual_is_net=bool(residual_is_net),
                residual_employment_type=str(residual_employment_type),
                region=str(region),
                multiplier_method=active_multiplier_method,
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                life_expectancy_basis=str(life_expectancy_basis),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Retirement Age: {result['retirement_age']:.8f}")
            st.write(f"Loss Age(s): start={effective_retirement_age:.2f}, end={effective_impairment_end_age:.2f}")
            st.write(f"Period Years: {result['period_years']:.8f}")
            st.write(f"But For Net Annual: {result['but_for_net_annual']:.8f}")
            st.write(f"Residual Net Annual: {result['residual_net_annual']:.8f}")
            st.write(f"Net Annual Loss: {result['net_annual_loss']:.8f}")
            st.write(f"But For Injury Life Multiplier: {result['but_for_life_multiplier']:.8f}")
            st.write(f"Mortality-To-Retirement Multiplier: {result['mortality_to_retirement_multiplier']:.8f}")
            st.write(f"Pension Multiplier: {result['pension_multiplier']:.8f}")
            st.write(f"Total Loss: {result['total_loss']:.8f}")
            st.caption(
                f"LE controls used: life_expectancy={life_expectancy_basis}, multiplier={active_multiplier_method}, "
                f"but_for_life_expectancy={but_for_life_expectancy}, but_for_multiplier={but_for_multiplier_method}"
            )
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Pension (Early receipt)":
    st.subheader("Pension (Early receipt)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="per_le_mode")
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=45.40, step=0.01, format="%.2f", key="per_claimant")
            calculation_date = None
            dob = None
        else:
            dob = _date_input("DOB", value=date(1980, 4, 23), key="per_dob")
            calculation_date = _date_input("Calculation Date", value=date(2025, 9, 16), key="per_calc_date")
            claimant_age = None
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="per_gender")
        region = st.selectbox("Region", ["England_Wales_NI"], key="per_region")
        retirement_age = st.number_input("Retirement Age (table mapping)", value=68, min_value=50, max_value=80, step=1, key="per_ret")
    with g3:
        life_expectancy_basis = st.selectbox("Life Expectancy", ["Impaired", "Standard"], index=0, key="per_basis")
        impairment_end_age = st.number_input(
            "Impairment (Live Until Age)",
            value=72.0,
            step=0.01,
            format="%.2f",
            key="per_imp",
            disabled=(life_expectancy_basis != "Impaired"),
        )
        multiplier_method = "term_certain"
        but_for_life_expectancy = "Standard"
        but_for_multiplier_method = "term_certain"
        if life_expectancy_basis == "Impaired":
            multiplier_method = st.selectbox(
                "Multiplier",
                ["term_certain", "find_appropriate_age"],
                index=0,
                key="per_mm_global",
            )
            but_for_life_expectancy = st.selectbox(
                "But For Life Expectancy",
                ["Standard", "Impaired"],
                index=0,
                key="per_but_for_le",
            )
            but_for_multiplier_method = st.selectbox(
                "But For Multiplier",
                ["term_certain", "find_appropriate_age"],
                index=0,
                key="per_but_for_mm",
            )
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="per_dr")

    st.markdown("#### Pension (Early receipt) Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        expected_lump_sum = st.number_input("Expected Lump Sum", value=250000.0, min_value=0.0, step=1000.0, key="per_el")
        actual_lump_sum = st.number_input("Actual Lump Sum", value=100000.0, min_value=0.0, step=1000.0, key="per_al")
        date_received = _date_input("Date Received", value=date(2026, 3, 4), key="per_date_received")
    rate_freq_options = ["Per_Year", "Per_Month", "Per_Week", "Per_Day", "Per_Hour"]
    rate_type_options = ["Net", "Gross (Employed)", "Gross (Self-employed)"]
    with s2:
        expected_annual_rate = st.number_input("Expected Annual Rate", value=55000.0, min_value=0.0, step=1000.0, key="per_ea")
        expected_annual_frequency = st.selectbox("Expected Annual Rate Period", rate_freq_options, index=0, key="per_ea_freq")
        expected_rate_type = st.selectbox("Expected Annual Rate Type", rate_type_options, index=0, key="per_ea_type")
    with s3:
        actual_annual_rate = st.number_input("Actual Annual Rate", value=35000.0, min_value=0.0, step=1000.0, key="per_aa")
        actual_annual_frequency = st.selectbox("Actual Annual Rate Period", rate_freq_options, index=0, key="per_aa_freq")
        actual_rate_type = st.selectbox("Actual Annual Rate Type", rate_type_options, index=0, key="per_aa_type")

    st.markdown("#### Manual Overrides")
    use_age_at_receipt_override = st.checkbox("Override Age at Receipt", value=False, key="per_use_receipt_override")
    if use_age_at_receipt_override:
        age_at_receipt_override = st.number_input("Age at Receipt (override)", value=45.863, step=0.001, format="%.3f", key="per_receipt_override")
    else:
        age_at_receipt_override = None

    if st.button("Compute Pension Early Receipt", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")

            if use_age_at_receipt_override and age_at_receipt_override is not None:
                effective_age_at_receipt = float(age_at_receipt_override)
                st.caption("Age at receipt source: manual override")
            else:
                if le_input_mode != "derived_from_dates":
                    raise ValueError("In manual_years mode, enable 'Override Age at Receipt' and provide a value.")
                effective_age_at_receipt = _decimal_age_years(dob=dob, as_of=date_received)
                st.caption(f"Derived Age at Receipt: {effective_age_at_receipt:.3f}")
                st.caption("Age at receipt source: derived from DOB and Date Received")

            add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
            add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
            standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                zero_csv=add_zero,
                point5_csv=add_p5,
                claimant_age=float(effective_claimant_age),
            )
            effective_life_end_age = float(effective_claimant_age + float(standard_remaining_life))
            if life_expectancy_basis == "Impaired":
                effective_life_end_age = float(impairment_end_age)
            st.caption(f"Derived LE End Age: {effective_life_end_age:.3f}")

            freq_factor = {"Per_Year": 1.0, "Per_Month": 12.0, "Per_Week": 365.0 / 7.0, "Per_Day": 365.0, "Per_Hour": 365.0 * 24.0}
            expected_annual_rate_effective = float(expected_annual_rate) * float(freq_factor[str(expected_annual_frequency)])
            actual_annual_rate_effective = float(actual_annual_rate) * float(freq_factor[str(actual_annual_frequency)])
            expected_annual_is_net = str(expected_rate_type) == "Net"
            actual_annual_is_net = str(actual_rate_type) == "Net"
            expected_annual_employment_type = "self_employed" if str(expected_rate_type) == "Gross (Self-employed)" else "employed"
            actual_annual_employment_type = "self_employed" if str(actual_rate_type) == "Gross (Self-employed)" else "employed"

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=int(round(float(retirement_age))))
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            base = EarningsCalculation(
                table36_vector=_load_table36_vector(paths.table36_csv),
                retirement_table=_load_retirement_table_for_paths(paths, discount_rate),
                whole_life_table=_load_whole_life_table(paths.whole_life_csv),
            )
            calc = PensionEarlyReceiptCalculation(earnings_calculation=base)
            result = calc.calculate(
                claimant_age=float(effective_claimant_age),
                age_at_receipt=float(effective_age_at_receipt),
                retirement_age=float(retirement_age),
                impairment_end_age=float(effective_life_end_age),
                expected_lump_sum=float(expected_lump_sum),
                actual_lump_sum=float(actual_lump_sum),
                expected_annual_rate=float(expected_annual_rate_effective),
                expected_annual_is_net=bool(expected_annual_is_net),
                expected_annual_employment_type=str(expected_annual_employment_type),
                actual_annual_rate=float(actual_annual_rate_effective),
                actual_annual_is_net=bool(actual_annual_is_net),
                actual_annual_employment_type=str(actual_annual_employment_type),
                region=str(region),
                multiplier_method=str(multiplier_method),
                additional_tables_point5_csv=paths.additional_tables_point5_csv,
                table35_csv=paths.table35_csv,
                additional_tables_zero_csv=paths.additional_tables_zero_csv,
                life_expectancy_basis=str(life_expectancy_basis),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Life Multiplier at Receipt: {result['life_multiplier_at_receipt']:.8f}")
            st.write(f"Multiplier to Retirement at Receipt: {result['multiplier_to_retirement_at_receipt']:.8f}")
            st.write(f"Longden Factor: {result['longden_factor']:.8f}")
            st.write(f"Years to Retirement: {result['years_to_retirement']:.8f}")
            st.write(f"Discount Factor: {result['discount_factor']:.8f}")
            st.write(f"Present Value Expected Lump Sum: {result['present_value_expected_lump_sum']:.8f}")
            st.write(f"Lump Sum Loss: {result['lump_sum_loss']:.8f}")
            st.write(f"Annual Loss: {result['annual_loss']:.8f}")
            st.write(f"Pension Multiplier: {result['pension_multiplier']:.8f}")
            st.write(f"Annual Line Total: {result['annual_line_total']:.8f}")
            st.write(f"Total Loss: {result['total_loss']:.8f}")
            st.caption(
                f"LE controls used: life_expectancy={life_expectancy_basis}, multiplier={multiplier_method}, "
                f"but_for_life_expectancy={but_for_life_expectancy}, but_for_multiplier={but_for_multiplier_method}"
            )
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Accommodation (RvJ)":
    st.subheader("Accommodation (RvJ)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="arvj_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="arvj_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="arvj_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="arvj_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="arvj_gender")
        life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="arvj_le_basis")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="arvj_dr")
    with g3:
        impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="arvj_imp_type", disabled=(life_expectancy_basis != "impaired"))
        impaired_end_age = st.number_input("Impaired End Age", value=72.00, min_value=0.01, step=0.01, format="%.2f", key="arvj_imp_end", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "end_age"))
        years_reduction = st.number_input("Years Reduction from Standard", value=0.0, min_value=0.0, step=0.01, format="%.2f", key="arvj_years_reduction", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "years_reduction"))

    st.markdown("#### RvJ Settings")
    s1, s2, s3 = st.columns(3)
    with s1:
        age_at_start_text = st.text_input("Loss Age(s) Start", value="", placeholder="Age at Calculation", key="arvj_age_start")
        age_at_end_text = st.text_input("Loss Age(s) End", value="", placeholder="Rest of Life", key="arvj_age_end")
        cost_required_property = st.number_input("Cost of Required Property", value=1000000.0, min_value=0.0, step=1000.0, key="arvj_req")
    with s2:
        allowance_existing = st.number_input("Allowance for Existing", value=20000.0, min_value=0.0, step=1000.0, key="arvj_existing")
        cost_adaptations = st.number_input("Cost of Adaptations", value=100000.0, min_value=0.0, step=1000.0, key="arvj_adapt")
        betterment = st.number_input("Betterment", value=60000.0, min_value=0.0, step=1000.0, key="arvj_betterment")
    with s3:
        use_discount_rate = st.checkbox("Use Discount Rate", value=True, key="arvj_use_dr")
        custom_rate_percent = st.number_input("Custom Rate (%)", value=1.0, min_value=0.0, step=0.1, format="%.2f", key="arvj_custom_rate", disabled=use_discount_rate)
        increased_running_costs = st.number_input("Increased Running Costs", value=10000.0, min_value=0.0, step=100.0, key="arvj_running")

    st.markdown("#### Manual Overrides")
    life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f", key="arvj_lm_override")
    use_life_end_age_override = st.checkbox("Override Life Expectancy End Age", value=False, key="arvj_use_le_end")
    life_end_age_override = None
    if use_life_end_age_override:
        life_end_age_override = st.number_input("Life Expectancy End Age (Override)", value=84.69, min_value=0.01, step=0.01, format="%.2f", key="arvj_le_end")

    if st.button("Compute Accommodation (RvJ)", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")

            add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
            add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
            standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                zero_csv=add_zero, point5_csv=add_p5, claimant_age=float(effective_claimant_age)
            )
            if life_expectancy_basis == "standard":
                effective_life_end_age = float(effective_claimant_age + standard_remaining_life)
            else:
                if impairment_input_type == "end_age":
                    effective_life_end_age = float(impaired_end_age)
                else:
                    effective_life_end_age = float(effective_claimant_age + standard_remaining_life - float(years_reduction))
            if life_end_age_override is not None:
                effective_life_end_age = float(life_end_age_override)

            age_at_start = float(effective_claimant_age) if str(age_at_start_text).strip() == "" else float(age_at_start_text)
            if str(age_at_end_text).strip() == "" or str(age_at_end_text).strip().lower() == "rest of life":
                age_at_end = float(effective_life_end_age)
            else:
                age_at_end = min(float(age_at_end_text), float(effective_life_end_age))

            life_expectancy_years = float(effective_life_end_age - effective_claimant_age)
            if life_expectancy_years <= 0:
                raise ValueError("Derived life expectancy years must be greater than 0.")

            if life_multiplier_override > 0:
                life_multiplier = float(life_multiplier_override)
            else:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=float(effective_claimant_age), gender=str(gender))

            rate_to_apply = float(discount_rate) / 100.0 if use_discount_rate else float(custom_rate_percent) / 100.0
            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=68)
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)

            calc = AccommodationRvJCalculation(
                care_multiplier_calculation=CareMultiplierCalculation(table36_vector=_load_table36_vector(paths.table36_csv)),
                table35_vector=_load_table36_vector(paths.table35_csv),
            )
            result = calc.calculate(
                claimant_age=float(effective_claimant_age),
                age_at_start=float(age_at_start),
                age_at_end=float(age_at_end),
                life_expectancy_years=float(life_expectancy_years),
                life_multiplier=float(life_multiplier),
                cost_required_property=float(cost_required_property),
                allowance_existing=float(allowance_existing),
                cost_adaptations=float(cost_adaptations),
                betterment=float(betterment),
                increased_running_costs=float(increased_running_costs),
                rate_to_apply=float(rate_to_apply),
            )
            st.success(SUCCESS_MSG)
            st.write(f"Derived LE End Age: {effective_life_end_age:.8f}")
            st.write(f"Ongoing Capital Cost Annual: {result['ongoing_annual']:.8f}")
            st.write(f"Ongoing Multiplier: {result['ongoing_multiplier']:.8f}")
            st.write(f"Ongoing Capital Cost Total: {result['ongoing_total']:.8f}")
            st.write(f"Adaptation Net: {result['adaptation_net']:.8f}")
            st.write(f"Adaptation Discount Factor: {result['discount_factor']:.8f}")
            st.write(f"Adaptation Total: {result['adaptation_total']:.8f}")
            st.write(f"Total: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")

elif selected_function == "Accommodation (Swift v Carpenter)":
    st.subheader("Accommodation (Swift v Carpenter)")
    st.markdown("#### Global Settings")
    g1, g2, g3 = st.columns(3)
    with g1:
        le_input_mode = st.selectbox("Life Expectancy Input Mode", ["derived_from_dates", "manual_years"], index=0, key="asc_le_mode")
        claimant_age = None
        if le_input_mode == "manual_years":
            claimant_age = st.number_input("Claimant Age", value=42.76, step=0.01, format="%.2f", key="asc_claimant_age")
        else:
            dob = _date_input("DOB", value=date(1983, 6, 9), key="asc_dob")
            calculation_date = _date_input("Calculation Date", value=date(2026, 3, 13), key="asc_calc_date")
    with g2:
        gender = st.selectbox("Gender", ["male", "female"], key="asc_gender")
        life_expectancy_basis = st.selectbox("Life Expectancy Basis", ["standard", "impaired"], index=0, key="asc_le_basis")
        discount_rate = st.number_input("Discount Rate Column", value=0.5, step=0.25, format="%.2f", key="asc_dr")
    with g3:
        impairment_input_type = st.selectbox("Impairment Input Type", ["end_age", "years_reduction"], index=0, key="asc_imp_type", disabled=(life_expectancy_basis != "impaired"))
        impaired_end_age = st.number_input("Impaired End Age", value=72.00, min_value=0.01, step=0.01, format="%.2f", key="asc_imp_end", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "end_age"))
        years_reduction = st.number_input("Years Reduction from Standard", value=0.0, min_value=0.0, step=0.01, format="%.2f", key="asc_years_reduction", disabled=(life_expectancy_basis != "impaired" or impairment_input_type != "years_reduction"))

    st.markdown("#### Swift v Carpenter Settings")
    s1, s2 = st.columns(2)
    with s1:
        age_at_start_text = st.text_input("Loss Age(s) Start", value="", placeholder="Age at Calculation", key="asc_age_start")
        age_at_end_text = st.text_input("Loss Age(s) End", value="", placeholder="Rest of Life", key="asc_age_end")
        cost_required_property = st.number_input("Cost of Required Property", value=500000.0, min_value=0.0, step=1000.0, key="asc_req")
    with s2:
        allowance_existing = st.number_input("Allowance for Existing", value=30000.0, min_value=0.0, step=1000.0, key="asc_existing")
        rate_to_apply_percent = st.number_input("Rate to Apply (%)", value=5.0, min_value=0.0, step=0.1, format="%.2f", key="asc_rate")

    if st.button("Compute Accommodation (Swift v Carpenter)", use_container_width=True):
        try:
            if le_input_mode == "manual_years":
                if claimant_age is None:
                    raise ValueError("Claimant Age is required in manual_years mode.")
                effective_claimant_age = float(claimant_age)
            else:
                effective_claimant_age = _decimal_age_years(dob=dob, as_of=calculation_date)
                st.caption(f"Derived Claimant Age: {effective_claimant_age:.2f}")

            add_zero = "data/ogden8_additional_males_0.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_0.csv"
            add_p5 = "data/ogden8_additional_males_05.csv" if str(gender).lower() == "male" else "data/ogden8_additional_females_05.csv"
            standard_remaining_life, _ = VehicleCalculation.derive_standard_from_additional_tables(
                zero_csv=add_zero, point5_csv=add_p5, claimant_age=float(effective_claimant_age)
            )
            if life_expectancy_basis == "standard":
                effective_life_end_age = float(effective_claimant_age + standard_remaining_life)
            else:
                if impairment_input_type == "end_age":
                    effective_life_end_age = float(impaired_end_age)
                else:
                    effective_life_end_age = float(effective_claimant_age + standard_remaining_life - float(years_reduction))

            age_at_start = float(effective_claimant_age) if str(age_at_start_text).strip() == "" else float(age_at_start_text)
            if str(age_at_end_text).strip() == "" or str(age_at_end_text).strip().lower() == "rest of life":
                age_at_end = float(effective_life_end_age)
            else:
                age_at_end = min(float(age_at_end_text), float(effective_life_end_age))

            paths = resolve_ogden_paths(gender=str(gender), discount_rate=float(discount_rate), retirement_age=68)
            if paths.warning:
                st.warning(paths.warning)
            _show_tables_used("CSV Used", paths)
            calc = AccommodationSwiftCarpenterCalculation(
                table35_vector=_load_table36_vector(paths.table35_csv),
            )
            result = calc.calculate(
                claimant_age=float(effective_claimant_age),
                age_at_start=float(age_at_start),
                age_at_end=float(age_at_end),
                cost_required_property=float(cost_required_property),
                allowance_existing=float(allowance_existing),
                reversionary_rate=float(rate_to_apply_percent) / 100.0,
            )
            st.success(SUCCESS_MSG)
            st.write(f"Derived LE End Age: {effective_life_end_age:.8f}")
            st.write(f"Net Capital: {result['net_capital']:.8f}")
            st.write(f"Discount Multiplier (at rate): {result['discount_multiplier']:.8f}")
            st.write(f"Reversionary Interest: {result['reversionary_interest']:.8f}")
            st.write(f"Life Interest: {result['life_interest']:.8f}")
            st.write(f"Discount Early Receipt Factor: {result['discount_factor']:.8f}")
            st.write(f"Total: {result['total_loss']:.8f}")
            _render_trace(result["trace"])
        except Exception as exc:
            st.error(f"Error: {exc}")
