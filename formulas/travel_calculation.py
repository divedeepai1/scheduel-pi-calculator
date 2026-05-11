from dataclasses import dataclass
from typing import Dict, List


_TRAVEL_TIME_INCREMENTS = {
    "Over_Period",
    "Per_Day",
    "Per_Week",
    "Per_Month",
    "Per_Year",
    "Per_Weekday",
    "Per_Weekend",
}

_DISTANCE_INPUT_TYPES = {"Each_Way", "Overall"}

_FREQUENCY_PER_YEAR = {
    "Per_Day": 365.25,
    "Per_Week": 365.0 / 7.0,
    "Per_Month": 12.0,
    "Per_Year": 1.0,
    "Per_Weekday": 260.0,
    "Per_Weekend": 104.0,
}


@dataclass
class TravelCalculation:
    def calculate_annual(
        self,
        distance: float,
        distance_input_type: str,
        mileage_rate: float,
        parking_cost: float,
        journey_count: float,
        time_increment: str,
        period_years: float | None = None,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []

        if distance < 0:
            raise ValueError("distance must be non-negative.")
        if mileage_rate < 0:
            raise ValueError("mileage_rate must be non-negative.")
        if parking_cost < 0:
            raise ValueError("parking_cost must be non-negative.")
        if journey_count < 0:
            raise ValueError("journey_count must be non-negative.")
        if distance_input_type not in _DISTANCE_INPUT_TYPES:
            raise ValueError(f"distance_input_type must be one of {sorted(_DISTANCE_INPUT_TYPES)}.")
        if time_increment not in _TRAVEL_TIME_INCREMENTS:
            raise ValueError(f"time_increment must be one of {sorted(_TRAVEL_TIME_INCREMENTS)}.")
        if time_increment == "Over_Period":
            if period_years is None:
                raise ValueError("period_years is required when time_increment is Over_Period.")
            if period_years <= 0:
                raise ValueError("period_years must be greater than 0 for Over_Period.")

        effective_distance = distance * (2.0 if distance_input_type == "Each_Way" else 1.0)
        journey_cost = (effective_distance * mileage_rate) + parking_cost
        if time_increment == "Over_Period":
            frequency_per_year = 1.0 / float(period_years)
            annual_journey_count = journey_count * frequency_per_year
        else:
            frequency_per_year = _FREQUENCY_PER_YEAR[time_increment]
            annual_journey_count = journey_count * frequency_per_year
        annual_loss = annual_journey_count * journey_cost

        trace.append(
            f"DEBUG: Effective Distance = distance * factor = {distance:.8f} * "
            f"{(2.0 if distance_input_type == 'Each_Way' else 1.0):.8f} = {effective_distance:.8f}"
        )
        trace.append(
            f"DEBUG: Journey Cost = (effective_distance * mileage_rate) + parking_cost = "
            f"({effective_distance:.8f} * {mileage_rate:.8f}) + {parking_cost:.8f} = {journey_cost:.8f}"
        )
        trace.append(
            f"DEBUG: Annual Journey Count = journey_count * frequency_per_year = "
            f"{journey_count:.8f} * {frequency_per_year:.8f} = {annual_journey_count:.8f}"
        )
        trace.append(
            f"DEBUG: Annual Loss = annual_journey_count * journey_cost = "
            f"{annual_journey_count:.8f} * {journey_cost:.8f} = {annual_loss:.8f}"
        )

        return {
            "effective_distance": effective_distance,
            "journey_cost": journey_cost,
            "annual_journey_count": annual_journey_count,
            "annual_loss": annual_loss,
            "trace": trace,
        }
