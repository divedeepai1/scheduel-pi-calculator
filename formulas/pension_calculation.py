from dataclasses import dataclass
from typing import Dict, List

from .earnings_calculation import EarningsCalculation


@dataclass
class PensionCalculation:
    earnings_calculation: EarningsCalculation

    @staticmethod
    def _income_tax_uk(taxable_income: float) -> float:
        """UK income tax with personal allowance taper; NI excluded."""
        if taxable_income <= 0:
            return 0.0
        personal_allowance = 12570.0
        if taxable_income > 100000.0:
            personal_allowance = max(0.0, personal_allowance - ((taxable_income - 100000.0) / 2.0))

        taxable = max(0.0, taxable_income - personal_allowance)
        tax = 0.0
        if taxable > 0:
            basic = min(taxable, 37700.0)
            tax += basic * 0.20
        if taxable > 37700.0:
            higher_limit = 125140.0 - personal_allowance
            higher_slice = min(taxable, higher_limit) - 37700.0
            tax += max(0.0, higher_slice) * 0.40
        if taxable_income > 125140.0:
            tax += (taxable_income - 125140.0) * 0.45
        return round(tax, 2)

    @classmethod
    def _pension_to_net(cls, annual_pension: float, other_taxable_income: float) -> float:
        """
        Pension income is taxable but not NI-able.
        Computes net pension by taxing it as the marginal slice on top of other income.
        """
        before = max(0.0, other_taxable_income)
        after = before + max(0.0, annual_pension)
        tax_attributable = cls._income_tax_uk(after) - cls._income_tax_uk(before)
        return round(max(0.0, annual_pension) - tax_attributable, 2)

    def calculate(
        self,
        claimant_age: float,
        impairment_end_age: float,
        but_for_amount: float,
        but_for_is_net: bool,
        but_for_employment_type: str,
        residual_amount: float,
        residual_is_net: bool,
        residual_employment_type: str,
        region: str,
        multiplier_method: str,
        additional_tables_point5_csv: str,
        additional_tables_zero_csv: str | None = None,
        life_expectancy_basis: str = "Impaired",
        other_taxable_income: float = 0.0,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []
        retirement_age = self.earnings_calculation._infer_retirement_age_from_table()
        if impairment_end_age <= retirement_age:
            raise ValueError("Attempted to divide by zero: impairment_end_age must be greater than retirement_age.")
        if multiplier_method not in {"term_certain", "find_appropriate_age"}:
            raise ValueError("multiplier_method must be term_certain or find_appropriate_age.")
        basis = str(life_expectancy_basis).strip().lower()
        if basis not in {"impaired", "standard"}:
            raise ValueError("life_expectancy_basis must be Impaired or Standard.")

        if but_for_is_net:
            but_for_net = but_for_amount
        else:
            but_for_net = self._pension_to_net(float(but_for_amount), float(other_taxable_income))
        if residual_is_net:
            residual_net = residual_amount
        else:
            residual_net = self._pension_to_net(float(residual_amount), float(other_taxable_income))
        net_annual_loss = but_for_net - residual_net

        mortality_to_retirement = self.earnings_calculation._additional_tables_multiplier_from_csv(
            csv_path=additional_tables_point5_csv,
            age_at_trial=claimant_age,
            target_end_age=retirement_age,
        )

        if basis == "standard":
            # PI standard pension behavior aligns to whole-life based claimant anchor.
            but_for_life_multiplier = self.earnings_calculation._whole_life_interp(claimant_age)
        else:
            if multiplier_method == "term_certain":
                but_for_life_multiplier = self.earnings_calculation._table36_interp(impairment_end_age - claimant_age)
            else:
                remaining_life = impairment_end_age - claimant_age
                if additional_tables_zero_csv:
                    _, but_for_life_multiplier = self.earnings_calculation._find_appropriate_anchor_from_whole_life_additional(
                        zero_csv=additional_tables_zero_csv,
                        point5_csv=additional_tables_point5_csv,
                        remaining_life=remaining_life,
                    )
                else:
                    but_for_life_multiplier = self.earnings_calculation._whole_life_interp(claimant_age)

        pension_multiplier = but_for_life_multiplier - mortality_to_retirement
        if pension_multiplier <= 0:
            raise ValueError("Attempted to divide by zero: non-positive pension multiplier.")

        total_loss = net_annual_loss * pension_multiplier
        trace.append(f"DEBUG: But-for net annual = {but_for_net:.8f}")
        trace.append(f"DEBUG: Residual net annual = {residual_net:.8f}")
        trace.append(f"DEBUG: Other taxable income basis for pension tax = {other_taxable_income:.8f}")
        trace.append(f"DEBUG: Net annual loss = {net_annual_loss:.8f}")
        trace.append(f"DEBUG: Mortality-adjusted multiplier to retirement = {mortality_to_retirement:.8f}")
        trace.append(f"DEBUG: But-for injury life multiplier = {but_for_life_multiplier:.8f}")
        trace.append(
            f"DEBUG: Pension multiplier from retirement = {but_for_life_multiplier:.8f} - {mortality_to_retirement:.8f} = {pension_multiplier:.8f}"
        )
        trace.append(f"DEBUG: Total loss = {net_annual_loss:.8f} * {pension_multiplier:.8f} = {total_loss:.8f}")
        return {
            "retirement_age": retirement_age,
            "period_years": impairment_end_age - retirement_age,
            "but_for_net_annual": but_for_net,
            "residual_net_annual": residual_net,
            "net_annual_loss": net_annual_loss,
            "but_for_life_multiplier": but_for_life_multiplier,
            "mortality_to_retirement_multiplier": mortality_to_retirement,
            "pension_multiplier": pension_multiplier,
            "total_loss": total_loss,
            "trace": trace,
        }

