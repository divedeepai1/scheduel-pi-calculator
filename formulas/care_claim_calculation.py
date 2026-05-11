from dataclasses import dataclass
from typing import Dict, Optional, List, Any

from .care_calculation import CareCalculation
from .care_multiplier_calculation import CareMultiplierCalculation


@dataclass
class CareClaimCalculation:
    care_calculation: CareCalculation
    care_multiplier_calculation: CareMultiplierCalculation

    def calculate(
        self,
        age_at_start: float,
        age_at_end: float,
        number_of_hours: float,
        time_increment: str,
        care_rate_type: str,
        rate_values: Optional[Dict[str, float]] = None,
        percentage_less: float = 0.0,
        manual_rate: Optional[float] = None,
        specify_increment: Optional[str] = None,
        number_days_specify: Optional[float] = None,
        number_weeks_specify: Optional[float] = None,
        number_months_specify: Optional[float] = None,
        term_start_years: float = 0.0,
        term_end_years: float = 0.0,
        life_expectancy_years: float = 0.0,
        life_multiplier: float = 0.0,
    ) -> dict:
        care_part = self.care_calculation.calculate(
            age_at_start=age_at_start,
            age_at_end=age_at_end,
            number_of_hours=number_of_hours,
            time_increment=time_increment,
            care_rate_type=care_rate_type,
            rate_values=rate_values or {},
            percentage_less=percentage_less,
            manual_rate=manual_rate,
            specify_increment=specify_increment,
            number_days_specify=number_days_specify,
            number_weeks_specify=number_weeks_specify,
            number_months_specify=number_months_specify,
        )

        multiplier_part = self.care_multiplier_calculation.apportion_period_multiplier(
            start_years=term_start_years,
            end_years=term_end_years,
            life_expectancy_years=life_expectancy_years,
            life_multiplier=life_multiplier,
        )

        total_award = float(care_part["annualised_cost"]) * float(multiplier_part["period_multiplier"])

        trace = []
        trace.extend(care_part["trace"])
        trace.extend(multiplier_part["trace"])
        trace.append(
            f"DEBUG: Total Award = AnnualisedCost * PeriodMultiplier = {care_part['annualised_cost']:.8f} * {multiplier_part['period_multiplier']:.8f} = {total_award:.8f}"
        )

        return {
            "annualised_cost": float(care_part["annualised_cost"]),
            "period_multiplier": float(multiplier_part["period_multiplier"]),
            "total_award": total_award,
            "term_multiplier_start": float(multiplier_part["term_multiplier_start"]),
            "term_multiplier_end": float(multiplier_part["term_multiplier_end"]),
            "term_multiplier_life_expectancy": float(multiplier_part["term_multiplier_life_expectancy"]),
            "trace": trace,
        }

    def calculate_split(
        self,
        periods: List[Dict[str, Any]],
        claimant_age: float,
        life_expectancy_years: float,
        life_multiplier: float,
        require_contiguous: bool = True,
        tolerance: float = 1e-9,
    ) -> Dict[str, Any]:
        if not periods:
            raise ValueError("periods cannot be empty.")

        prepared = []
        for idx, p in enumerate(periods):
            if "age_at_start" in p and "age_at_end" in p:
                start = float(p["age_at_start"])
                end = float(p["age_at_end"])
            elif "period_until_age" in p:
                start = float(p.get("age_at_start", claimant_age if idx == 0 else prepared[-1][1]))
                end = float(p["period_until_age"])
            elif "age_at_end" in p:
                start = float(p.get("age_at_start", claimant_age if idx == 0 else prepared[-1][1]))
                end = float(p["age_at_end"])
            else:
                raise ValueError("Each period must define age_at_start/age_at_end or period_until_age.")
            if end <= start:
                raise ValueError(f"Split period {idx + 1} invalid range {start} -> {end}.")
            prepared.append((start, end, p))

        prepared.sort(key=lambda x: x[0])
        for i in range(len(prepared) - 1):
            curr_end = prepared[i][1]
            next_start = prepared[i + 1][0]
            if next_start < curr_end - tolerance:
                raise ValueError(f"Split periods overlap: {curr_end} vs next start {next_start}.")
            if require_contiguous and abs(next_start - curr_end) > tolerance:
                raise ValueError(f"Split periods not contiguous: expected {curr_end}, got {next_start}.")

        phase_results = []
        total_award = 0.0
        trace: List[str] = []
        for i, (start, end, p) in enumerate(prepared, start=1):
            term_start_years = float(start - claimant_age)
            term_end_years = float(end - claimant_age)
            result = self.calculate(
                age_at_start=start,
                age_at_end=end,
                number_of_hours=float(p["number_of_hours"]),
                time_increment=str(p["time_increment"]),
                care_rate_type=str(p["care_rate_type"]),
                rate_values=p.get("rate_values"),
                percentage_less=float(p.get("percentage_less", 0.0)),
                manual_rate=p.get("manual_rate"),
                specify_increment=p.get("specify_increment"),
                number_days_specify=p.get("number_days_specify"),
                number_weeks_specify=p.get("number_weeks_specify"),
                number_months_specify=p.get("number_months_specify"),
                term_start_years=term_start_years,
                term_end_years=term_end_years,
                life_expectancy_years=life_expectancy_years,
                life_multiplier=life_multiplier,
            )
            phase_award = float(result["total_award"])
            total_award += phase_award
            phase_results.append(
                {
                    "phase": i,
                    "age_at_start": start,
                    "age_at_end": end,
                    "duration_years": end - start,
                    "annualised_cost": float(result["annualised_cost"]),
                    "period_multiplier": float(result["period_multiplier"]),
                    "total_award": phase_award,
                    "trace": result["trace"],
                }
            )
            trace.append(
                f"DEBUG: Phase {i} -> duration={end - start:.8f}, annual={result['annualised_cost']:.8f}, multiplier={result['period_multiplier']:.8f}, total={phase_award:.8f}"
            )

        trace.append(f"DEBUG: Split Claim Total Award = {total_award:.8f}")
        return {
            "phase_results": phase_results,
            "total_award": total_award,
            "trace": trace,
        }
