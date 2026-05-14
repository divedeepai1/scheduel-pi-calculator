from dataclasses import dataclass
from typing import Dict, List

from .ashe_loader import load_ashe_row
from .earnings_calculation import EarningsCalculation


@dataclass
class EarningsAsheCalculation:
    earnings_calculation: EarningsCalculation

    def calculate(
        self,
        claimant_age: float,
        age_at_start: float,
        age_at_end: float,
        ashe_workbook_path: str,
        ashe_dataset: str,
        ashe_code: str,
        ashe_region_prefix: str | None,
        but_for_amount: float | None,
        but_for_ashe_field: str | None,
        but_for_frequency: str,
        but_for_is_net: bool,
        residual_amount: float | None,
        residual_ashe_field: str | None,
        residual_frequency: str,
        residual_is_net: bool,
        employment_type: str,
        region: str,
        contingency_factor: float = 0.87,
        multiplier_mode: str = "auto",
        additional_tables_csv: str | None = None,
        additional_tables_zero_csv: str | None = None,
        additional_tables_point5_csv: str | None = None,
        table35_csv: str | None = None,
        retirement_table_full_csv: str | None = None,
        life_expectancy_end_age: float | None = None,
        impairment_end_age: float | None = None,
        impaired_multiplier_method: str = "find_appropriate_age",
        round_final_multiplier_dp: int | None = 2,
        pi_round_intermediates_2dp: bool = True,
    ) -> Dict[str, float | str | List[str]]:
        trace: List[str] = []
        ashe_row = load_ashe_row(
            workbook_path=ashe_workbook_path,
            dataset=ashe_dataset,
            code=ashe_code,
            region_prefix=ashe_region_prefix,
        )
        trace.append(f"DEBUG: ASHE row = {ashe_row.description} (code={ashe_row.code})")
        trace.append(
            f"DEBUG: ASHE stats -> jobs={_fmt_opt(ashe_row.jobs_thousands)}, "
            f"median={_fmt_opt(ashe_row.median)}, mean={_fmt_opt(ashe_row.mean)}"
        )

        effective_but_for = self._resolve_amount(
            explicit_amount=but_for_amount,
            ashe_row=ashe_row,
            ashe_field=but_for_ashe_field,
            label="but-for",
            trace=trace,
        )
        effective_residual = self._resolve_amount(
            explicit_amount=residual_amount,
            ashe_row=ashe_row,
            ashe_field=residual_ashe_field,
            label="residual",
            trace=trace,
        )

        result = self.earnings_calculation.calculate(
            claimant_age=claimant_age,
            age_at_start=age_at_start,
            age_at_end=age_at_end,
            but_for_amount=effective_but_for,
            but_for_frequency=but_for_frequency,
            but_for_is_net=but_for_is_net,
            residual_amount=effective_residual,
            residual_frequency=residual_frequency,
            residual_is_net=residual_is_net,
            employment_type=employment_type,
            region=region,
            contingency_factor=contingency_factor,
            multiplier_mode=multiplier_mode,
            additional_tables_csv=additional_tables_csv,
            additional_tables_zero_csv=additional_tables_zero_csv,
            additional_tables_point5_csv=additional_tables_point5_csv,
            table35_csv=table35_csv,
            retirement_table_full_csv=retirement_table_full_csv,
            life_expectancy_end_age=life_expectancy_end_age,
            impairment_end_age=impairment_end_age,
            impaired_multiplier_method=impaired_multiplier_method,
            round_final_multiplier_dp=round_final_multiplier_dp,
            pi_round_intermediates_2dp=pi_round_intermediates_2dp,
        )
        merged_trace = trace + list(result.get("trace", []))
        out: Dict[str, float | str | List[str]] = dict(result)
        out["ashe_code_used"] = ashe_row.code
        out["ashe_description_used"] = ashe_row.description
        out["but_for_amount_used"] = effective_but_for
        out["residual_amount_used"] = effective_residual
        out["trace"] = merged_trace
        return out

    @staticmethod
    def _resolve_amount(
        explicit_amount: float | None,
        ashe_row,
        ashe_field: str | None,
        label: str,
        trace: List[str],
    ) -> float:
        if explicit_amount is not None:
            trace.append(f"DEBUG: {label} amount uses explicit input = {explicit_amount:.8f}")
            return float(explicit_amount)
        if not ashe_field:
            raise ValueError(f"Provide {label}_amount or {label}_ashe_field.")
        val = ashe_row.field_value(ashe_field)
        trace.append(f"DEBUG: {label} amount uses ASHE field '{ashe_field}' = {val:.8f}")
        return float(val)


def _fmt_opt(v: float | None) -> str:
    return "None" if v is None else f"{v:.8f}"
