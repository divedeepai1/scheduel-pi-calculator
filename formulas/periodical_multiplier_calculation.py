from dataclasses import dataclass

from .general_periodical_calculation import GeneralPeriodicalCalculation


@dataclass
class PeriodicalMultiplierCalculation:
    """
    Periodical Multiplier (PM):
    Uses the same engine as GP but focuses on multiplier output.
    """

    gp_calculation: GeneralPeriodicalCalculation

    def calculate(
        self,
        *,
        recurrence_every: float,
        recurrence_unit: str,
        calculation_age: float,
        life_expectancy_age: float,
        life_multiplier: float,
        start_age: float | None = None,
        end_age: float | None = None,
        start_at_calculation_age: bool = False,
        end_at_rest_of_life: bool = False,
        loss_amount: float = 0.0,
        pi_parity_mode: bool = True,
        use_mortality_adjustment: bool = True,
    ) -> dict:
        gp_result = self.gp_calculation.calculate(
            loss_amount=float(loss_amount),
            recurrence_every=recurrence_every,
            recurrence_unit=recurrence_unit,
            calculation_age=calculation_age,
            life_expectancy_age=life_expectancy_age,
            life_multiplier=life_multiplier,
            start_age=start_age,
            end_age=end_age,
            start_at_calculation_age=start_at_calculation_age,
            end_at_rest_of_life=end_at_rest_of_life,
            pi_parity_mode=pi_parity_mode,
            use_mortality_adjustment=use_mortality_adjustment,
        )
        return {
            "method": "periodical_multiplier",
            "purchase_count": int(gp_result["purchase_count"]),
            "raw_multiplier": float(gp_result["raw_multiplier"]),
            "life_term_multiplier": float(gp_result["life_term_multiplier"]),
            "life_multiplier": float(gp_result["life_multiplier"]),
            "multiplier": float(gp_result["multiplier"]),
            "total": float(gp_result["total"]),
            "trace": list(gp_result["trace"]),
        }
