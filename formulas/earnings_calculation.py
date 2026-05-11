import csv
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


_FREQUENCY_FACTORS = {
    "Per_Year": 1.0,
    "Per_Month": 12.0,
    "Per_Week": 365.0 / 7.0,
}


@dataclass
class EarningsCalculation:
    table36_vector: List[float]
    retirement_table: List[Tuple[float, float]]
    whole_life_table: List[Tuple[float, float]]

    def calculate(
        self,
        claimant_age: float,
        age_at_start: float,
        age_at_end: float,
        but_for_amount: float,
        but_for_frequency: str,
        but_for_is_net: bool,
        residual_amount: float,
        residual_frequency: str,
        residual_is_net: bool,
        employment_type: str,
        region: str,
        contingency_factor: float = 0.87,
        multiplier_mode: str = "auto",
        additional_tables_csv: str | None = None,
        impairment_end_age: float | None = None,
        impaired_multiplier_method: str = "find_appropriate_age",
        additional_tables_zero_csv: str | None = None,
        additional_tables_point5_csv: str | None = None,
        table35_csv: str | None = None,
        retirement_table_full_csv: str | None = None,
        residual_after_retirement: bool = False,
        life_expectancy_end_age: float | None = None,
        round_final_multiplier_dp: int | None = None,
        pi_round_intermediates_2dp: bool = False,
        _allow_auto_split: bool = True,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []
        if age_at_end <= age_at_start:
            raise ValueError("age_at_end must be greater than age_at_start.")
        if age_at_start < claimant_age:
            raise ValueError("age_at_start cannot be earlier than claimant_age.")
        if contingency_factor <= 0:
            raise ValueError("contingency_factor must be greater than 0.")
        if but_for_frequency not in _FREQUENCY_FACTORS or residual_frequency not in _FREQUENCY_FACTORS:
            raise ValueError("Frequency must be one of Per_Year, Per_Month, Per_Week.")
        if employment_type not in {"employed", "self_employed"}:
            raise ValueError("employment_type must be employed or self_employed.")
        if region not in {"England_Wales_NI", "Scotland"}:
            raise ValueError("region must be England_Wales_NI or Scotland.")
        if region == "Scotland":
            raise ValueError("Scotland tax bands are not implemented yet.")
        if multiplier_mode not in {"auto", "manual", "additional"}:
            raise ValueError("multiplier_mode must be auto, manual, or additional.")
        if impaired_multiplier_method not in {"find_appropriate_age", "term_certain"}:
            raise ValueError("impaired_multiplier_method must be find_appropriate_age or term_certain.")

        retirement_age = self._infer_retirement_age_from_table()
        apply_ni = age_at_start < retirement_age - 1e-9

        effective_age_at_end = age_at_end
        if life_expectancy_end_age is not None:
            effective_age_at_end = min(effective_age_at_end, float(life_expectancy_end_age))
            if effective_age_at_end < age_at_end - 1e-9:
                trace.append(
                    f"DEBUG: Capping age_at_end from {age_at_end:.8f} to life_expectancy_end_age {effective_age_at_end:.8f}."
                )
        # PI-style impaired earnings are capped at impairment end age when that cap is pre-retirement.
        if impairment_end_age is not None and impairment_end_age <= retirement_age + 1e-9:
            effective_age_at_end = min(effective_age_at_end, impairment_end_age)
            if effective_age_at_end < age_at_end - 1e-9:
                trace.append(
                    f"DEBUG: Capping age_at_end from {age_at_end:.8f} to impairment_end_age {effective_age_at_end:.8f}."
                )

        # PI-style dynamic segmentation when range crosses retirement:
        # pre-retirement uses but-for/residual as entered; post-retirement
        # keeps but-for but typically stops residual stream.
        if _allow_auto_split and age_at_start < retirement_age < effective_age_at_end:
            pre_result = self.calculate(
                claimant_age=claimant_age,
                age_at_start=age_at_start,
                age_at_end=retirement_age,
                but_for_amount=but_for_amount,
                but_for_frequency=but_for_frequency,
                but_for_is_net=but_for_is_net,
                residual_amount=residual_amount,
                residual_frequency=residual_frequency,
                residual_is_net=residual_is_net,
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
                residual_after_retirement=residual_after_retirement,
                life_expectancy_end_age=life_expectancy_end_age,
                round_final_multiplier_dp=round_final_multiplier_dp,
                pi_round_intermediates_2dp=pi_round_intermediates_2dp,
                _allow_auto_split=False,
            )
            post_residual_amount = residual_amount if residual_after_retirement else 0.0
            post_residual_is_net = residual_is_net if residual_after_retirement else True
            post_result = self.calculate(
                claimant_age=claimant_age,
                age_at_start=retirement_age,
                age_at_end=effective_age_at_end,
                but_for_amount=but_for_amount,
                but_for_frequency=but_for_frequency,
                but_for_is_net=but_for_is_net,
                residual_amount=post_residual_amount,
                residual_frequency=residual_frequency,
                residual_is_net=post_residual_is_net,
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
                residual_after_retirement=residual_after_retirement,
                life_expectancy_end_age=life_expectancy_end_age,
                round_final_multiplier_dp=round_final_multiplier_dp,
                pi_round_intermediates_2dp=pi_round_intermediates_2dp,
                _allow_auto_split=False,
            )
            phase_results = [
                {
                    "phase": 1.0,
                    "age_at_start": float(age_at_start),
                    "age_at_end": float(retirement_age),
                    "net_annual_loss": float(pre_result["net_annual_loss"]),
                    "final_multiplier": float(pre_result["final_multiplier"]),
                    "total_loss": float(pre_result["total_loss"]),
                },
                {
                    "phase": 2.0,
                    "age_at_start": float(retirement_age),
                    "age_at_end": float(effective_age_at_end),
                    "net_annual_loss": float(post_result["net_annual_loss"]),
                    "final_multiplier": float(post_result["final_multiplier"]),
                    "total_loss": float(post_result["total_loss"]),
                },
            ]
            total_loss = float(pre_result["total_loss"]) + float(post_result["total_loss"])
            trace.append(
                "DEBUG: Auto-split across retirement boundary enabled: "
                f"{age_at_start:.8f}->{retirement_age:.8f} and {retirement_age:.8f}->{effective_age_at_end:.8f}"
            )
            trace.extend([f"DEBUG: PRE {line}" for line in pre_result.get("trace", [])])
            trace.extend([f"DEBUG: POST {line}" for line in post_result.get("trace", [])])
            trace.append(f"DEBUG: Auto-split total loss = {total_loss:.8f}")
            return {
                "period_years": float(effective_age_at_end - age_at_start),
                "but_for_annual_net": float(pre_result["but_for_annual_net"]),
                "residual_annual_net": float(pre_result["residual_annual_net"]),
                "net_annual_loss": float(pre_result["net_annual_loss"]),
                "period_multiplier": float(pre_result["period_multiplier"]),
                "final_multiplier": float(pre_result["final_multiplier"]),
                "total_loss": total_loss,
                "multiplier_mode_used": str(pre_result["multiplier_mode_used"]),
                "phase_results": phase_results,
                "trace": trace,
            }

        period_years = max(0.0, effective_age_at_end - age_at_start)
        start_years_from_trial = age_at_start - claimant_age
        end_years_from_trial = effective_age_at_end - claimant_age
        trace.append(f"DEBUG: Period years = {period_years:.8f}")

        but_for_gross_annual = but_for_amount * _FREQUENCY_FACTORS[but_for_frequency]
        residual_gross_annual = residual_amount * _FREQUENCY_FACTORS[residual_frequency]
        trace.append(f"DEBUG: But-for annual gross = {but_for_gross_annual:.8f}")
        trace.append(f"DEBUG: Residual annual gross = {residual_gross_annual:.8f}")

        if but_for_is_net:
            but_for_net_annual = but_for_gross_annual
        else:
            but_for_net_annual = self._to_net_annual(
                but_for_gross_annual,
                employment_type,
                region,
                apply_ni=apply_ni,
            )
        if residual_is_net:
            residual_net_annual = residual_gross_annual
        else:
            residual_net_annual = self._to_net_annual(
                residual_gross_annual,
                employment_type,
                region,
                apply_ni=apply_ni,
            )

        net_annual_loss = but_for_net_annual - residual_net_annual
        trace.append(f"DEBUG: But-for annual net = {but_for_net_annual:.8f}")
        trace.append(f"DEBUG: Residual annual net = {residual_net_annual:.8f}")
        trace.append(f"DEBUG: Net annual loss = {net_annual_loss:.8f}")

        effective_mode = multiplier_mode
        if multiplier_mode == "auto":
            # Default to PI trace-style manual path unless caller explicitly requests additional.
            effective_mode = "manual"
        trace.append(f"DEBUG: Multiplier mode requested={multiplier_mode}, used={effective_mode}")

        if effective_mode == "additional":
            if not additional_tables_csv:
                raise ValueError("additional_tables_csv is required when multiplier_mode resolves to additional.")
            start_additional = self._additional_tables_multiplier_from_csv(
                csv_path=additional_tables_csv,
                age_at_trial=claimant_age,
                target_end_age=age_at_start,
            )
            end_additional = self._additional_tables_multiplier_from_csv(
                csv_path=additional_tables_csv,
                age_at_trial=claimant_age,
                target_end_age=effective_age_at_end,
            )
            period_multiplier = end_additional - start_additional
            trace.append(
                f"DEBUG: Additional period multiplier = Additional({effective_age_at_end:.8f}) - Additional({age_at_start:.8f}) = "
                f"{end_additional:.8f} - {start_additional:.8f} = {period_multiplier:.8f}"
            )
        else:
            if period_years <= 0.0:
                period_multiplier = 0.0
                trace.append("DEBUG: Effective period is non-positive after impairment cap; period multiplier set to 0.")
                final_multiplier = period_multiplier * contingency_factor
                if round_final_multiplier_dp is not None:
                    original_final = final_multiplier
                    final_multiplier = round(final_multiplier, int(round_final_multiplier_dp))
                    trace.append(
                        f"DEBUG: Rounded final multiplier ({int(round_final_multiplier_dp)} dp) = "
                        f"{original_final:.8f} -> {final_multiplier:.8f}"
                    )
                total_loss = net_annual_loss * final_multiplier
                trace.append(
                    f"DEBUG: Final multiplier = {period_multiplier:.8f} * {contingency_factor:.8f} = {final_multiplier:.8f}"
                )
                trace.append(f"DEBUG: Total loss = {net_annual_loss:.8f} * {final_multiplier:.8f} = {total_loss:.8f}")
                return {
                    "period_years": period_years,
                    "but_for_annual_net": but_for_net_annual,
                    "residual_annual_net": residual_net_annual,
                    "net_annual_loss": net_annual_loss,
                    "period_multiplier": period_multiplier,
                    "final_multiplier": final_multiplier,
                    "total_loss": total_loss,
                    "multiplier_mode_used": effective_mode,
                    "trace": trace,
                }

            retirement_years_from_trial = retirement_age - claimant_age
            term_full_to_retirement = self._table36_interp(retirement_years_from_trial)
            term_at_start = self._table36_interp(start_years_from_trial)
            term_at_end = self._table36_interp(end_years_from_trial)
            if pi_round_intermediates_2dp:
                term_full_to_retirement = round(term_full_to_retirement, 2)
                term_at_start = round(term_at_start, 2)
                term_at_end = round(term_at_end, 2)
            term_slice = term_at_end - term_at_start
            if term_full_to_retirement <= 0:
                raise ValueError("Invalid retirement basis: full term-certain to retirement must be > 0.")

            retirement_multiplier = self._retirement_interp(claimant_age)
            if pi_round_intermediates_2dp:
                retirement_multiplier = round(retirement_multiplier, 2)
            if impairment_end_age is not None:
                if additional_tables_point5_csv is None:
                    additional_tables_point5_csv = additional_tables_csv

                if impairment_end_age > retirement_age + 1e-9:
                    # When impairment extends beyond retirement, PI behavior aligns with retirement anchor lookup.
                    if not additional_tables_point5_csv:
                        raise ValueError(
                            "additional_tables_point5_csv (or additional_tables_csv) required for impairment_end_age > retirement."
                        )
                    retirement_multiplier = self._additional_tables_multiplier_from_csv(
                        csv_path=additional_tables_point5_csv,
                        age_at_trial=claimant_age,
                        target_end_age=retirement_age,
                    )
                    trace.append(
                        "DEBUG: impairment_end_age > retirement_age; using Additional +0.5% retirement anchor "
                        f"= {retirement_multiplier:.8f}"
                    )
                else:
                    deferred_years = max(0.0, age_at_start - claimant_age)
                    deferred_factor = 1.0
                    if deferred_years > 1e-9:
                        if not table35_csv:
                            raise ValueError("table35_csv is required when deferred period is present for impaired branch.")
                        table35_vector = self._load_single_column_vector(table35_csv)
                        deferred_factor = self._table35_interp(table35_vector, deferred_years)
                    if impaired_multiplier_method == "term_certain":
                        anchor_years = max(0.0, impairment_end_age - age_at_start)
                        retirement_multiplier = self._table36_interp(anchor_years) * deferred_factor
                        trace.append(
                            f"DEBUG: impaired term-certain anchor years={anchor_years:.8f}, deferred_factor={deferred_factor:.8f}, "
                            f"retirement_multiplier={retirement_multiplier:.8f}"
                        )
                    else:
                        remaining_life = max(0.0, impairment_end_age - age_at_start)
                        if additional_tables_zero_csv and additional_tables_point5_csv:
                            effective_age, anchor = self._find_appropriate_anchor_from_whole_life_additional(
                                zero_csv=additional_tables_zero_csv,
                                point5_csv=additional_tables_point5_csv,
                                remaining_life=remaining_life,
                            )
                        elif retirement_table_full_csv:
                            anchor = self._find_appropriate_anchor_from_retirement_table(
                                csv_path=retirement_table_full_csv,
                                remaining_life=remaining_life,
                                discount_rate=0.5,
                            )
                            effective_age = float("nan")
                        else:
                            raise ValueError(
                                "find_appropriate_age needs both additional_tables_zero_csv/additional_tables_point5_csv "
                                "or retirement_table_full_csv."
                            )
                        retirement_multiplier = anchor * deferred_factor
                        trace.append(
                            f"DEBUG: impaired find-appropriate-age remaining_life={remaining_life:.8f}, "
                            f"effective_age={effective_age:.8f}, anchor={anchor:.8f}, deferred_factor={deferred_factor:.8f}, "
                            f"retirement_multiplier={retirement_multiplier:.8f}"
                        )

            if effective_age_at_end <= retirement_age + 1e-9:
                if (
                    impairment_end_age is not None
                    and impairment_end_age <= retirement_age
                    and impaired_multiplier_method in {"find_appropriate_age", "term_certain"}
                ):
                    impairment_years_from_trial = max(0.0, impairment_end_age - claimant_age)
                    term_at_impairment = self._table36_interp(impairment_years_from_trial)
                    if pi_round_intermediates_2dp:
                        term_at_impairment = round(term_at_impairment, 2)
                    denom = term_at_impairment - term_at_start
                    if denom <= 0.0:
                        period_multiplier = 0.0
                    else:
                        period_multiplier = (term_slice / denom) * retirement_multiplier
                    trace.append(
                        f"DEBUG: Apportion impaired pre-retirement period = (Table36({end_years_from_trial:.8f}) - Table36({start_years_from_trial:.8f})) / "
                        f"(Table36({impairment_years_from_trial:.8f}) - Table36({start_years_from_trial:.8f})) * RetirementMultiplier"
                    )
                    trace.append(
                        f"DEBUG: = ({term_at_end:.8f} - {term_at_start:.8f}) / ({term_at_impairment:.8f} - {term_at_start:.8f}) * "
                        f"{retirement_multiplier:.8f} = {period_multiplier:.8f}"
                    )
                else:
                    period_multiplier = (term_slice / term_full_to_retirement) * retirement_multiplier
                    trace.append(
                        f"DEBUG: Apportion pre-retirement period = (Table36({end_years_from_trial:.8f}) - Table36({start_years_from_trial:.8f})) / "
                        f"Table36({retirement_years_from_trial:.8f}) * RetirementMultiplier"
                    )
                    trace.append(
                        f"DEBUG: = ({term_at_end:.8f} - {term_at_start:.8f}) / {term_full_to_retirement:.8f} * {retirement_multiplier:.8f} = {period_multiplier:.8f}"
                    )
                trace.append(
                    f"DEBUG: Retirement multiplier at claimant age ({claimant_age:.8f}) = {retirement_multiplier:.8f}"
                )
            else:
                # PI-style post-retirement apportionment using term-certain ratio over retirement denominator.
                term_at_retirement = self._table36_interp(retirement_years_from_trial)
                if pi_round_intermediates_2dp:
                    term_at_retirement = round(term_at_retirement, 2)
                period_multiplier = ((term_at_end - term_at_retirement) / term_full_to_retirement) * retirement_multiplier
                trace.append(
                    f"DEBUG: Post-retirement apportionment = (Table36({end_years_from_trial:.8f}) - Table36({retirement_years_from_trial:.8f})) / "
                    f"Table36({retirement_years_from_trial:.8f}) * RetirementMultiplier"
                )
                trace.append(
                    f"DEBUG: = ({term_at_end:.8f} - {term_at_retirement:.8f}) / {term_full_to_retirement:.8f} * "
                    f"{retirement_multiplier:.8f} = {period_multiplier:.8f}"
                )

        final_multiplier = period_multiplier * contingency_factor
        if round_final_multiplier_dp is not None:
            original_final = final_multiplier
            final_multiplier = round(final_multiplier, int(round_final_multiplier_dp))
            trace.append(
                f"DEBUG: Rounded final multiplier ({int(round_final_multiplier_dp)} dp) = "
                f"{original_final:.8f} -> {final_multiplier:.8f}"
            )
        total_loss = net_annual_loss * final_multiplier
        trace.append(f"DEBUG: Final multiplier = {period_multiplier:.8f} * {contingency_factor:.8f} = {final_multiplier:.8f}")
        trace.append(f"DEBUG: Total loss = {net_annual_loss:.8f} * {final_multiplier:.8f} = {total_loss:.8f}")

        return {
            "period_years": period_years,
            "but_for_annual_net": but_for_net_annual,
            "residual_annual_net": residual_net_annual,
            "net_annual_loss": net_annual_loss,
            "period_multiplier": period_multiplier,
            "final_multiplier": final_multiplier,
            "total_loss": total_loss,
            "multiplier_mode_used": effective_mode,
            "trace": trace,
        }

    def _solve_effective_age_from_remaining_life(self, zero_csv: str, target_end_age: float, remaining_life: float) -> float:
        low = 0.0
        high = min(target_end_age, 125.0)
        # value(age) is generally decreasing by age for fixed target_end_age
        for _ in range(40):
            mid = (low + high) / 2.0
            val = self._additional_tables_multiplier_from_csv(zero_csv, mid, target_end_age)
            if val > remaining_life:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    @staticmethod
    def _find_appropriate_anchor_from_whole_life_additional(
        zero_csv: str,
        point5_csv: str,
        remaining_life: float,
    ) -> Tuple[float, float]:
        def _row_plateau_values(csv_path: str) -> List[Tuple[float, float]]:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
            pairs: List[Tuple[float, float]] = []
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
            return pairs

        zero_pairs = _row_plateau_values(zero_csv)
        p5_pairs = _row_plateau_values(point5_csv)
        p5_map = {age: val for age, val in p5_pairs}
        joint: List[Tuple[float, float, float]] = []
        for age, z in zero_pairs:
            if age in p5_map:
                joint.append((age, z, p5_map[age]))
        if len(joint) < 2:
            raise ValueError("Could not align age rows between additional 0% and 0.5% tables.")

        # At maturity rows, whole-life style values decrease by age.
        if remaining_life >= joint[0][1]:
            return joint[0][0], joint[0][2]
        if remaining_life <= joint[-1][1]:
            return joint[-1][0], joint[-1][2]
        for (age_a, z_a, p_a), (age_b, z_b, p_b) in zip(joint[:-1], joint[1:]):
            if z_a >= remaining_life >= z_b:
                if z_a == z_b:
                    return age_a, p_a
                t = (remaining_life - z_b) / (z_a - z_b)
                eff_age = (t * age_a) + ((1.0 - t) * age_b)
                anchor = (t * p_a) + ((1.0 - t) * p_b)
                return eff_age, anchor
        return joint[-1][0], joint[-1][2]

    @staticmethod
    def _load_single_column_vector(csv_path: str) -> List[float]:
        vector: List[float] = []
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                try:
                    vector.append(float(row[0]))
                except (ValueError, IndexError):
                    continue
        if not vector:
            raise ValueError(f"No numeric values found in {csv_path}.")
        return vector

    @staticmethod
    def _find_appropriate_anchor_from_retirement_table(
        csv_path: str,
        remaining_life: float,
        discount_rate: float,
    ) -> float:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 3:
            raise ValueError(f"Invalid retirement table CSV: {csv_path}")
        header = rows[0]
        try:
            col_0 = header.index("0.0")
            col_dr = header.index(str(discount_rate))
        except ValueError as exc:
            raise ValueError(f"Required discount columns not found in {csv_path}") from exc

        life_pairs: List[Tuple[float, float]] = []
        for r in rows[1:]:
            if len(r) <= max(col_0, col_dr):
                continue
            try:
                life0 = float(r[col_0])
                life_dr = float(r[col_dr])
            except ValueError:
                continue
            life_pairs.append((life0, life_dr))
        if len(life_pairs) < 2:
            raise ValueError(f"Not enough numeric rows in {csv_path}")

        # In these tables, 0% values decrease with age.
        if remaining_life >= life_pairs[0][0]:
            return life_pairs[0][1]
        if remaining_life <= life_pairs[-1][0]:
            return life_pairs[-1][1]
        for (l0a, lra), (l0b, lrb) in zip(life_pairs[:-1], life_pairs[1:]):
            if l0a >= remaining_life >= l0b:
                if l0a == l0b:
                    return lra
                t = (remaining_life - l0b) / (l0a - l0b)
                return (t * lra) + ((1.0 - t) * lrb)
        return life_pairs[-1][1]

    @staticmethod
    def _table35_interp(vector: List[float], years: float) -> float:
        if years <= 0:
            return 1.0
        if years < 1:
            return 1.0 + ((float(vector[0]) - 1.0) * years)
        lo = int(math.floor(years))
        hi = lo + 1
        if hi > len(vector):
            return float(vector[-1])
        v_lo = float(vector[lo - 1])
        v_hi = float(vector[hi - 1])
        return ((hi - years) * v_lo) + ((years - lo) * v_hi)

    @staticmethod
    def load_retirement_table(csv_path: str, discount_rate: float = 0.5) -> List[Tuple[float, float]]:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 2:
            raise ValueError(f"Invalid retirement table file: {csv_path}")
        header = rows[0]
        try:
            col_idx = header.index(str(discount_rate))
        except ValueError as exc:
            raise ValueError(f"Discount rate column {discount_rate} not found in {csv_path}") from exc

        table: List[Tuple[float, float]] = []
        for r in rows[1:]:
            if len(r) <= col_idx:
                continue
            try:
                age = float(r[0])
                val = float(r[col_idx])
            except ValueError:
                continue
            table.append((age, val))
        if not table:
            raise ValueError(f"No usable rows found in retirement table {csv_path}")
        return table

    def _table36_interp(self, years: float) -> float:
        if years <= 0:
            return 0.0
        if years < 1:
            return years * float(self.table36_vector[0])
        lo = int(math.floor(years))
        hi = lo + 1
        if hi > len(self.table36_vector):
            raise ValueError(f"Table36 vector too short for {years} years")
        v_lo = float(self.table36_vector[lo - 1])
        v_hi = float(self.table36_vector[hi - 1])
        return ((hi - years) * v_lo) + ((years - lo) * v_hi)

    def _retirement_interp(self, age: float) -> float:
        return self._interp_age_table(self.retirement_table, age)

    def _whole_life_interp(self, age: float) -> float:
        return self._interp_age_table(self.whole_life_table, age)

    def _infer_retirement_age_from_table(self) -> float:
        if not self.retirement_table:
            raise ValueError("retirement_table is empty.")
        # Ogden retirement tables are typically keyed by age up to (retirement_age - 1).
        return float(self.retirement_table[-1][0]) + 1.0

    def _additional_tables_multiplier_from_csv(
        self,
        csv_path: str,
        age_at_trial: float,
        target_end_age: float,
    ) -> float:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 3:
            raise ValueError(f"Additional tables CSV appears too short: {csv_path}")

        header = rows[0]
        age_axis: List[float] = []
        end_age_axis: List[float] = []
        for col in header[1:]:
            try:
                end_age_axis.append(float(col))
            except ValueError:
                end_age_axis.append(float("nan"))

        grid: List[List[float | None]] = []
        for row in rows[1:]:
            if not row:
                continue
            try:
                row_age = float(row[0])
            except ValueError:
                continue
            vals: List[float | None] = []
            for cell in row[1:]:
                cell = cell.strip()
                if cell == "":
                    vals.append(None)
                else:
                    try:
                        vals.append(float(cell))
                    except ValueError:
                        vals.append(None)
            age_axis.append(row_age)
            grid.append(vals)

        if not age_axis or not end_age_axis:
            raise ValueError(f"Could not parse additional table axes from {csv_path}")

        r0, r1, rt = self._bracket(age_axis, age_at_trial)
        c0, c1, ct = self._bracket(end_age_axis, target_end_age)
        v00 = self._nearest_non_empty(grid, r0, c0)
        v01 = self._nearest_non_empty(grid, r0, c1)
        v10 = self._nearest_non_empty(grid, r1, c0)
        v11 = self._nearest_non_empty(grid, r1, c1)
        top = ((1.0 - ct) * v00) + (ct * v01)
        bottom = ((1.0 - ct) * v10) + (ct * v11)
        return float(((1.0 - rt) * top) + (rt * bottom))

    @staticmethod
    def _interp_age_table(table: List[Tuple[float, float]], age: float) -> float:
        if age <= table[0][0]:
            return table[0][1]
        if age >= table[-1][0]:
            return table[-1][1]
        for i in range(len(table) - 1):
            a0, v0 = table[i]
            a1, v1 = table[i + 1]
            if a0 <= age <= a1:
                if a1 == a0:
                    return v0
                t = (age - a0) / (a1 - a0)
                return ((1 - t) * v0) + (t * v1)
        return table[-1][1]

    @staticmethod
    def _bracket(axis: List[float], x: float) -> Tuple[int, int, float]:
        valid = [(i, v) for i, v in enumerate(axis) if not math.isnan(v)]
        if not valid:
            raise ValueError("Axis has no numeric values for interpolation.")
        if x <= valid[0][1]:
            return valid[0][0], valid[0][0], 0.0
        if x >= valid[-1][1]:
            return valid[-1][0], valid[-1][0], 0.0
        for (i0, v0), (i1, v1) in zip(valid[:-1], valid[1:]):
            if v0 <= x <= v1:
                if v1 == v0:
                    return i0, i1, 0.0
                t = (x - v0) / (v1 - v0)
                return i0, i1, t
        return valid[-1][0], valid[-1][0], 0.0

    @staticmethod
    def _nearest_non_empty(grid: List[List[float | None]], r: int, c: int) -> float:
        max_radius = max(len(grid), len(grid[0]) if grid else 0)
        for radius in range(max_radius + 1):
            rmin = max(0, r - radius)
            rmax = min(len(grid) - 1, r + radius)
            cmin = max(0, c - radius)
            cmax = min(len(grid[0]) - 1, c + radius) if grid and grid[0] else 0
            for rr in range(rmin, rmax + 1):
                for cc in range(cmin, cmax + 1):
                    val = grid[rr][cc]
                    if val is not None:
                        return float(val)
        raise ValueError("No numeric cell found near interpolation point in additional table.")

    @staticmethod
    def _to_net_annual(gross: float, employment_type: str, region: str, apply_ni: bool = True) -> float:
        # Region currently restricted to England/Wales/NI path.
        personal_allowance = 12570.0
        if gross > 100000.0:
            personal_allowance = max(0.0, personal_allowance - ((gross - 100000.0) / 2.0))

        ni = 0.0
        if apply_ni:
            if employment_type == "employed":
                # PI examples align with a NI primary threshold of 12,584.
                ni_primary_threshold = 12584.0
                if gross > ni_primary_threshold:
                    ni += (min(gross, 50270.0) - ni_primary_threshold) * 0.08
                if gross > 50270.0:
                    ni += (gross - 50270.0) * 0.02
            else:
                # PI examples use fixed Class 2 (182) plus Class 4 where applicable.
                if gross > 0:
                    ni += 182.0
                if gross > 12570.0:
                    ni += (min(gross, 50270.0) - 12570.0) * 0.06
                if gross > 50270.0:
                    ni += (gross - 50270.0) * 0.02

        taxable = max(0.0, gross - personal_allowance)
        tax = 0.0
        if taxable > 0:
            basic = min(taxable, 37700.0)
            tax += basic * 0.20
        if taxable > 37700.0:
            higher_limit = 125140.0 - personal_allowance
            higher_slice = min(taxable, higher_limit) - 37700.0
            tax += max(0.0, higher_slice) * 0.40
        if gross > 125140.0:
            tax += (gross - 125140.0) * 0.45

        tax = round(tax, 2)
        ni = round(ni, 2)
        return round(gross - (tax + ni), 2)
