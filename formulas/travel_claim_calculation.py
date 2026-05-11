from dataclasses import dataclass
from typing import Dict, List

from .care_multiplier_calculation import CareMultiplierCalculation
from .travel_calculation import TravelCalculation


@dataclass
class TravelClaimCalculation:
    travel_calculation: TravelCalculation
    care_multiplier_calculation: CareMultiplierCalculation

    def calculate(
        self,
        age_at_start: float,
        age_at_end: float,
        claimant_age: float,
        life_expectancy_years: float,
        life_multiplier: float,
        distance: float,
        distance_input_type: str,
        mileage_rate: float,
        parking_cost: float,
        journey_count: float,
        time_increment: str,
    ) -> Dict[str, float | List[str]]:
        annual_part = self.travel_calculation.calculate_annual(
            distance=distance,
            distance_input_type=distance_input_type,
            mileage_rate=mileage_rate,
            parking_cost=parking_cost,
            journey_count=journey_count,
            time_increment=time_increment,
            period_years=(age_at_end - age_at_start),
        )

        term_start_years = float(age_at_start - claimant_age)
        term_end_years = float(age_at_end - claimant_age)
        multiplier_part = self.care_multiplier_calculation.apportion_period_multiplier(
            start_years=term_start_years,
            end_years=term_end_years,
            life_expectancy_years=life_expectancy_years,
            life_multiplier=life_multiplier,
        )

        total_loss = float(annual_part["annual_loss"]) * float(multiplier_part["period_multiplier"])

        trace: List[str] = []
        trace.extend(annual_part["trace"])
        trace.extend(multiplier_part["trace"])
        trace.append(
            f"DEBUG: Total Loss = annual_loss * period_multiplier = {annual_part['annual_loss']:.8f} * "
            f"{multiplier_part['period_multiplier']:.8f} = {total_loss:.8f}"
        )

        return {
            "annual_loss": float(annual_part["annual_loss"]),
            "period_multiplier": float(multiplier_part["period_multiplier"]),
            "term_multiplier_start": float(multiplier_part["term_multiplier_start"]),
            "term_multiplier_end": float(multiplier_part["term_multiplier_end"]),
            "term_multiplier_life_expectancy": float(multiplier_part["term_multiplier_life_expectancy"]),
            "total_loss": total_loss,
            "trace": trace,
        }
