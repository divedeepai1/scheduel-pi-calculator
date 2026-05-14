from dataclasses import dataclass
from typing import List, Dict, Any

from .continuous_multiplier_calculation import ContinuousMultiplierCalculation


_FREQUENCY_FACTORS = {
    "Per_Year": 1.0,
    "Per_Month": 12.0,
    "Per_Week": 365.0 / 7.0,
    "Per_Day": 365.25,
}


@dataclass
class LifetimeSplitCalculation:
    """
    Lifetime (Split):
    - Build contiguous periods
    - Annualise each period amount
    - Apply CM multiplier for each period
    - Sum period totals
    """

    cm_calculation: ContinuousMultiplierCalculation

    def calculate(
        self,
        *,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        periods: List[Dict[str, Any]],
        start_at_calculation_age: bool = True,
        start_age: float | None = None,
        cap_end_to_life_expectancy: bool = True,
        use_apportionment: bool = True,
        apportionment_method: str = "term_certain_end_minus_start",
    ) -> dict:
        if calculation_age <= 0:
            raise ValueError("calculation_age must be greater than 0.")
        if life_expectancy_age <= calculation_age:
            raise ValueError("life_expectancy_age must be greater than calculation_age.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0.")
        if not periods:
            raise ValueError("periods cannot be empty.")

        current_start_age = float(calculation_age if start_at_calculation_age else start_age)
        if current_start_age is None:
            raise ValueError("start_age is required when start_at_calculation_age is False.")

        out_periods: List[Dict[str, Any]] = []
        trace: List[str] = []
        grand_total = 0.0

        for idx, p in enumerate(periods):
            amount = float(p.get("amount", 0.0))
            frequency = str(p.get("frequency", "Per_Year"))
            if frequency not in _FREQUENCY_FACTORS:
                raise ValueError(f"Unsupported frequency '{frequency}' in period {idx + 1}.")
            if amount < 0:
                raise ValueError(f"amount must be non-negative in period {idx + 1}.")

            is_rest = bool(p.get("rest_of_life", False))
            if is_rest:
                raw_end_age = float(life_expectancy_age)
            else:
                if "end_age" not in p:
                    raise ValueError(f"end_age is required for non-rest period {idx + 1}.")
                raw_end_age = float(p["end_age"])

            end_age = float(min(raw_end_age, life_expectancy_age)) if cap_end_to_life_expectancy else float(raw_end_age)
            annualised = float(amount * _FREQUENCY_FACTORS[frequency])

            if end_age < current_start_age:
                raise ValueError(f"end_age must be >= start_age in period {idx + 1}.")

            if abs(end_age - current_start_age) <= 1e-9:
                period_multiplier = 0.0
                cm_trace = [f"DEBUG: Zero-length period at age {current_start_age:.8f}; multiplier set to 0."]
            else:
                cm = self.cm_calculation.calculate(
                    calculation_age=calculation_age,
                    life_expectancy_age=life_expectancy_age,
                    life_multiplier=life_multiplier,
                    start_age=current_start_age,
                    end_age=end_age,
                    start_at_calculation_age=False,
                    end_at_rest_of_life=False,
                    use_apportionment=use_apportionment,
                    apportionment_method=apportionment_method,
                )
                period_multiplier = float(cm["period_multiplier"])
                cm_trace = list(cm["trace"])

            period_total = float(annualised * period_multiplier)
            grand_total += period_total

            out_periods.append(
                {
                    "index": idx + 1,
                    "start_age": float(current_start_age),
                    "end_age": float(end_age),
                    "amount": amount,
                    "frequency": frequency,
                    "annualised_amount": annualised,
                    "period_multiplier": period_multiplier,
                    "period_total": period_total,
                    "trace": cm_trace,
                }
            )
            trace.append(
                f"DEBUG: Period {idx+1}: annualised={annualised:.8f}, multiplier={period_multiplier:.8f}, total={period_total:.8f}"
            )
            if raw_end_age > life_expectancy_age and cap_end_to_life_expectancy:
                trace.append(
                    f"DEBUG: Capping period {idx+1} end_age from {raw_end_age:.8f} to life_expectancy_age {life_expectancy_age:.8f}."
                )

            current_start_age = float(end_age)

        trace.append(f"DEBUG: Lifetime Split Total = {grand_total:.8f}")
        return {
            "method": "lifetime_split",
            "calculation_age": float(calculation_age),
            "life_expectancy_age": float(life_expectancy_age),
            "life_multiplier": float(life_multiplier),
            "periods": out_periods,
            "total": float(grand_total),
            "trace": trace,
        }
