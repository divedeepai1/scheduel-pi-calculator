import csv
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class LossOfEarningsInterpolation:
    """
    Compares two multiplier paths for retirement-age interpolation tests:
    1) Manual interpolation between nearest main retirement-age tables.
    2) Additional Tables multiplier (provided externally from PI/GAD output).
    """

    def compare(
        self,
        retirement_age_actual: float,
        retirement_age_lower: float,
        retirement_age_upper: float,
        multiplier_lower: float,
        multiplier_upper: float,
        additional_tables_multiplier: float | None = None,
    ) -> Dict[str, float | List[str] | None]:
        trace: List[str] = []
        if retirement_age_upper <= retirement_age_lower:
            raise ValueError("retirement_age_upper must be greater than retirement_age_lower.")
        if not (retirement_age_lower <= retirement_age_actual <= retirement_age_upper):
            raise ValueError("retirement_age_actual must lie between retirement_age_lower and retirement_age_upper.")

        # Para 32-style linear interpolation between nearest retirement-age tables.
        manual_multiplier = (
            ((retirement_age_upper - retirement_age_actual) * multiplier_lower)
            + ((retirement_age_actual - retirement_age_lower) * multiplier_upper)
        ) / (retirement_age_upper - retirement_age_lower)
        trace.append(
            "DEBUG: Manual interpolation = "
            f"(({retirement_age_upper:.8f} - {retirement_age_actual:.8f}) * {multiplier_lower:.8f} + "
            f"({retirement_age_actual:.8f} - {retirement_age_lower:.8f}) * {multiplier_upper:.8f}) / "
            f"({retirement_age_upper:.8f} - {retirement_age_lower:.8f}) = {manual_multiplier:.8f}"
        )

        delta = None
        pct_delta = None
        if additional_tables_multiplier is not None:
            delta = manual_multiplier - additional_tables_multiplier
            pct_delta = (delta / additional_tables_multiplier) * 100 if additional_tables_multiplier != 0 else None
            trace.append(
                f"DEBUG: Delta vs Additional Tables = {manual_multiplier:.8f} - "
                f"{additional_tables_multiplier:.8f} = {delta:.8f}"
            )
            if pct_delta is not None:
                trace.append(f"DEBUG: Percent Delta = ({delta:.8f} / {additional_tables_multiplier:.8f}) * 100 = {pct_delta:.8f}")
            else:
                trace.append("DEBUG: Percent Delta = undefined (additional_tables_multiplier is 0)")

        return {
            "manual_multiplier": manual_multiplier,
            "additional_tables_multiplier": additional_tables_multiplier,
            "delta": delta,
            "percent_delta": pct_delta,
            "trace": trace,
        }

    def compare_period_methods(
        self,
        table36_vector: List[float],
        age_at_trial: float,
        start_years_from_trial: float,
        end_years_from_trial: float,
        additional_tables_csv: str,
        start_age: float,
        end_age: float,
        contingency_factor: float = 1.0,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []
        if start_years_from_trial < 0 or end_years_from_trial < 0:
            raise ValueError("start/end years from trial must be non-negative.")
        if end_years_from_trial <= start_years_from_trial:
            raise ValueError("end_years_from_trial must be greater than start_years_from_trial.")
        if end_age <= start_age:
            raise ValueError("end_age must be greater than start_age.")
        if contingency_factor <= 0:
            raise ValueError("contingency_factor must be greater than 0.")
        if not table36_vector:
            raise ValueError("table36_vector cannot be empty.")

        manual_start = self._table36_interp(table36_vector, start_years_from_trial)
        manual_end = self._table36_interp(table36_vector, end_years_from_trial)
        manual_period = manual_end - manual_start
        manual_after = manual_period * contingency_factor
        trace.append(
            f"DEBUG: Manual period = Table36({end_years_from_trial:.8f}) - Table36({start_years_from_trial:.8f}) = "
            f"{manual_end:.8f} - {manual_start:.8f} = {manual_period:.8f}"
        )
        trace.append(
            f"DEBUG: Manual after contingency = {manual_period:.8f} * {contingency_factor:.8f} = {manual_after:.8f}"
        )

        add_start = self.additional_tables_multiplier_from_csv(
            csv_path=additional_tables_csv,
            age_at_trial=age_at_trial,
            target_end_age=start_age,
        )
        add_end = self.additional_tables_multiplier_from_csv(
            csv_path=additional_tables_csv,
            age_at_trial=age_at_trial,
            target_end_age=end_age,
        )
        add_period = add_end - add_start
        add_after = add_period * contingency_factor
        trace.append(
            f"DEBUG: Additional period = Additional({end_age:.8f}) - Additional({start_age:.8f}) = "
            f"{add_end:.8f} - {add_start:.8f} = {add_period:.8f}"
        )
        trace.append(
            f"DEBUG: Additional after contingency = {add_period:.8f} * {contingency_factor:.8f} = {add_after:.8f}"
        )

        delta = manual_after - add_after
        pct_delta = (delta / add_after) * 100 if add_after != 0 else 0.0
        trace.append(f"DEBUG: Delta (manual - additional) = {manual_after:.8f} - {add_after:.8f} = {delta:.8f}")
        trace.append(f"DEBUG: Percent Delta = ({delta:.8f} / {add_after:.8f}) * 100 = {pct_delta:.8f}")

        return {
            "manual_start": manual_start,
            "manual_end": manual_end,
            "manual_period": manual_period,
            "manual_after_contingency": manual_after,
            "additional_start": add_start,
            "additional_end": add_end,
            "additional_period": add_period,
            "additional_after_contingency": add_after,
            "delta": delta,
            "percent_delta": pct_delta,
            "trace": trace,
        }

    def compare_book_manual_vs_additional(
        self,
        claimant_age: float,
        retirement_age_actual: float,
        retirement_age_lower: float,
        retirement_age_upper: float,
        lower_table_csv: str,
        upper_table_csv: str,
        additional_tables_csv: str,
        discount_rate: float,
    ) -> Dict[str, float | List[str]]:
        trace: List[str] = []
        a = retirement_age_lower
        b = retirement_age_upper
        r = retirement_age_actual
        x = claimant_age
        if not (a <= r <= b):
            raise ValueError("retirement_age_actual must be between retirement_age_lower and retirement_age_upper.")
        if b <= a:
            raise ValueError("retirement_age_upper must be greater than retirement_age_lower.")

        # Para 33/34 method:
        # X+A-R (lookup in A table), X+B-R (lookup in B table), then weighted interpolation.
        age_for_a = x + a - r
        age_for_b = x + b - r
        m = self.multiplier_from_retirement_table_csv(lower_table_csv, age_for_a, discount_rate)
        n = self.multiplier_from_retirement_table_csv(upper_table_csv, age_for_b, discount_rate)
        manual = (((b - r) * m) + ((r - a) * n)) / (b - a)

        additional = self.additional_tables_multiplier_from_csv(
            csv_path=additional_tables_csv,
            age_at_trial=x,
            target_end_age=r,
        )
        delta = manual - additional
        pct_delta = (delta / additional) * 100 if additional != 0 else 0.0

        trace.append(f"DEBUG: A={a:.8f}, B={b:.8f}, R={r:.8f}, X={x:.8f}")
        trace.append(f"DEBUG: Age for A-table lookup = X + A - R = {age_for_a:.8f}")
        trace.append(f"DEBUG: Age for B-table lookup = X + B - R = {age_for_b:.8f}")
        trace.append(f"DEBUG: M (A-table multiplier) = {m:.8f}")
        trace.append(f"DEBUG: N (B-table multiplier) = {n:.8f}")
        trace.append(
            f"DEBUG: Manual interpolation = ((B-R)*M + (R-A)*N)/(B-A) = "
            f"(({b-r:.8f})*{m:.8f} + ({r-a:.8f})*{n:.8f})/{b-a:.8f} = {manual:.8f}"
        )
        trace.append(f"DEBUG: Additional table multiplier at end age R={r:.8f} = {additional:.8f}")
        trace.append(f"DEBUG: Delta (manual - additional) = {delta:.8f}")
        trace.append(f"DEBUG: Percent Delta = {pct_delta:.8f}")

        return {
            "manual_multiplier": manual,
            "additional_multiplier": additional,
            "delta": delta,
            "percent_delta": pct_delta,
            "trace": trace,
        }

    def additional_tables_multiplier_from_csv(
        self,
        csv_path: str,
        age_at_trial: float,
        target_end_age: float,
    ) -> float:
        if age_at_trial < 0:
            raise ValueError("age_at_trial must be non-negative.")
        if target_end_age < 0:
            raise ValueError("target_end_age must be non-negative.")

        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 3:
            raise ValueError(f"Additional tables CSV appears too short: {csv_path}")

        header = rows[0]
        year_headers: List[float] = []
        for col in header[1:]:
            try:
                year_headers.append(float(col))
            except ValueError:
                year_headers.append(float("nan"))

        age_rows: List[float] = []
        grid: List[List[float | None]] = []
        for row in rows[1:]:
            if not row:
                continue
            try:
                age_rows.append(float(row[0]))
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
            grid.append(vals)

        if not age_rows or not year_headers:
            raise ValueError(f"Could not parse additional table axes from {csv_path}")

        r0, r1, rt = self._bracket(age_rows, age_at_trial)
        c0, c1, ct = self._bracket(year_headers, target_end_age)

        v00 = self._nearest_non_empty(grid, r0, c0)
        v01 = self._nearest_non_empty(grid, r0, c1)
        v10 = self._nearest_non_empty(grid, r1, c0)
        v11 = self._nearest_non_empty(grid, r1, c1)

        top = ((1.0 - ct) * v00) + (ct * v01)
        bottom = ((1.0 - ct) * v10) + (ct * v11)
        value = ((1.0 - rt) * top) + (rt * bottom)
        return float(value)

    def multiplier_from_retirement_table_csv(
        self,
        csv_path: str,
        age_at_trial: float,
        discount_rate: float,
    ) -> float:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 3:
            raise ValueError(f"Retirement table CSV appears too short: {csv_path}")

        header = rows[0]
        rate_axis: List[float] = []
        for c in header[1:]:
            try:
                rate_axis.append(float(c))
            except ValueError:
                rate_axis.append(float("nan"))

        age_axis: List[float] = []
        grid: List[List[float]] = []
        for row in rows[1:]:
            if not row:
                continue
            try:
                age_val = float(row[0])
            except ValueError:
                continue
            vals: List[float] = []
            ok = True
            for cell in row[1:]:
                cell = cell.strip()
                if cell == "":
                    ok = False
                    break
                try:
                    vals.append(float(cell))
                except ValueError:
                    ok = False
                    break
            if not ok:
                continue
            age_axis.append(age_val)
            grid.append(vals)

        if not age_axis or not rate_axis:
            raise ValueError(f"Could not parse retirement table axes from {csv_path}")

        r0, r1, rt = self._bracket(age_axis, age_at_trial)
        c0, c1, ct = self._bracket(rate_axis, discount_rate)

        v00 = grid[r0][c0]
        v01 = grid[r0][c1]
        v10 = grid[r1][c0]
        v11 = grid[r1][c1]
        top = ((1.0 - ct) * v00) + (ct * v01)
        bottom = ((1.0 - ct) * v10) + (ct * v11)
        value = ((1.0 - rt) * top) + (rt * bottom)
        return float(value)

    @staticmethod
    def _bracket(axis: List[float], x: float) -> Tuple[int, int, float]:
        if not axis:
            raise ValueError("Axis is empty.")
        if x <= axis[0]:
            return 0, 0, 0.0
        if x >= axis[-1]:
            idx = len(axis) - 1
            return idx, idx, 0.0
        for i in range(len(axis) - 1):
            a = axis[i]
            b = axis[i + 1]
            if a <= x <= b:
                t = 0.0 if b == a else (x - a) / (b - a)
                return i, i + 1, float(t)
        idx = len(axis) - 1
        return idx, idx, 0.0

    @staticmethod
    def _nearest_non_empty(grid: List[List[float | None]], r: int, c: int) -> float:
        rows = len(grid)
        cols = len(grid[r]) if rows else 0
        if rows == 0 or cols == 0:
            raise ValueError("Grid is empty.")
        if c >= len(grid[r]):
            c = len(grid[r]) - 1
        val = grid[r][c]
        if val is not None:
            return float(val)

        radius = 1
        while radius < max(rows, cols):
            for rr in range(max(0, r - radius), min(rows, r + radius + 1)):
                cc_left = c - radius
                cc_right = c + radius
                if 0 <= cc_left < len(grid[rr]) and grid[rr][cc_left] is not None:
                    return float(grid[rr][cc_left])
                if 0 <= cc_right < len(grid[rr]) and grid[rr][cc_right] is not None:
                    return float(grid[rr][cc_right])
            radius += 1
        raise ValueError("Could not find a non-empty nearby value in additional tables grid.")

    @staticmethod
    def _table36_interp(vector: List[float], years: float) -> float:
        if years < 0:
            raise ValueError("years must be non-negative for Table36 interpolation.")
        if years == 0:
            return 0.0
        if years < 1:
            lo, hi, vl, vh = 0, 1, 0.0, float(vector[0])
            return ((hi - years) * vl) + ((years - lo) * vh)

        lo = int(years // 1)
        hi = lo + 1
        if hi > len(vector):
            raise ValueError(f"Table36 vector too short for {years} years.")
        vl = float(vector[lo - 1])
        vh = float(vector[hi - 1])
        return ((hi - years) * vl) + ((years - lo) * vh)
