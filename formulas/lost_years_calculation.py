from dataclasses import dataclass
from typing import Dict, List

from .earnings_calculation import EarningsCalculation


@dataclass
class LostYearsCalculation:
    earnings_calculation: EarningsCalculation

    def calculate(
        self,
        claimant_age: float,
        current_life_end_age: float,
        but_for_remaining_life_years: float,
        but_for_multiplier_method: str,
        lost_years_rate: float,
        contingency_factor: float,
        earnings_periods: List[Dict[str, float | str | bool]],
        current_multiplier_method: str = "term_certain",
        pension_lump_sum_amount: float = 0.0,
        pension_lump_sum_age: float | None = None,
        pension_annual_amount: float = 0.0,
        pension_annual_start_age: float | None = None,
        pension_annual_end_age: float | None = None,
        employment_type: str = "employed",
        region: str = "England_Wales_NI",
        values_are_net: bool = False,
        table35_csv: str | None = None,
        but_for_age: float | None = None,
        additional_tables_zero_csv: str | None = None,
        additional_tables_point5_csv: str | None = None,
    ) -> Dict[str, float | List[Dict[str, float]] | List[str]]:
        trace: List[str] = []
        if lost_years_rate < 0 or lost_years_rate > 1:
            raise ValueError("lost_years_rate must be in [0, 1].")
        if contingency_factor <= 0:
            raise ValueError("contingency_factor must be > 0.")
        if but_for_multiplier_method not in {"term_certain", "find_appropriate_age"}:
            raise ValueError("but_for_multiplier_method must be term_certain or find_appropriate_age.")
        if current_multiplier_method not in {"term_certain", "find_appropriate_age"}:
            raise ValueError("current_multiplier_method must be term_certain or find_appropriate_age.")
        if current_life_end_age <= claimant_age:
            raise ValueError("current_life_end_age must be greater than claimant_age.")
        if but_for_remaining_life_years <= 0:
            raise ValueError("but_for_remaining_life_years must be > 0.")

        base_but_for_multiplier = self.earnings_calculation._table36_interp(but_for_remaining_life_years)
        if but_for_multiplier_method == "term_certain":
            but_for_multiplier = base_but_for_multiplier
        else:
            if additional_tables_zero_csv and additional_tables_point5_csv:
                _, but_for_multiplier = self.earnings_calculation._find_appropriate_anchor_from_whole_life_additional(
                    zero_csv=additional_tables_zero_csv,
                    point5_csv=additional_tables_point5_csv,
                    remaining_life=but_for_remaining_life_years,
                )
            else:
                lookup_age = claimant_age if but_for_age is None else but_for_age
                but_for_multiplier = self.earnings_calculation._whole_life_interp(lookup_age)

        current_life_years = current_life_end_age - claimant_age
        if current_multiplier_method == "term_certain":
            current_life_multiplier = self.earnings_calculation._table36_interp(current_life_years)
        else:
            if additional_tables_zero_csv and additional_tables_point5_csv:
                _, current_life_multiplier = self.earnings_calculation._find_appropriate_anchor_from_whole_life_additional(
                    zero_csv=additional_tables_zero_csv,
                    point5_csv=additional_tables_point5_csv,
                    remaining_life=current_life_years,
                )
            else:
                current_life_multiplier = self.earnings_calculation._whole_life_interp(float(claimant_age))
        base_lost_years_multiplier = base_but_for_multiplier - current_life_multiplier
        lost_years_multiplier = but_for_multiplier - current_life_multiplier
        if base_lost_years_multiplier <= 0:
            raise ValueError("Invalid baseline lost-years multiplier (<= 0).")
        normalization_ratio = lost_years_multiplier / base_lost_years_multiplier

        trace.append(f"DEBUG: But For Injury Life Multiplier = {but_for_multiplier:.8f}")
        trace.append(f"DEBUG: Current Life Multiplier = {current_life_multiplier:.8f}")
        trace.append(f"DEBUG: Lost Years Multiplier = {lost_years_multiplier:.8f}")
        trace.append(f"DEBUG: Baseline Lost Years Multiplier = {base_lost_years_multiplier:.8f}")
        trace.append(f"DEBUG: Lost Years Normalization Ratio = {normalization_ratio:.8f}")

        line_items: List[Dict[str, float]] = []
        total_loss = 0.0

        for idx, period in enumerate(earnings_periods, start=1):
            age_at_start = float(period["age_at_start"])
            age_at_end = float(period["age_at_end"])
            amount = float(period["amount"])
            frequency = str(period.get("frequency", "Per_Year"))
            is_net = bool(period.get("is_net", values_are_net))

            annual = amount * {"Per_Year": 1.0, "Per_Month": 12.0, "Per_Week": 365.0 / 7.0}[frequency]
            if is_net:
                net_annual = annual
            else:
                net_annual = self.earnings_calculation._to_net_annual(
                    annual,
                    employment_type=employment_type,
                    region=region,
                    apply_ni=age_at_start < self.earnings_calculation._infer_retirement_age_from_table(),
                )
            annual_used = net_annual * lost_years_rate
            term_start = max(0.0, age_at_start - claimant_age)
            term_end = max(0.0, age_at_end - claimant_age)
            base_slice = self.earnings_calculation._table36_interp(term_end) - self.earnings_calculation._table36_interp(term_start)
            period_multiplier = base_slice * contingency_factor * normalization_ratio
            line_total = annual_used * period_multiplier
            total_loss += line_total
            line_items.append(
                {
                    "index": float(idx),
                    "annual_net": net_annual,
                    "annual_used": annual_used,
                    "period_multiplier": period_multiplier,
                    "total": line_total,
                }
            )

        if pension_lump_sum_amount > 0 and pension_lump_sum_age is not None:
            if not table35_csv:
                raise ValueError("table35_csv is required when pension_lump_sum_amount is provided.")
            table35_vector = EarningsCalculation._load_single_column_vector(table35_csv)
            defer_years = max(0.0, pension_lump_sum_age - claimant_age)
            lump_multiplier = EarningsCalculation._table35_interp(table35_vector, defer_years)
            annual_used = pension_lump_sum_amount * lost_years_rate
            line_total = annual_used * lump_multiplier
            total_loss += line_total
            line_items.append(
                {
                    "index": float(len(line_items) + 1),
                    "annual_net": pension_lump_sum_amount,
                    "annual_used": annual_used,
                    "period_multiplier": lump_multiplier,
                    "total": line_total,
                }
            )

        if (
            pension_annual_amount > 0
            and pension_annual_start_age is not None
            and pension_annual_end_age is not None
            and pension_annual_end_age > pension_annual_start_age
        ):
            if values_are_net:
                net_annual = pension_annual_amount
            else:
                # Pension annual NI is not applied in this head.
                net_annual = self.earnings_calculation._to_net_annual(
                    pension_annual_amount,
                    employment_type=employment_type,
                    region=region,
                    apply_ni=False,
                )
            annual_used = net_annual * lost_years_rate
            term_start = max(0.0, pension_annual_start_age - claimant_age)
            base_slice = self.earnings_calculation._table36_interp(but_for_remaining_life_years) - self.earnings_calculation._table36_interp(term_start)
            period_multiplier = base_slice * normalization_ratio
            line_total = annual_used * period_multiplier
            total_loss += line_total
            line_items.append(
                {
                    "index": float(len(line_items) + 1),
                    "annual_net": net_annual,
                    "annual_used": annual_used,
                    "period_multiplier": period_multiplier,
                    "total": line_total,
                }
            )

        return {
            "but_for_injury_life_multiplier": but_for_multiplier,
            "current_life_multiplier": current_life_multiplier,
            "lost_years_multiplier": lost_years_multiplier,
            "normalization_ratio": normalization_ratio,
            "line_items": line_items,
            "total_loss": total_loss,
            "trace": trace,
        }

