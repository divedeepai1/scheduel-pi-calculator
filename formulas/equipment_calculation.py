import math
from dataclasses import dataclass
from typing import Dict, List

_REPLACEMENT_UNITS = {"Days", "Weeks", "Months", "Years"}
_PURCHASE_MORTALITY_MODES = {"no_mortality", "use_mortality", "use_mortality_pi_mm"}
_PURCHASE_BOUNDARY_MODES = {"future_only", "include_start"}


@dataclass
class EquipmentCalculation:
    table35_vector: List[float]
    table36_vector: List[float]

    def calculate(
        self,
        age_at_start: float,
        age_at_end: float,
        cost_of_equipment: float,
        replacement_every_value: float,
        replacement_every_unit: str,
        claimant_age: float,
        life_expectancy_years: float,
        life_multiplier: float,
        annual_insurance: float = 0.0,
        annual_maintenance: float = 0.0,
        purchase_mortality_mode: str = "no_mortality",
        purchase_boundary_mode: str | None = None,
        recurring_use_apportionment: bool = True,
    ) -> Dict[str, float | int | List[str]]:
        trace: List[str] = []

        if age_at_end <= age_at_start:
            raise ValueError("age_at_end must be greater than age_at_start.")
        if cost_of_equipment < 0:
            raise ValueError("cost_of_equipment must be non-negative.")
        if replacement_every_value <= 0:
            raise ValueError("replacement_every_value must be greater than 0.")
        if replacement_every_unit not in _REPLACEMENT_UNITS:
            raise ValueError(f"replacement_every_unit must be one of {sorted(_REPLACEMENT_UNITS)}.")
        if purchase_mortality_mode not in _PURCHASE_MORTALITY_MODES:
            raise ValueError(f"purchase_mortality_mode must be one of {sorted(_PURCHASE_MORTALITY_MODES)}.")
        if purchase_boundary_mode is not None and purchase_boundary_mode not in _PURCHASE_BOUNDARY_MODES:
            raise ValueError(f"purchase_boundary_mode must be one of {sorted(_PURCHASE_BOUNDARY_MODES)}.")
        if annual_insurance < 0 or annual_maintenance < 0:
            raise ValueError("annual_insurance and annual_maintenance must be non-negative.")
        if life_expectancy_years <= 0:
            raise ValueError("life_expectancy_years must be greater than 0.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0.")
        if not self.table35_vector:
            raise ValueError("table35_vector cannot be empty.")
        if not self.table36_vector:
            raise ValueError("table36_vector cannot be empty.")

        life_expectancy_end_age = float(claimant_age + life_expectancy_years)
        effective_end_age = float(min(age_at_end, life_expectancy_end_age))
        period_years = float(effective_end_age - age_at_start)
        start_years = float(age_at_start - claimant_age)
        end_years = float(effective_end_age - claimant_age)
        if start_years < 0:
            raise ValueError("age_at_start cannot be earlier than claimant_age.")
        if end_years <= start_years:
            raise ValueError("Derived end_years must be greater than start_years.")

        replacement_every_years = self._to_years(replacement_every_value, replacement_every_unit)
        annual_equipment_cost_display = float(cost_of_equipment)
        annual_recurring_cost = float(annual_insurance + annual_maintenance)
        purchase_years = self._build_purchase_years(
            start_years=start_years,
            end_years=end_years,
            replacement_every_years=replacement_every_years,
            purchase_boundary_mode=purchase_boundary_mode,
        )
        purchase_count = len(purchase_years)
        boundary_mode_used = "pi_include_start_exclude_end" if purchase_boundary_mode is None else purchase_boundary_mode

        trace.append(f"DEBUG: Period Years = {period_years:.8f}")
        trace.append(
            f"DEBUG: Effective End Age = min(age_at_end={age_at_end:.8f}, life_expectancy_end_age={life_expectancy_end_age:.8f}) = {effective_end_age:.8f}"
        )
        trace.append(f"DEBUG: Start/End Years from Calculation Age = {start_years:.8f} -> {end_years:.8f}")
        trace.append(
            f"DEBUG: Replacement Every = {replacement_every_value:.8f} {replacement_every_unit} -> {replacement_every_years:.8f} years"
        )
        trace.append(f"DEBUG: Annual Equipment Cost (display) = {annual_equipment_cost_display:.8f}")
        trace.append(f"DEBUG: Purchase Boundary Mode = {boundary_mode_used}")
        trace.append(f"DEBUG: Purchase Mortality Mode = {purchase_mortality_mode}")
        trace.append(f"DEBUG: Purchase Count = {purchase_count}")
        if purchase_years:
            trace.append("DEBUG: Purchase Years = " + ", ".join(f"{y:.8f}" for y in purchase_years))
        trace.append(
            f"DEBUG: Annual Recurring Cost = insurance + maintenance = {annual_insurance:.8f} + {annual_maintenance:.8f} = {annual_recurring_cost:.8f}"
        )

        equipment_multiplier = 0.0
        for y in purchase_years:
            factor = self._table35_factor(years=y, trace=trace)
            factor = self._apply_purchase_mortality_factor(
                years=y,
                factor=factor,
                purchase_mortality_mode=purchase_mortality_mode,
                life_multiplier=life_multiplier,
                life_expectancy_years=life_expectancy_years,
                trace=trace,
            )
            equipment_multiplier += factor
            trace.append(
                f"DEBUG: Equipment multiplier accumulation += Table35({y:.8f}) = {factor:.8f} -> {equipment_multiplier:.8f}"
            )
        capital_total = cost_of_equipment * equipment_multiplier

        term_start = self._table36_multiplier(years=start_years, trace=trace)
        term_end = self._table36_multiplier(years=end_years, trace=trace)
        term_life = self._table36_multiplier(years=life_expectancy_years, trace=trace)
        if recurring_use_apportionment:
            recurring_multiplier = ((term_end - term_start) / term_life) * life_multiplier
            trace.append(
                f"DEBUG: Recurring apportionment = (({term_end:.8f} - {term_start:.8f}) / {term_life:.8f}) * {life_multiplier:.8f} = {recurring_multiplier:.8f}"
            )
        else:
            recurring_multiplier = (term_end - term_start)
            trace.append(
                f"DEBUG: Recurring direct term_certain multiplier (no apportionment) = {term_end:.8f} - {term_start:.8f} = {recurring_multiplier:.8f}"
            )

        insurance_total = annual_insurance * recurring_multiplier
        maintenance_total = annual_maintenance * recurring_multiplier
        recurring_total = insurance_total + maintenance_total
        total_loss = capital_total + insurance_total + maintenance_total

        trace.append(f"DEBUG: Equipment Multiplier (sum of Table35 purchase factors) = {equipment_multiplier:.8f}")
        trace.append(f"DEBUG: Recurring Multiplier = {recurring_multiplier:.8f}")
        trace.append(
            f"DEBUG: Equipment Capital Total = annual_equipment_cost_display * equipment_multiplier = {annual_equipment_cost_display:.8f} * {equipment_multiplier:.8f} = {capital_total:.8f}"
        )
        trace.append(
            f"DEBUG: Insurance Total = annual_insurance * recurring_multiplier = {annual_insurance:.8f} * {recurring_multiplier:.8f} = {insurance_total:.8f}"
        )
        trace.append(
            f"DEBUG: Maintenance Total = annual_maintenance * recurring_multiplier = {annual_maintenance:.8f} * {recurring_multiplier:.8f} = {maintenance_total:.8f}"
        )
        trace.append(
            f"DEBUG: Recurring Total = insurance_total + maintenance_total = {insurance_total:.8f} + {maintenance_total:.8f} = {recurring_total:.8f}"
        )
        trace.append(
            f"DEBUG: Total Loss = capital_total + insurance_total + maintenance_total = {capital_total:.8f} + {insurance_total:.8f} + {maintenance_total:.8f} = {total_loss:.8f}"
        )

        return {
            "period_years": period_years,
            "start_years": start_years,
            "end_years": end_years,
            "effective_end_age": effective_end_age,
            "annual_equipment_cost_display": annual_equipment_cost_display,
            "purchase_count": purchase_count,
            "purchase_years": purchase_years,
            "purchase_mortality_mode": purchase_mortality_mode,
            "purchase_boundary_mode": boundary_mode_used,
            "capital_total": capital_total,
            "equipment_multiplier": equipment_multiplier,
            "annual_recurring_cost": annual_recurring_cost,
            "term_multiplier_start": term_start,
            "term_multiplier_end": term_end,
            "term_multiplier_life_expectancy": term_life,
            "recurring_multiplier": recurring_multiplier,
            "insurance_total": insurance_total,
            "maintenance_total": maintenance_total,
            "recurring_total": recurring_total,
            "total_loss": total_loss,
            "trace": trace,
        }

    @staticmethod
    def _to_years(replacement_every_value: float, replacement_every_unit: str) -> float:
        if replacement_every_unit == "Days":
            return replacement_every_value / 365.0
        if replacement_every_unit == "Weeks":
            return replacement_every_value / (365.0 / 7.0)
        if replacement_every_unit == "Months":
            return replacement_every_value / 12.0
        return replacement_every_value

    @staticmethod
    def _build_purchase_years(
        start_years: float,
        end_years: float,
        replacement_every_years: float,
        purchase_boundary_mode: str | None,
    ) -> List[float]:
        # PI default stream: start anchored, include start, exclude exact end.
        if purchase_boundary_mode is None:
            years: List[float] = []
            i = 0
            while True:
                y = start_years + (i * replacement_every_years)
                if y >= end_years - 1e-12:
                    break
                years.append(y)
                i += 1
            return years

        if purchase_boundary_mode == "include_start":
            purchase_count = int(math.floor((end_years - start_years) / replacement_every_years)) + 1
            return [start_years + (i * replacement_every_years) for i in range(max(0, purchase_count))]

        # default: first purchase after start (future-only stream)
        first_idx = math.floor(start_years / replacement_every_years) + 1
        purchase_count = int(math.ceil((end_years - start_years) / replacement_every_years))
        return [(first_idx + i) * replacement_every_years for i in range(max(0, purchase_count))]

    @staticmethod
    def _apply_purchase_mortality_factor(
        years: float,
        factor: float,
        purchase_mortality_mode: str,
        life_multiplier: float,
        life_expectancy_years: float,
        trace: List[str],
    ) -> float:
        if purchase_mortality_mode == "no_mortality":
            return factor
        if years == 0:
            return factor
        if purchase_mortality_mode == "use_mortality":
            survival = 0.9909 if years <= 1.0 + 1e-9 else 0.9913
            adjusted = max(0.0, factor * survival)
            trace.append(
                f"DEBUG: Purchase mortality adjustment at {years:.8f} years -> "
                f"{factor:.8f} * {survival:.8f} = {adjusted:.8f}"
            )
            return adjusted
        if life_expectancy_years <= 0:
            raise ValueError("life_expectancy_years must be greater than 0 for mortality adjustment.")
        mortality_multiplier = life_multiplier / life_expectancy_years
        adjusted = max(0.0, factor * mortality_multiplier)
        trace.append(
            f"DEBUG: Purchase mortality adjustment (PI support method) at {years:.8f} years -> "
            f"{factor:.8f} * (life_multiplier/life_expectancy_years={life_multiplier:.8f}/{life_expectancy_years:.8f}"
            f"={mortality_multiplier:.8f}) = {adjusted:.8f}"
        )
        return adjusted

    def _table35_factor(self, years: float, trace: List[str]) -> float:
        if years < 0:
            raise ValueError("years must be non-negative for Table 35 interpolation.")
        if years == 0:
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

    def _table36_multiplier(self, years: float, trace: List[str]) -> float:
        if years < 0:
            raise ValueError("years must be non-negative.")
        if years == 0:
            trace.append("DEBUG: Table 36 - 0 years at 0.50%: 0.00000000")
            return 0.0
        if years < 1.0:
            yr_lower = 0
            yr_upper = 1
            m_lower = 0.0
            m_upper = float(self.table36_vector[0])
        else:
            yr_lower = int(math.floor(years))
            yr_upper = yr_lower + 1
            if yr_upper > len(self.table36_vector):
                raise ValueError(
                    f"Table 36 vector too short for {years} years; need entry for year {yr_upper}."
                )
            m_lower = float(self.table36_vector[yr_lower - 1])
            m_upper = float(self.table36_vector[yr_upper - 1])
        interpolated = ((yr_upper - years) * m_lower) + ((years - yr_lower) * m_upper)
        trace.append(f"DEBUG: Table 36 - {yr_lower} years at 0.50%: {m_lower:.8f}")
        trace.append(f"DEBUG: Table 36 - {yr_upper} years at 0.50%: {m_upper:.8f}")
        trace.append(
            f"DEBUG: Table 36 interpolate ({yr_upper}-{years:.8f})*{m_lower:.8f} + ({years:.8f}-{yr_lower})*{m_upper:.8f} = {interpolated:.8f}"
        )
        return interpolated
