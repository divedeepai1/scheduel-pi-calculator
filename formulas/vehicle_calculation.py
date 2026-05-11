import math
import csv
from dataclasses import dataclass
from typing import Dict, List


_REPLACEMENT_UNITS = {"Days", "Weeks", "Months", "Years"}
_PURCHASE_MORTALITY_MODES = {"no_mortality", "use_mortality", "use_mortality_pi_mm"}


@dataclass
class VehicleCalculation:
    table35_vector: List[float]
    table36_vector: List[float]

    def calculate(
        self,
        claimant_age: float,
        age_at_start: float,
        age_at_end: float,
        life_expectancy_end_age: float,
        life_expectancy_years: float,
        life_multiplier: float,
        required_vehicle_cost: float,
        existing_vehicle_credit: float,
        trade_in_value: float,
        replacement_every_value: float,
        replacement_every_unit: str,
        replacement_start_age: float | None,
        increased_insurance: float,
        increased_running_costs: float,
        purchase_mortality_mode: str = "no_mortality",
    ) -> Dict[str, float | int | List[float] | List[str]]:
        trace: List[str] = []
        if not self.table35_vector or not self.table36_vector:
            raise ValueError("table35_vector and table36_vector are required.")
        if age_at_end <= age_at_start:
            raise ValueError("age_at_end must be greater than age_at_start.")
        if life_expectancy_end_age <= claimant_age:
            raise ValueError("life_expectancy_end_age must be greater than claimant_age.")
        if replacement_every_value <= 0:
            raise ValueError("replacement_every_value must be greater than 0.")
        if replacement_every_unit not in _REPLACEMENT_UNITS:
            raise ValueError(f"replacement_every_unit must be one of {sorted(_REPLACEMENT_UNITS)}.")
        if purchase_mortality_mode not in _PURCHASE_MORTALITY_MODES:
            raise ValueError(f"purchase_mortality_mode must be one of {sorted(_PURCHASE_MORTALITY_MODES)}.")
        for name, val in [
            ("required_vehicle_cost", required_vehicle_cost),
            ("existing_vehicle_credit", existing_vehicle_credit),
            ("trade_in_value", trade_in_value),
            ("increased_insurance", increased_insurance),
            ("increased_running_costs", increased_running_costs),
            ("life_multiplier", life_multiplier),
            ("life_expectancy_years", life_expectancy_years),
        ]:
            if val < 0:
                raise ValueError(f"{name} must be non-negative.")

        effective_end_age = min(age_at_end, life_expectancy_end_age)
        if effective_end_age <= age_at_start:
            raise ValueError("effective end age must be greater than age_at_start.")

        start_years = age_at_start - claimant_age
        end_years = effective_end_age - claimant_age
        if start_years < 0:
            raise ValueError("age_at_start cannot be earlier than claimant_age.")

        replacement_every_years = self._to_years(replacement_every_value, replacement_every_unit)
        initial_net_cost = required_vehicle_cost - existing_vehicle_credit
        replacement_net_cost = required_vehicle_cost - trade_in_value
        annual_extras = increased_insurance + increased_running_costs

        initial_multiplier = self._table35_factor(start_years, trace)
        initial_total = initial_net_cost * initial_multiplier

        if replacement_start_age is None:
            replacement_start_years = start_years + replacement_every_years
        else:
            if replacement_start_age <= age_at_start:
                raise ValueError("replacement_start_age must be greater than age_at_start.")
            replacement_start_years = replacement_start_age - claimant_age

        replacement_years = self._replacement_years(replacement_start_years, end_years, replacement_every_years)
        pi_mm_mortality_multiplier = None
        if purchase_mortality_mode == "use_mortality_pi_mm":
            tc_life_multiplier = self._table36_multiplier(life_expectancy_years, trace)
            if tc_life_multiplier <= 0:
                raise ValueError("Derived Table 36 life term multiplier must be greater than 0 for PI MM mode.")
            pi_mm_mortality_multiplier = life_multiplier / tc_life_multiplier
            trace.append(
                "DEBUG: PI MM mortality multiplier = life_multiplier / "
                f"Table36(life_expectancy_years) = {life_multiplier:.8f} / {tc_life_multiplier:.8f} = "
                f"{pi_mm_mortality_multiplier:.8f}"
            )
        replacements_multiplier = 0.0
        for y in replacement_years:
            f = self._table35_factor(y, trace)
            f = self._apply_purchase_mortality_factor(
                years=y,
                factor=f,
                purchase_mortality_mode=purchase_mortality_mode,
                life_multiplier=life_multiplier,
                life_expectancy_years=life_expectancy_years,
                pi_mm_mortality_multiplier=pi_mm_mortality_multiplier,
                trace=trace,
            )
            replacements_multiplier += f
        replacements_total = replacement_net_cost * replacements_multiplier

        m_start = self._table36_multiplier(start_years, trace)
        m_end = self._table36_multiplier(end_years, trace)
        m_life = self._table36_multiplier(life_expectancy_years, trace)
        annual_multiplier = ((m_end - m_start) / m_life) * life_multiplier
        insurance_total = increased_insurance * annual_multiplier
        running_total = increased_running_costs * annual_multiplier
        annual_extras_total = annual_extras * annual_multiplier
        total_loss = initial_total + replacements_total + annual_extras_total

        trace.append(f"DEBUG: Initial Net Cost = {required_vehicle_cost:.8f} - {existing_vehicle_credit:.8f} = {initial_net_cost:.8f}")
        trace.append(f"DEBUG: Replacement Net Cost = {required_vehicle_cost:.8f} - {trade_in_value:.8f} = {replacement_net_cost:.8f}")
        trace.append(f"DEBUG: Replacement Stream Start Years = {replacement_start_years:.8f}")
        trace.append(f"DEBUG: Purchase Mortality Mode = {purchase_mortality_mode}")
        trace.append(f"DEBUG: Initial Total = {initial_net_cost:.8f} * {initial_multiplier:.8f} = {initial_total:.8f}")
        trace.append(f"DEBUG: Replacements Total = {replacement_net_cost:.8f} * {replacements_multiplier:.8f} = {replacements_total:.8f}")
        trace.append(f"DEBUG: Annual Extras Multiplier = (({m_end:.8f}-{m_start:.8f})/{m_life:.8f})*{life_multiplier:.8f} = {annual_multiplier:.8f}")
        trace.append(f"DEBUG: Insurance Total = {increased_insurance:.8f} * {annual_multiplier:.8f} = {insurance_total:.8f}")
        trace.append(f"DEBUG: Running Costs Total = {increased_running_costs:.8f} * {annual_multiplier:.8f} = {running_total:.8f}")
        trace.append(f"DEBUG: Total Loss = {initial_total:.8f} + {replacements_total:.8f} + {annual_extras_total:.8f} = {total_loss:.8f}")

        return {
            "start_years": start_years,
            "end_years": end_years,
            "effective_end_age": effective_end_age,
            "initial_net_cost": initial_net_cost,
            "replacement_net_cost": replacement_net_cost,
            "replacement_every_years": replacement_every_years,
            "replacement_start_years": replacement_start_years,
            "initial_multiplier": initial_multiplier,
            "initial_total": initial_total,
            "replacement_count": len(replacement_years),
            "replacement_years": replacement_years,
            "replacements_multiplier": replacements_multiplier,
            "replacements_total": replacements_total,
            "annual_extras": annual_extras,
            "annual_multiplier": annual_multiplier,
            "insurance_total": insurance_total,
            "running_total": running_total,
            "annual_extras_total": annual_extras_total,
            "total_loss": total_loss,
            "trace": trace,
        }

    @staticmethod
    def _apply_purchase_mortality_factor(
        years: float,
        factor: float,
        purchase_mortality_mode: str,
        life_multiplier: float,
        life_expectancy_years: float,
        pi_mm_mortality_multiplier: float | None,
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
        if pi_mm_mortality_multiplier is None:
            raise ValueError("pi_mm_mortality_multiplier is required for use_mortality_pi_mm mode.")
        mortality_multiplier = pi_mm_mortality_multiplier
        adjusted = max(0.0, factor * mortality_multiplier)
        trace.append(
            f"DEBUG: Purchase mortality adjustment (PI support method) at {years:.8f} years -> "
            f"{factor:.8f} * mortality_multiplier({mortality_multiplier:.8f}) = {adjusted:.8f}"
        )
        return adjusted

    @staticmethod
    def _to_years(value: float, unit: str) -> float:
        if unit == "Days":
            return value / 365.0
        if unit == "Weeks":
            return value / (365.0 / 7.0)
        if unit == "Months":
            return value / 12.0
        return value

    @staticmethod
    def _replacement_years(first: float, end_years: float, cycle_years: float) -> List[float]:
        years: List[float] = []
        i = 0
        while True:
            y = first + (i * cycle_years)
            # PI-style boundary: do not include a purchase exactly at end age.
            if y >= end_years - 1e-12:
                break
            years.append(y)
            i += 1
        return years

    def _table35_factor(self, years: float, trace: List[str]) -> float:
        if years == 0:
            return 1.0
        if years < 1:
            lo, hi = 0, 1
            vlo, vhi = 1.0, float(self.table35_vector[0])
        else:
            lo = int(math.floor(years))
            hi = lo + 1
            if hi > len(self.table35_vector):
                raise ValueError(f"Table 35 vector too short for {years} years.")
            vlo = float(self.table35_vector[lo - 1])
            vhi = float(self.table35_vector[hi - 1])
        out = ((hi - years) * vlo) + ((years - lo) * vhi)
        trace.append(f"DEBUG: Table35({years:.8f}) between {lo} and {hi} = {out:.8f}")
        return out

    def _table36_multiplier(self, years: float, trace: List[str]) -> float:
        if years == 0:
            return 0.0
        if years < 1:
            lo, hi = 0, 1
            vlo, vhi = 0.0, float(self.table36_vector[0])
        else:
            lo = int(math.floor(years))
            hi = lo + 1
            if hi > len(self.table36_vector):
                raise ValueError(f"Table 36 vector too short for {years} years.")
            vlo = float(self.table36_vector[lo - 1])
            vhi = float(self.table36_vector[hi - 1])
        out = ((hi - years) * vlo) + ((years - lo) * vhi)
        trace.append(f"DEBUG: Table36({years:.8f}) between {lo} and {hi} = {out:.8f}")
        return out

    @staticmethod
    def derive_life_expectancy_years_from_life_multiplier(table36_vector: List[float], life_multiplier: float) -> float:
        """
        Approximate term-certain years whose Table 36 value matches the supplied life multiplier.
        This is used as the standard-mode default when an explicit LE end age override is not provided.
        """
        if not table36_vector:
            raise ValueError("table36_vector is required.")
        if life_multiplier <= 0:
            raise ValueError("life_multiplier must be greater than 0 to derive life expectancy years.")

        first = float(table36_vector[0])
        if life_multiplier <= first:
            return life_multiplier / first

        for i in range(1, len(table36_vector)):
            lo_year = float(i)
            hi_year = float(i + 1)
            lo_val = float(table36_vector[i - 1])
            hi_val = float(table36_vector[i])
            if lo_val <= life_multiplier <= hi_val:
                if hi_val == lo_val:
                    return lo_year
                frac = (life_multiplier - lo_val) / (hi_val - lo_val)
                return lo_year + frac

        raise ValueError(
            f"Cannot derive life expectancy years from life_multiplier={life_multiplier:.8f}; "
            "value is outside Table 36 range."
        )

    @staticmethod
    def derive_standard_from_additional_tables(
        zero_csv: str,
        point5_csv: str,
        claimant_age: float,
    ) -> tuple[float, float]:
        """
        Derive standard remaining-life years (0% maturity row path) and +0.5 anchor
        from Additional Tables by interpolating the row-plateau values at claimant age.
        Returns: (remaining_life_years, life_multiplier_anchor_point5)
        """
        if claimant_age < 0:
            raise ValueError("claimant_age must be non-negative.")

        zero_pairs = VehicleCalculation._row_plateau_values(zero_csv)
        p5_pairs = VehicleCalculation._row_plateau_values(point5_csv)
        remaining_life_years = VehicleCalculation._interp_by_age(zero_pairs, claimant_age)
        life_multiplier_anchor = VehicleCalculation._interp_by_age(p5_pairs, claimant_age)
        return float(remaining_life_years), float(life_multiplier_anchor)

    @staticmethod
    def derive_anchor_from_remaining_life(
        zero_csv: str,
        point5_csv: str,
        remaining_life_years: float,
    ) -> tuple[float, float]:
        """
        Inverse-map remaining life on Additional 0% to effective age, then map that age
        onto Additional +0.5% for the anchor multiplier.
        Returns: (effective_age, life_multiplier_anchor_point5)
        """
        if remaining_life_years <= 0:
            raise ValueError("remaining_life_years must be greater than 0.")
        zero_pairs = VehicleCalculation._row_plateau_values(zero_csv)
        p5_pairs = VehicleCalculation._row_plateau_values(point5_csv)
        effective_age = VehicleCalculation._inverse_age_from_value_desc(zero_pairs, remaining_life_years)
        anchor = VehicleCalculation._interp_by_age(p5_pairs, effective_age)
        return float(effective_age), float(anchor)

    @staticmethod
    def _row_plateau_values(csv_path: str) -> List[tuple[float, float]]:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        pairs: List[tuple[float, float]] = []
        for row in rows[1:]:
            if not row:
                continue
            try:
                age = float(row[0])
            except ValueError:
                continue
            vals: List[float] = []
            for cell in row[1:]:
                cell = cell.strip()
                if not cell:
                    continue
                try:
                    vals.append(float(cell))
                except ValueError:
                    continue
            if vals:
                pairs.append((age, max(vals)))
        if len(pairs) < 2:
            raise ValueError(f"Not enough usable rows in additional table {csv_path}")
        return sorted(pairs, key=lambda x: x[0])

    @staticmethod
    def _interp_by_age(pairs: List[tuple[float, float]], age: float) -> float:
        if age <= pairs[0][0]:
            return float(pairs[0][1])
        if age >= pairs[-1][0]:
            return float(pairs[-1][1])
        for (a0, v0), (a1, v1) in zip(pairs[:-1], pairs[1:]):
            if a0 <= age <= a1:
                if a1 == a0:
                    return float(v0)
                t = (age - a0) / (a1 - a0)
                return float(((1.0 - t) * v0) + (t * v1))
        return float(pairs[-1][1])

    @staticmethod
    def _inverse_age_from_value_desc(pairs: List[tuple[float, float]], target_value: float) -> float:
        # Values decrease with age in whole-life style plateau rows.
        if target_value >= pairs[0][1]:
            return float(pairs[0][0])
        if target_value <= pairs[-1][1]:
            return float(pairs[-1][0])
        for (a0, v0), (a1, v1) in zip(pairs[:-1], pairs[1:]):
            if v0 >= target_value >= v1:
                if v0 == v1:
                    return float(a0)
                t = (target_value - v1) / (v0 - v1)
                return float((t * a0) + ((1.0 - t) * a1))
        return float(pairs[-1][0])
