from dataclasses import dataclass
import math
from typing import Dict, List

from .earnings_calculation import EarningsCalculation
from .pension_calculation import PensionCalculation


@dataclass
class PensionEarlyReceiptCalculation:
    earnings_calculation: EarningsCalculation

    def calculate(
        self,
        claimant_age: float,
        age_at_receipt: float,
        retirement_age: float,
        impairment_end_age: float,
        expected_lump_sum: float,
        actual_lump_sum: float,
        expected_annual_rate: float,
        expected_annual_is_net: bool,
        expected_annual_employment_type: str,
        actual_annual_rate: float,
        actual_annual_is_net: bool,
        actual_annual_employment_type: str,
        region: str,
        multiplier_method: str,
        additional_tables_point5_csv: str,
        table35_csv: str,
        additional_tables_zero_csv: str | None = None,
        life_expectancy_basis: str = "Impaired",
        other_taxable_income: float = 0.0,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []
        if retirement_age <= age_at_receipt:
            years_to_retirement = retirement_age - age_at_receipt
        else:
            years_to_retirement = retirement_age - age_at_receipt
        if years_to_retirement <= 0:
            raise ValueError("years_to_retirement must be > 0 for early receipt.")

        # Lump-sum line (Longden method)
        life_multiplier_at_receipt = self.earnings_calculation._whole_life_interp(age_at_receipt)
        multiplier_to_retirement_at_receipt = self.earnings_calculation._additional_tables_multiplier_from_csv(
            csv_path=additional_tables_point5_csv,
            age_at_trial=age_at_receipt,
            target_end_age=retirement_age,
        )
        longden_factor = 1.0 - (multiplier_to_retirement_at_receipt / life_multiplier_at_receipt)

        table35_vector = EarningsCalculation._load_single_column_vector(table35_csv)
        discount_factor = EarningsCalculation._table35_interp(table35_vector, years_to_retirement)
        present_value_expected = expected_lump_sum * discount_factor
        # PI style: round UP to nearest 5.
        present_value_expected_rounded = math.ceil(present_value_expected / 5.0) * 5.0
        longden_factor_for_deduction = round(longden_factor, 4)
        lump_sum_loss = present_value_expected_rounded - (actual_lump_sum * longden_factor_for_deduction)

        # Annual pension line (reuse pension multiplier method)
        pension_calc = PensionCalculation(earnings_calculation=self.earnings_calculation)
        pension_result = pension_calc.calculate(
            claimant_age=claimant_age,
            impairment_end_age=impairment_end_age,
            but_for_amount=expected_annual_rate,
            but_for_is_net=expected_annual_is_net,
            but_for_employment_type=expected_annual_employment_type,
            residual_amount=actual_annual_rate,
            residual_is_net=actual_annual_is_net,
            residual_employment_type=actual_annual_employment_type,
            region=region,
            multiplier_method=multiplier_method,
            additional_tables_point5_csv=additional_tables_point5_csv,
            additional_tables_zero_csv=additional_tables_zero_csv,
            life_expectancy_basis=life_expectancy_basis,
            other_taxable_income=other_taxable_income,
        )
        annual_loss = float(pension_result["net_annual_loss"])
        pension_multiplier = float(pension_result["pension_multiplier"])
        pension_multiplier_for_line = round(pension_multiplier, 2)
        annual_line_total = annual_loss * pension_multiplier_for_line

        total_loss = lump_sum_loss + annual_line_total
        trace.append(f"DEBUG: Life Multiplier at Receipt = {life_multiplier_at_receipt:.8f}")
        trace.append(f"DEBUG: Multiplier to Retirement at Receipt = {multiplier_to_retirement_at_receipt:.8f}")
        trace.append(f"DEBUG: Longden Factor = 1 - ({multiplier_to_retirement_at_receipt:.8f} / {life_multiplier_at_receipt:.8f}) = {longden_factor:.8f}")
        trace.append(f"DEBUG: Years to Retirement = {years_to_retirement:.8f}")
        trace.append(f"DEBUG: Discount Factor (Table35) = {discount_factor:.8f}")
        trace.append(f"DEBUG: Present Value of Expected Lump Sum = {expected_lump_sum:.8f} * {discount_factor:.8f} = {present_value_expected:.8f}")
        trace.append(f"DEBUG: Present Value Rounded (nearest 5) = {present_value_expected_rounded:.8f}")
        trace.append(
            f"DEBUG: Lump Sum Loss = {present_value_expected_rounded:.8f} - ({actual_lump_sum:.8f} * {longden_factor_for_deduction:.8f}) = {lump_sum_loss:.8f}"
        )
        trace.append(f"DEBUG: Annual Pension Loss = {annual_loss:.8f}")
        trace.append(f"DEBUG: Other taxable income basis for pension tax = {other_taxable_income:.8f}")
        trace.append(f"DEBUG: Pension Multiplier = {pension_multiplier:.8f}")
        trace.append(
            f"DEBUG: Annual Line Total = {annual_loss:.8f} * round2({pension_multiplier:.8f})={pension_multiplier_for_line:.8f} = {annual_line_total:.8f}"
        )
        trace.append(f"DEBUG: Total Early Receipt Loss = {lump_sum_loss:.8f} + {annual_line_total:.8f} = {total_loss:.8f}")

        return {
            "life_multiplier_at_receipt": life_multiplier_at_receipt,
            "multiplier_to_retirement_at_receipt": multiplier_to_retirement_at_receipt,
            "longden_factor": longden_factor,
            "years_to_retirement": years_to_retirement,
            "discount_factor": discount_factor,
            "present_value_expected_lump_sum": present_value_expected_rounded,
            "lump_sum_loss": lump_sum_loss,
            "annual_loss": annual_loss,
            "pension_multiplier": pension_multiplier,
            "annual_line_total": annual_line_total,
            "total_loss": total_loss,
            "trace": trace,
        }

