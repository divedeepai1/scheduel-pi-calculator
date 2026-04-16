from dataclasses import dataclass
from typing import Dict, Optional

from .care_calculation import CareCalculation
from .care_multiplier_calculation import CareMultiplierCalculation


@dataclass
class CareClaimCalculation:
    care_calculation: CareCalculation
    care_multiplier_calculation: CareMultiplierCalculation

    def calculate(
        self,
        age_at_start: float,
        age_at_end: float,
        number_of_hours: float,
        time_increment: str,
        care_rate_type: str,
        rate_values: Optional[Dict[str, float]] = None,
        percentage_less: float = 0.0,
        manual_rate: Optional[float] = None,
        specify_increment: Optional[str] = None,
        number_days_specify: Optional[float] = None,
        number_weeks_specify: Optional[float] = None,
        number_months_specify: Optional[float] = None,
        term_start_years: float = 0.0,
        term_end_years: float = 0.0,
        life_expectancy_years: float = 0.0,
        life_multiplier: float = 0.0,
    ) -> dict:
        care_part = self.care_calculation.calculate(
            age_at_start=age_at_start,
            age_at_end=age_at_end,
            number_of_hours=number_of_hours,
            time_increment=time_increment,
            care_rate_type=care_rate_type,
            rate_values=rate_values or {},
            percentage_less=percentage_less,
            manual_rate=manual_rate,
            specify_increment=specify_increment,
            number_days_specify=number_days_specify,
            number_weeks_specify=number_weeks_specify,
            number_months_specify=number_months_specify,
        )

        multiplier_part = self.care_multiplier_calculation.apportion_period_multiplier(
            start_years=term_start_years,
            end_years=term_end_years,
            life_expectancy_years=life_expectancy_years,
            life_multiplier=life_multiplier,
        )

        total_award = float(care_part["annualised_cost"]) * float(multiplier_part["period_multiplier"])

        trace = []
        trace.extend(care_part["trace"])
        trace.extend(multiplier_part["trace"])
        trace.append(
            f"DEBUG: Total Award = AnnualisedCost * PeriodMultiplier = {care_part['annualised_cost']:.8f} * {multiplier_part['period_multiplier']:.8f} = {total_award:.8f}"
        )

        return {
            "annualised_cost": float(care_part["annualised_cost"]),
            "period_multiplier": float(multiplier_part["period_multiplier"]),
            "total_award": total_award,
            "term_multiplier_start": float(multiplier_part["term_multiplier_start"]),
            "term_multiplier_end": float(multiplier_part["term_multiplier_end"]),
            "term_multiplier_life_expectancy": float(multiplier_part["term_multiplier_life_expectancy"]),
            "trace": trace,
        }
