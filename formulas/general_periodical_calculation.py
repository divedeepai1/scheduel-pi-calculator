from dataclasses import dataclass
from typing import List
import math

from .care_multiplier_calculation import CareMultiplierCalculation


_RECURRENCE_TO_YEARS = {
    "Years": 1.0,
    "Months": 1.0 / 12.0,
    "Weeks": 7.0 / 365.0,
    "Days": 1.0 / 365.25,
}


@dataclass
class GeneralPeriodicalCalculation:
    """
    General Periodical (GP):
    multiplier = sum(Table35 factor at each scheduled purchase time)
    total = loss_amount * multiplier
    """

    table35_vector: List[float]
    table36_vector: List[float]

    def _table35_factor(self, years: float, trace: List[str]) -> float:
        if years < 0:
            raise ValueError("years must be non-negative for Table 35 interpolation.")
        if years == 0:
            return 1.0
        if years < 1.0:
            lo = 0
            hi = 1
            vlo = 1.0
            vhi = float(self.table35_vector[0])
        else:
            lo = int(math.floor(years))
            hi = lo + 1
            if hi > len(self.table35_vector):
                raise ValueError(f"Table 35 vector too short for {years} years; need entry for year {hi}.")
            vlo = float(self.table35_vector[lo - 1])
            vhi = float(self.table35_vector[hi - 1])
        out = ((hi - years) * vlo) + ((years - lo) * vhi)
        trace.append(f"DEBUG: Table 35 - {lo} years at 0.50%: {vlo:.8f}")
        trace.append(f"DEBUG: Table 35 - {hi} years at 0.50%: {vhi:.8f}")
        trace.append(
            f"DEBUG: Table 35 interpolate ({hi}-{years:.8f})*{vlo:.8f} + ({years:.8f}-{lo})*{vhi:.8f} = {out:.8f}"
        )
        return out

    @staticmethod
    def _build_purchase_years(start_years: float, end_years: float, recurrence_years: float) -> List[float]:
        years: List[float] = []
        t = float(start_years)
        eps = 1e-9
        # PI-style GP scheduling: include start point, exclude terminal end point.
        while t < end_years - eps:
            years.append(float(t))
            t += recurrence_years
        return years

    def calculate(
        self,
        *,
        loss_amount: float,
        recurrence_every: float,
        recurrence_unit: str,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        start_age: float | None = None,
        end_age: float | None = None,
        start_at_calculation_age: bool = False,
        end_at_rest_of_life: bool = False,
        pi_parity_mode: bool = True,
    ) -> dict:
        if loss_amount < 0:
            raise ValueError("loss_amount must be non-negative.")
        if recurrence_every <= 0:
            raise ValueError("recurrence_every must be greater than 0.")
        if recurrence_unit not in _RECURRENCE_TO_YEARS:
            raise ValueError("recurrence_unit must be one of Days, Weeks, Months, Years.")
        if calculation_age <= 0:
            raise ValueError("calculation_age must be greater than 0.")
        if life_expectancy_age <= calculation_age:
            raise ValueError("life_expectancy_age must be greater than calculation_age.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0.")
        if not self.table35_vector:
            raise ValueError("table35_vector cannot be empty.")
        if not self.table36_vector:
            raise ValueError("table36_vector cannot be empty.")

        resolved_start_age = float(calculation_age) if start_at_calculation_age else float(start_age)
        if end_at_rest_of_life:
            resolved_end_age = float(life_expectancy_age)
        else:
            if end_age is None:
                raise ValueError("end_age is required when end_at_rest_of_life is False.")
            resolved_end_age = float(min(end_age, life_expectancy_age))

        start_years = float(resolved_start_age - calculation_age)
        end_years = float(resolved_end_age - calculation_age)
        if start_years < 0:
            raise ValueError("start period cannot be before calculation age.")
        if end_years < start_years:
            raise ValueError("end period must be >= start period.")

        recurrence_years = float(recurrence_every) * float(_RECURRENCE_TO_YEARS[recurrence_unit])
        purchase_years = self._build_purchase_years(start_years, end_years, recurrence_years)

        trace: List[str] = []
        multiplier = 0.0
        for idx, t in enumerate(purchase_years):
            f = self._table35_factor(t, trace)
            if pi_parity_mode:
                f = round(float(f), 2)
            multiplier += f
            if idx < 5 or idx >= max(0, len(purchase_years) - 5):
                trace.append(f"DEBUG: Purchase {idx+1} at {t:.8f} years -> factor {f:.8f}")

        life_expectancy_years = float(life_expectancy_age - calculation_age)
        life_term = CareMultiplierCalculation(self.table36_vector).table36_multiplier(
            life_expectancy_years, trace=trace
        )
        adjusted_multiplier = float(multiplier * (float(life_multiplier) / float(life_term)))
        if pi_parity_mode:
            adjusted_multiplier = round(float(adjusted_multiplier), 3)

        total = float(loss_amount * adjusted_multiplier)
        trace.append(f"DEBUG: Raw Multiplier = sum(factors) = {multiplier:.8f}")
        trace.append(
            f"DEBUG: Mortality adjustment = life_multiplier / life_term = {float(life_multiplier):.8f} / {float(life_term):.8f}"
        )
        trace.append(f"DEBUG: Adjusted Multiplier = {multiplier:.8f} * ({float(life_multiplier):.8f}/{float(life_term):.8f}) = {adjusted_multiplier:.8f}")
        trace.append(
            f"DEBUG: Total = loss_amount * adjusted_multiplier = {loss_amount:.8f} * {adjusted_multiplier:.8f} = {total:.8f}"
        )

        return {
            "method": "general_periodical",
            "loss_amount": float(loss_amount),
            "recurrence_every": float(recurrence_every),
            "recurrence_unit": str(recurrence_unit),
            "recurrence_years": recurrence_years,
            "calculation_age": float(calculation_age),
            "life_expectancy_age": float(life_expectancy_age),
            "start_age": float(resolved_start_age),
            "end_age": float(resolved_end_age),
            "start_years": start_years,
            "end_years": end_years,
            "purchase_count": len(purchase_years),
            "raw_multiplier": float(multiplier),
            "life_multiplier": float(life_multiplier),
            "life_term_multiplier": float(life_term),
            "multiplier": float(adjusted_multiplier),
            "total": total,
            "trace": trace,
        }
