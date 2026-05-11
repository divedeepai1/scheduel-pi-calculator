from dataclasses import dataclass
from typing import Dict, List

from .care_multiplier_calculation import CareMultiplierCalculation
from .earnings_calculation import EarningsCalculation


@dataclass
class AccommodationRvJCalculation:
    care_multiplier_calculation: CareMultiplierCalculation
    table35_vector: List[float]

    def calculate(
        self,
        *,
        claimant_age: float,
        age_at_start: float,
        age_at_end: float,
        life_expectancy_years: float,
        life_multiplier: float,
        cost_required_property: float,
        allowance_existing: float,
        cost_adaptations: float,
        betterment: float,
        increased_running_costs: float,
        rate_to_apply: float,
    ) -> Dict[str, float | List[str]]:
        if age_at_end <= age_at_start:
            raise ValueError("age_at_end must be greater than age_at_start.")
        if life_expectancy_years <= 0:
            raise ValueError("life_expectancy_years must be > 0.")
        if rate_to_apply < 0:
            raise ValueError("rate_to_apply must be >= 0.")

        capital_increase = float(cost_required_property - allowance_existing + betterment)
        rvj_value = float(capital_increase * rate_to_apply)
        ongoing_annual = float(rvj_value + increased_running_costs)

        term_start_years = float(age_at_start - claimant_age)
        term_end_years = float(age_at_end - claimant_age)
        mult = self.care_multiplier_calculation.apportion_period_multiplier(
            start_years=term_start_years,
            end_years=term_end_years,
            life_expectancy_years=life_expectancy_years,
            life_multiplier=life_multiplier,
        )
        ongoing_total = float(ongoing_annual * float(mult["period_multiplier"]))

        discount_factor = EarningsCalculation._table35_interp(self.table35_vector, max(0.0, term_start_years))
        adaptation_net = float(cost_adaptations - betterment)
        adaptation_total = float(adaptation_net * discount_factor)

        total = float(ongoing_total + adaptation_total)
        trace: List[str] = []
        trace.extend(mult["trace"])
        trace.append(f"DEBUG: Capital Increase = required - existing + betterment = {capital_increase:.8f}")
        trace.append(f"DEBUG: RvJ Value = capital_increase * rate_to_apply = {capital_increase:.8f} * {rate_to_apply:.8f} = {rvj_value:.8f}")
        trace.append(f"DEBUG: Ongoing Annual = rvj_value + increased_running = {rvj_value:.8f} + {increased_running_costs:.8f} = {ongoing_annual:.8f}")
        trace.append(f"DEBUG: Ongoing Total = ongoing_annual * period_multiplier = {ongoing_annual:.8f} * {mult['period_multiplier']:.8f} = {ongoing_total:.8f}")
        trace.append(f"DEBUG: Discount factor (Table35) at deferment {max(0.0, term_start_years):.8f} years = {discount_factor:.8f}")
        trace.append(f"DEBUG: Adaptation Net = adaptations - betterment = {cost_adaptations:.8f} - {betterment:.8f} = {adaptation_net:.8f}")
        trace.append(f"DEBUG: Adaptation Total = adaptation_net * discount_factor = {adaptation_net:.8f} * {discount_factor:.8f} = {adaptation_total:.8f}")
        trace.append(f"DEBUG: Total = ongoing_total + adaptation_total = {ongoing_total:.8f} + {adaptation_total:.8f} = {total:.8f}")
        return {
            "capital_increase": capital_increase,
            "rvj_value": rvj_value,
            "ongoing_annual": ongoing_annual,
            "ongoing_multiplier": float(mult["period_multiplier"]),
            "ongoing_total": ongoing_total,
            "discount_factor": discount_factor,
            "adaptation_net": adaptation_net,
            "adaptation_total": adaptation_total,
            "total_loss": total,
            "trace": trace,
        }


@dataclass
class AccommodationSwiftCarpenterCalculation:
    table35_vector: List[float]

    def calculate(
        self,
        *,
        claimant_age: float,
        age_at_start: float,
        age_at_end: float,
        cost_required_property: float,
        allowance_existing: float,
        reversionary_rate: float,
    ) -> Dict[str, float | List[str]]:
        if age_at_end <= age_at_start:
            raise ValueError("age_at_end must be greater than age_at_start.")
        if reversionary_rate < 0:
            raise ValueError("reversionary_rate must be >= 0.")

        period_years = float(age_at_end - age_at_start)
        net_capital = float(cost_required_property - allowance_existing)

        # Discount multiplier for period at reversionary rate (e.g., 5%).
        discount_multiplier = float((1.0 + reversionary_rate) ** (-period_years))
        reversionary_interest = float(net_capital * discount_multiplier)
        life_interest = float(net_capital - reversionary_interest)

        term_start_years = float(age_at_start - claimant_age)
        early_receipt_discount = EarningsCalculation._table35_interp(self.table35_vector, max(0.0, term_start_years))
        total = float(life_interest * early_receipt_discount)

        trace: List[str] = [
            f"DEBUG: Period Years = age_at_end - age_at_start = {period_years:.8f}",
            f"DEBUG: Net Capital = required - existing = {cost_required_property:.8f} - {allowance_existing:.8f} = {net_capital:.8f}",
            f"DEBUG: Discount multiplier for period at rate = (1 + {reversionary_rate:.8f})^(-{period_years:.8f}) = {discount_multiplier:.8f}",
            f"DEBUG: Reversionary Interest = net_capital * discount_multiplier = {net_capital:.8f} * {discount_multiplier:.8f} = {reversionary_interest:.8f}",
            f"DEBUG: Life Interest = net_capital - reversionary_interest = {net_capital:.8f} - {reversionary_interest:.8f} = {life_interest:.8f}",
            f"DEBUG: Discount factor (Table35) at deferment {max(0.0, term_start_years):.8f} years = {early_receipt_discount:.8f}",
            f"DEBUG: Total = life_interest * discount_factor = {life_interest:.8f} * {early_receipt_discount:.8f} = {total:.8f}",
        ]
        return {
            "period_years": period_years,
            "net_capital": net_capital,
            "discount_multiplier": discount_multiplier,
            "reversionary_interest": reversionary_interest,
            "life_interest": life_interest,
            "discount_factor": early_receipt_discount,
            "total_loss": total,
            "trace": trace,
        }
