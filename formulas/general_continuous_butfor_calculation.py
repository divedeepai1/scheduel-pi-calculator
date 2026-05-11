from dataclasses import dataclass

from .continuous_multiplier_calculation import ContinuousMultiplierCalculation


_FREQUENCY_FACTORS = {
    "Per_Year": 1.0,
    "Per_Month": 12.0,
    "Per_Week": 365.0 / 7.0,
    "Per_Day": 365.25,
}


@dataclass
class GeneralContinuousButForCalculation:
    """
    General Continuous (But For):
    total = (annual_result - annual_prior) * period_multiplier
    """

    cm_calculation: ContinuousMultiplierCalculation

    def calculate(
        self,
        *,
        cost_prior: float,
        cost_prior_frequency: str,
        cost_result: float,
        cost_result_frequency: str,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        start_age: float | None = None,
        end_age: float | None = None,
        start_at_calculation_age: bool = False,
        end_at_rest_of_life: bool = False,
    ) -> dict:
        if cost_prior < 0 or cost_result < 0:
            raise ValueError("cost_prior and cost_result must be non-negative.")
        if cost_prior_frequency not in _FREQUENCY_FACTORS or cost_result_frequency not in _FREQUENCY_FACTORS:
            raise ValueError("Frequencies must be one of Per_Year, Per_Month, Per_Week, Per_Day.")

        annual_prior = float(cost_prior) * float(_FREQUENCY_FACTORS[cost_prior_frequency])
        annual_result = float(cost_result) * float(_FREQUENCY_FACTORS[cost_result_frequency])
        net_annual_loss = float(annual_result - annual_prior)

        cm = self.cm_calculation.calculate(
            calculation_age=calculation_age,
            life_expectancy_age=life_expectancy_age,
            life_multiplier=life_multiplier,
            start_age=start_age,
            end_age=end_age,
            start_at_calculation_age=start_at_calculation_age,
            end_at_rest_of_life=end_at_rest_of_life,
        )
        period_multiplier = float(cm["period_multiplier"])
        total = float(net_annual_loss * period_multiplier)

        trace = [
            f"DEBUG: Annual Prior = {cost_prior:.8f} * {_FREQUENCY_FACTORS[cost_prior_frequency]:.8f} = {annual_prior:.8f}",
            f"DEBUG: Annual Result = {cost_result:.8f} * {_FREQUENCY_FACTORS[cost_result_frequency]:.8f} = {annual_result:.8f}",
            f"DEBUG: Net Annual Loss = {annual_result:.8f} - {annual_prior:.8f} = {net_annual_loss:.8f}",
        ]
        trace.extend(cm["trace"])
        trace.append(
            f"DEBUG: Total = net_annual_loss * period_multiplier = {net_annual_loss:.8f} * {period_multiplier:.8f} = {total:.8f}"
        )

        return {
            "method": "general_continuous_but_for",
            "annual_prior": annual_prior,
            "annual_result": annual_result,
            "net_annual_loss": net_annual_loss,
            "period_multiplier": period_multiplier,
            "total": total,
            "cm_result": cm,
            "trace": trace,
        }
