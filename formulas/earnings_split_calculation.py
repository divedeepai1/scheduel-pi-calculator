from dataclasses import dataclass
from typing import Dict, List

from .earnings_calculation import EarningsCalculation


@dataclass
class EarningsSplitCalculation:
    earnings_calculation: EarningsCalculation

    def calculate_split(
        self,
        claimant_age: float,
        periods: List[Dict[str, float | str | bool]],
        employment_type: str,
        region: str,
        contingency_factor: float = 0.87,
        require_contiguous: bool = True,
        multiplier_mode: str = "auto",
        additional_tables_csv: str | None = None,
        impairment_end_age: float | None = None,
        impaired_multiplier_method: str = "find_appropriate_age",
        additional_tables_zero_csv: str | None = None,
        additional_tables_point5_csv: str | None = None,
        table35_csv: str | None = None,
        retirement_table_full_csv: str | None = None,
    ) -> Dict[str, float | List[Dict[str, float]] | List[str]]:
        if not periods:
            raise ValueError("periods cannot be empty.")

        normalized = sorted(periods, key=lambda p: float(p["age_at_start"]))
        trace: List[str] = []
        total_loss = 0.0
        phase_results: List[Dict[str, float]] = []

        phase_counter = 1
        for i, p in enumerate(normalized):
            start = float(p["age_at_start"])
            end = float(p["age_at_end"])
            if end <= start:
                raise ValueError("Each period must satisfy age_at_end > age_at_start.")
            if i > 0:
                prev_end = float(normalized[i - 1]["age_at_end"])
                if start < prev_end:
                    raise ValueError("Periods cannot overlap.")
                if require_contiguous and abs(start - prev_end) > 1e-9:
                    raise ValueError("Periods must be contiguous when require_contiguous is True.")

            res = self.earnings_calculation.calculate(
                claimant_age=claimant_age,
                age_at_start=start,
                age_at_end=end,
                but_for_amount=float(p["but_for_amount"]),
                but_for_frequency=str(p.get("but_for_frequency", "Per_Year")),
                but_for_is_net=bool(p.get("but_for_is_net", False)),
                residual_amount=float(p["residual_amount"]),
                residual_frequency=str(p.get("residual_frequency", "Per_Year")),
                residual_is_net=bool(p.get("residual_is_net", False)),
                employment_type=employment_type,
                region=region,
                contingency_factor=contingency_factor,
                multiplier_mode=multiplier_mode,
                additional_tables_csv=additional_tables_csv,
                impairment_end_age=impairment_end_age,
                impaired_multiplier_method=impaired_multiplier_method,
                additional_tables_zero_csv=additional_tables_zero_csv,
                additional_tables_point5_csv=additional_tables_point5_csv,
                table35_csv=table35_csv,
                retirement_table_full_csv=retirement_table_full_csv,
            )
            total_loss += float(res["total_loss"])
            if "phase_results" in res and isinstance(res["phase_results"], list):
                for sub in res["phase_results"]:
                    sub_start = float(sub["age_at_start"])
                    sub_end = float(sub["age_at_end"])
                    sub_net = float(sub["net_annual_loss"])
                    sub_mult = float(sub["final_multiplier"])
                    sub_total = float(sub["total_loss"])
                    phase_results.append(
                        {
                            "phase": float(phase_counter),
                            "age_at_start": sub_start,
                            "age_at_end": sub_end,
                            "net_annual_loss": sub_net,
                            "final_multiplier": sub_mult,
                            "total_loss": sub_total,
                        }
                    )
                    trace.append(
                        f"DEBUG: Phase {phase_counter} -> {sub_start:.2f} to {sub_end:.2f}, "
                        f"net={sub_net:.8f}, mult={sub_mult:.8f}, total={sub_total:.8f}"
                    )
                    phase_counter += 1
            else:
                net = float(res["net_annual_loss"])
                mult = float(res["final_multiplier"])
                subtotal = float(res["total_loss"])
                phase_results.append(
                    {
                        "phase": float(phase_counter),
                        "age_at_start": start,
                        "age_at_end": end,
                        "net_annual_loss": net,
                        "final_multiplier": mult,
                        "total_loss": subtotal,
                    }
                )
                trace.append(
                    f"DEBUG: Phase {phase_counter} -> {start:.2f} to {end:.2f}, net={net:.8f}, "
                    f"mult={mult:.8f}, total={subtotal:.8f}"
                )
                phase_counter += 1

        trace.append(f"DEBUG: Split Total Loss = {total_loss:.8f}")
        return {"phase_results": phase_results, "total_loss": total_loss, "trace": trace}
