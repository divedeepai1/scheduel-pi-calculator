from dataclasses import dataclass
from typing import List
import math


@dataclass
class GeneralOneOffCalculation:
    """
    General One Off (GOF):
    total = loss_amount * table35_factor(start_years)
    """

    table35_vector: List[float]

    def _table35_factor(self, years: float, trace: List[str]) -> float:
        if years < 0:
            raise ValueError("years must be non-negative for Table 35 interpolation.")
        if years == 0:
            trace.append("DEBUG: Table 35 - 0 years at 0.50%: 1.00000000")
            return 1.0
        if years < 1.0:
            yr_lower = 0
            yr_upper = 1
            f_lower = 1.0
            f_upper = float(self.table35_vector[0])
        else:
            yr_lower = int(math.floor(years))
            yr_upper = yr_lower + 1
            if yr_upper > len(self.table35_vector):
                raise ValueError(
                    f"Table 35 vector too short for {years} years; need entry for year {yr_upper}."
                )
            f_lower = float(self.table35_vector[yr_lower - 1])
            f_upper = float(self.table35_vector[yr_upper - 1])
        interpolated = ((yr_upper - years) * f_lower) + ((years - yr_lower) * f_upper)
        trace.append(f"DEBUG: Table 35 - {yr_lower} years at 0.50%: {f_lower:.8f}")
        trace.append(f"DEBUG: Table 35 - {yr_upper} years at 0.50%: {f_upper:.8f}")
        trace.append(
            f"DEBUG: Table 35 interpolate ({yr_upper}-{years:.8f})*{f_lower:.8f} + ({years:.8f}-{yr_lower})*{f_upper:.8f} = {interpolated:.8f}"
        )
        return interpolated

    def calculate(
        self,
        *,
        loss_amount: float,
        calculation_age: float,
        start_age: float | None = None,
        start_at_calculation_age: bool = False,
    ) -> dict:
        if loss_amount < 0:
            raise ValueError("loss_amount must be non-negative.")
        if calculation_age <= 0:
            raise ValueError("calculation_age must be greater than 0.")
        if not self.table35_vector:
            raise ValueError("table35_vector cannot be empty.")

        if start_at_calculation_age:
            resolved_start_age = float(calculation_age)
        else:
            if start_age is None:
                raise ValueError("start_age is required when start_at_calculation_age is False.")
            resolved_start_age = float(start_age)

        start_years = float(resolved_start_age - calculation_age)
        if start_years < 0:
            raise ValueError("start period cannot be before calculation age.")

        trace: List[str] = []
        multiplier = float(self._table35_factor(start_years, trace))
        total = float(loss_amount * multiplier)
        trace.append(
            f"DEBUG: Total = loss_amount * multiplier = {loss_amount:.8f} * {multiplier:.8f} = {total:.8f}"
        )
        return {
            "method": "general_one_off",
            "loss_amount": float(loss_amount),
            "calculation_age": float(calculation_age),
            "start_age": float(resolved_start_age),
            "start_years": start_years,
            "multiplier": multiplier,
            "total": total,
            "trace": trace,
        }
