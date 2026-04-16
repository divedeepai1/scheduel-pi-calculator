import csv
import json
from typing import Dict, List, Tuple

import streamlit as st

from formulas import (
    CareCalculation,
    CareSplitCalculation,
    CareMultiplierCalculation,
    CareClaimCalculation,
    CareWholeLifeCalculation,
)

SUCCESS_MSG = "Calculated successfully."


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


def _base_inputs(key_prefix: str) -> Dict[str, float]:
    col1, col2, col3 = st.columns(3)
    with col1:
        number_of_hours = st.number_input(
            "Number of Hours", value=20.0, min_value=0.0, step=1.0, key=f"{key_prefix}_hours"
        )
        percentage_less = st.number_input(
            "Less (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f"{key_prefix}_less"
        )
    with col2:
        time_increment = st.selectbox(
            "Time Increment",
            [
                "Over_Period",
                "Per_Day",
                "Per_Week",
                "Per_Month",
                "Per_Year",
                "Per_Weekday",
                "Per_Weekend",
                "Per_Monday",
                "Per_Tuesday",
                "Per_Wednesday",
                "Per_Thursday",
                "Per_Friday",
                "Per_Saturday",
                "Per_Sunday",
                "Per_Day_Specify",
                "Per_Week_Specify",
                "Per_Month_Specify",
                "Per_Weekday_Specify",
                "Per_Weekend_Specify",
            ],
            index=2,
            key=f"{key_prefix}_time_increment",
        )
        care_rate_type = st.selectbox(
            "Care Rate Type",
            [
                "Aggregate_Rate",
                "Basic_Rate",
                "Evening_Rate",
                "Weekend_Rate",
                "Saturday_Rate",
                "Sunday_Rate",
                "Aggregate_Day_Rate",
                "Specify_Rate",
            ],
            index=1,
            key=f"{key_prefix}_care_rate_type",
        )
    with col3:
        rate_value = st.number_input(
            "Rate Value", value=12.69, min_value=0.0, step=0.01, format="%.4f", key=f"{key_prefix}_rate_value"
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
            "Specify Increment",
            ["Over_Period_Specify", "Per_Week_Specify", "Per_Month_Specify", "Per_Year_Specify"],
            key=f"{key_prefix}_specify_increment",
        )
        if time_increment == "Per_Day_Specify":
            number_days_specify = st.number_input(
                "Number Days Specify", value=1.0, min_value=0.0, step=1.0, key=f"{key_prefix}_days_specify"
            )
        if time_increment in {"Per_Week_Specify", "Per_Weekday_Specify", "Per_Weekend_Specify"}:
            number_weeks_specify = st.number_input(
                "Number Weeks Specify", value=1.0, min_value=0.0, step=1.0, key=f"{key_prefix}_weeks_specify"
            )
        if time_increment == "Per_Month_Specify":
            number_months_specify = st.number_input(
                "Number Months Specify", value=1.0, min_value=0.0, step=1.0, key=f"{key_prefix}_months_specify"
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


st.set_page_config(page_title="Scheduel Calculator - Care", layout="wide")
st.title("Scheduel Calculator - Care")
st.caption("Streamlit interface for care annualisation and care claim calculations.")

tab_annual, tab_claim, tab_split = st.tabs(
    ["Care Annualisation", "Care Claim (Full)", "Care Split (JSON)"]
)

with tab_annual:
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
            start_date = str(st.date_input("Start Date"))
        with c2:
            end_date = str(st.date_input("End Date"))
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

with tab_claim:
    st.subheader("Care Claim (Annualisation + Multiplier)")
    c1, c2, c3 = st.columns(3)
    with c1:
        age_at_start = st.number_input("Age at Start", value=67.0, step=0.01, format="%.2f", key="claim_age_start")
        age_at_end = st.number_input("Age at End", value=80.0, step=0.01, format="%.2f", key="claim_age_end")
        claimant_age = st.number_input("Claimant Age", value=65.68, step=0.01, format="%.2f")
    with c2:
        gender = st.selectbox("Gender", ["male", "female"])
        life_expectancy_years = st.number_input("Life Expectancy Years", value=19.67, step=0.01, format="%.2f")
        term_start_override = st.number_input("Term Start Override (optional)", value=0.0, step=0.01, format="%.2f")
    with c3:
        term_end_override = st.number_input("Term End Override (optional)", value=0.0, step=0.01, format="%.2f")
        life_multiplier_override = st.number_input("Life Multiplier Override (optional)", value=0.0, step=0.0001, format="%.4f")
        table36_csv = st.text_input("Table36 CSV Path", value="data/ogden8table36dr05.csv")

    payload = _base_inputs("claim")
    if st.button("Compute Care Claim", use_container_width=True):
        try:
            term_start_years = term_start_override if term_start_override > 0 else (age_at_start - claimant_age)
            term_end_years = term_end_override if term_end_override > 0 else (age_at_end - claimant_age)

            if life_multiplier_override > 0:
                life_multiplier = life_multiplier_override
            else:
                wl = CareWholeLifeCalculation(
                    male_table=_load_whole_life_table("data/ogden8table1dr05.csv"),
                    female_table=_load_whole_life_table("data/ogden8table2dr05.csv"),
                )
                life_multiplier = wl.multiplier(claimant_age=claimant_age, gender=gender)

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
                life_expectancy_years=life_expectancy_years,
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

with tab_split:
    st.subheader("Care Split")
    st.caption("Paste a JSON array of period objects (same shape as data/sample_periods.json).")
    default_json = """[
  {"age_at_start": 67, "age_at_end": 70, "number_of_hours": 20, "time_increment": "Per_Week", "care_rate_type": "Basic_Rate", "rate_values": {"Basic_Rate": 12.69}},
  {"age_at_start": 70, "age_at_end": 80, "number_of_hours": 30, "time_increment": "Per_Week", "care_rate_type": "Basic_Rate", "rate_values": {"Basic_Rate": 12.69}}
]"""
    period_text = st.text_area("Periods JSON", value=default_json, height=220)
    require_contiguous = st.checkbox("Require contiguous periods", value=True)
    if st.button("Compute Care Split", use_container_width=True):
        try:
            periods = json.loads(period_text)
            if not isinstance(periods, list):
                raise ValueError("Periods JSON must be an array.")
            split_calc = CareSplitCalculation(care_calculation=CareCalculation())
            result = split_calc.calculate_split(
                periods=periods,
                require_contiguous=require_contiguous,
            )
            st.success(SUCCESS_MSG)
            for i, period_result in enumerate(result["period_results"], start=1):
                st.write(f"Period {i} Annualised Cost: {period_result['annualised_cost']:.8f}")
            st.write(f"Total Split Annualised Cost: {result['total_split_annualised_cost']:.8f}")
        except Exception as exc:
            st.error(f"Error: {exc}")
