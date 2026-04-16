from dataclasses import dataclass
from typing import List
import math


@dataclass
class CareMultiplierCalculation:
    """
    PI-style term-certain and apportionment calculations using a Table 36 vector.

    Table 36 vector is expected as 1-based years in order:
    index 0 -> 1 year multiplier, index 1 -> 2 year multiplier, etc.
    """

    table36_vector: List[float]

    def _validate_vector(self) -> None:
        if not self.table36_vector:
            raise ValueError("table36_vector cannot be empty.")
        if any(v < 0 for v in self.table36_vector):
            raise ValueError("table36_vector cannot contain negative values.")

    def table36_multiplier(self, years: float, trace: List[str] | None = None) -> float:
        self._validate_vector()
        if years <= 0:
            raise ValueError("years must be greater than 0 for Table 36 interpolation.")

        yr_lower = max(1, int(math.floor(years)))
        yr_upper = yr_lower + 1
        if yr_upper > len(self.table36_vector):
            raise ValueError(
                f"Table 36 vector too short for {years} years; need entry for year {yr_upper}."
            )

        m_lower = float(self.table36_vector[yr_lower - 1])
        m_upper = float(self.table36_vector[yr_upper - 1])
        interpolated = ((yr_upper - years) * m_lower) + ((years - yr_lower) * m_upper)

        if trace is not None:
            trace.append(f"DEBUG: Table 36 - {yr_lower} years at 0.50%: {m_lower:.8f}")
            trace.append(f"DEBUG: Table 36 - {yr_upper} years at 0.50%: {m_upper:.8f}")
            trace.append(f"DEBUG: Interpolate between {yr_lower} and {yr_upper}")
            trace.append(
                f"DEBUG: ({yr_upper}-{years:.8f})*{m_lower:.8f} + ({years:.8f}-{yr_lower})*{m_upper:.8f} = {interpolated:.8f}"
            )

        return interpolated

    def apportion_period_multiplier(
        self,
        start_years: float,
        end_years: float,
        life_expectancy_years: float,
        life_multiplier: float,
    ) -> dict:
        trace: List[str] = []
        if end_years <= start_years:
            raise ValueError("end_years must be greater than start_years.")
        if life_expectancy_years <= 0:
            raise ValueError("life_expectancy_years must be greater than 0.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0.")

        term_start = self.table36_multiplier(start_years, trace=trace)
        trace.append(
            f"DEBUG: Multiplier for Term Certain {start_years:.8f} years at 0.50% = {term_start:.8f}"
        )
        term_end = self.table36_multiplier(end_years, trace=trace)
        trace.append(
            f"DEBUG: Multiplier for Term Certain {end_years:.8f} years at 0.50% = {term_end:.8f}"
        )

        life_term = self.table36_multiplier(life_expectancy_years, trace=trace)
        trace.append(
            f"DEBUG: Apply to life multiplier using life expectancy {life_expectancy_years:.8f} years."
        )
        period_multiplier = ((term_end - term_start) / life_term) * life_multiplier
        trace.append(
            f"DEBUG: (({term_end:.8f} - {term_start:.8f}) / {life_term:.8f}) * {life_multiplier:.8f} = {period_multiplier:.8f}"
        )

        return {
            "term_multiplier_start": term_start,
            "term_multiplier_end": term_end,
            "term_multiplier_life_expectancy": life_term,
            "period_multiplier": period_multiplier,
            "trace": trace,
        }
