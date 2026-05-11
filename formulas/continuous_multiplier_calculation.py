from dataclasses import dataclass
from typing import List

from .care_multiplier_calculation import CareMultiplierCalculation


@dataclass
class ContinuousMultiplierCalculation:
    """
    PI-style Continuous Multiplier (CM) calculator.

    This wrapper keeps CM inputs in pi-calc style:
    - start/end as ages (or rest_of_life)
    - claimant calculation age
    - life expectancy age
    and delegates core Table 36 apportionment math to CareMultiplierCalculation.
    """

    table36_vector: List[float]

    def calculate(
        self,
        *,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        start_age: float | None = None,
        end_age: float | None = None,
        start_at_calculation_age: bool = False,
        end_at_rest_of_life: bool = False,
    ) -> dict:
        if calculation_age <= 0:
            raise ValueError("calculation_age must be greater than 0.")
        if life_expectancy_age <= calculation_age:
            raise ValueError("life_expectancy_age must be greater than calculation_age.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0.")

        if start_at_calculation_age:
            resolved_start_age = float(calculation_age)
        else:
            if start_age is None:
                raise ValueError("start_age is required when start_at_calculation_age is False.")
            resolved_start_age = float(start_age)

        if end_at_rest_of_life:
            resolved_end_age = float(life_expectancy_age)
        else:
            if end_age is None:
                raise ValueError("end_age is required when end_at_rest_of_life is False.")
            resolved_end_age = float(end_age)
            if resolved_end_age > float(life_expectancy_age):
                resolved_end_age = float(life_expectancy_age)

        start_years = float(resolved_start_age - calculation_age)
        end_years = float(resolved_end_age - calculation_age)
        life_expectancy_years = float(life_expectancy_age - calculation_age)

        if start_years < 0:
            raise ValueError("start period cannot be before calculation age.")
        if end_years <= start_years:
            raise ValueError("end period must be greater than start period.")

        apportion = CareMultiplierCalculation(self.table36_vector).apportion_period_multiplier(
            start_years=start_years,
            end_years=end_years,
            life_expectancy_years=life_expectancy_years,
            life_multiplier=float(life_multiplier),
        )
        trace = list(apportion["trace"])
        if (not end_at_rest_of_life) and (end_age is not None) and float(end_age) > float(life_expectancy_age):
            trace.insert(
                0,
                f"DEBUG: Capping end_age from {float(end_age):.8f} to life_expectancy_age {float(life_expectancy_age):.8f}.",
            )

        return {
            "method": "continuous_multiplier",
            "calculation_age": float(calculation_age),
            "life_expectancy_age": float(life_expectancy_age),
            "start_age": float(resolved_start_age),
            "end_age": float(resolved_end_age),
            "start_years": start_years,
            "end_years": end_years,
            "life_expectancy_years": life_expectancy_years,
            "life_multiplier": float(life_multiplier),
            "term_multiplier_start": float(apportion["term_multiplier_start"]),
            "term_multiplier_end": float(apportion["term_multiplier_end"]),
            "term_multiplier_life_expectancy": float(apportion["term_multiplier_life_expectancy"]),
            "period_multiplier": float(apportion["period_multiplier"]),
            "trace": trace,
        }
