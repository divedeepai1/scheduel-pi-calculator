from dataclasses import dataclass
from typing import List

from .continuous_multiplier_calculation import ContinuousMultiplierCalculation


_FREQUENCY_FACTORS = {
    "Per_Year": 1.0,
    "Per_Month": 12.0,
    "Per_Week": 365.0 / 7.0,
    "Per_Day": 365.25,
}


@dataclass
class GeneralContinuousCalculation:
    """
    General Continuous (GC):
    - Convert loss amount to annual amount
    - Apply continuous period multiplier (CM)
    """

    cm_calculation: ContinuousMultiplierCalculation

    def calculate(
        self,
        *,
        loss_amount: float,
        loss_frequency: str,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        start_age: float | None = None,
        end_age: float | None = None,
        start_at_calculation_age: bool = False,
        end_at_rest_of_life: bool = False,
        use_apportionment: bool = True,
        apportionment_method: str = "term_certain_end_minus_start",
    ) -> dict:
        if loss_amount < 0:
            raise ValueError("loss_amount must be non-negative.")
        if loss_frequency not in _FREQUENCY_FACTORS:
            raise ValueError("loss_frequency must be one of Per_Year, Per_Month, Per_Week, Per_Day.")

        trace: List[str] = []
        annual_loss = float(loss_amount) * float(_FREQUENCY_FACTORS[loss_frequency])
        trace.append(
            f"DEBUG: Annual Loss = loss_amount * frequency_factor = {loss_amount:.8f} * {_FREQUENCY_FACTORS[loss_frequency]:.8f} = {annual_loss:.8f}"
        )

        cm = self.cm_calculation.calculate(
            calculation_age=calculation_age,
            life_expectancy_age=life_expectancy_age,
            life_multiplier=life_multiplier,
            start_age=start_age,
            end_age=end_age,
            start_at_calculation_age=start_at_calculation_age,
            end_at_rest_of_life=end_at_rest_of_life,
            use_apportionment=use_apportionment,
            apportionment_method=apportionment_method,
        )
        period_multiplier = float(cm["period_multiplier"])
        total = float(annual_loss * period_multiplier)
        trace.extend(cm["trace"])
        trace.append(
            f"DEBUG: Total = annual_loss * period_multiplier = {annual_loss:.8f} * {period_multiplier:.8f} = {total:.8f}"
        )

        return {
            "method": "general_continuous",
            "loss_amount": float(loss_amount),
            "loss_frequency": str(loss_frequency),
            "annual_loss": annual_loss,
            "period_multiplier": period_multiplier,
            "total": total,
            "cm_result": cm,
            "trace": trace,
        }
