from dataclasses import dataclass
from typing import Dict

from openpyxl import load_workbook


_DATASET_TO_SHEET = {
    "all_workers": "All",
    "all_male_workers": "Male",
    "all_female_workers": "Female",
    "all_full_time_workers": "Full-Time",
    "all_part_time_workers": "Part-Time",
    "male_full_time_workers": "Male Full-Time",
    "male_part_time_workers": "Male Part-Time",
    "female_full_time_workers": "Female Full-Time",
    "female_part_time_workers": "Female Part-Time",
}


@dataclass
class AsheRow:
    description: str
    code: str
    jobs_thousands: float | None
    median: float | None
    mean: float | None
    percentiles: Dict[int, float]

    def field_value(self, field: str) -> float:
        normalized = field.strip().lower()
        if normalized == "median":
            val = self.median
        elif normalized == "mean":
            val = self.mean
        elif normalized.startswith("p"):
            p = int(normalized[1:])
            val = self.percentiles.get(p)
        else:
            raise ValueError(f"Unsupported ASHE field '{field}'. Use median, mean, or pXX (e.g. p50).")
        if val is None:
            raise ValueError(f"ASHE field '{field}' is unavailable for code {self.code} in selected dataset.")
        return float(val)


def load_ashe_row(
    workbook_path: str,
    dataset: str,
    code: str,
    region_prefix: str | None = None,
) -> AsheRow:
    dataset_key = dataset.strip().lower()
    if dataset_key not in _DATASET_TO_SHEET:
        raise ValueError(f"Unsupported ASHE dataset '{dataset}'.")
    sheet_name = _DATASET_TO_SHEET[dataset_key]

    wb = load_workbook(workbook_path, data_only=True, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in {workbook_path}.")
    ws = wb[sheet_name]

    # Header pattern in these ASHE workbooks:
    # row 5: Description | Code | (thousand) | Median | ... | Mean | ... | percentile columns...
    header_row = [ws.cell(5, c).value for c in range(1, 60)]
    percentile_cols: Dict[int, int] = {}
    for idx, val in enumerate(header_row, start=1):
        if isinstance(val, (int, float)):
            percentile_cols[int(val)] = idx

    code_str = str(code).strip()
    region_prefix_norm = region_prefix.strip().lower() if region_prefix else None
    best: AsheRow | None = None
    for row in ws.iter_rows(min_row=6, max_row=200000, values_only=True):
        if not row:
            continue
        row_code = _as_str(row[1] if len(row) > 1 else None)
        if row_code != code_str:
            continue
        desc = _as_str(row[0] if len(row) > 0 else None)
        if not desc:
            continue
        if region_prefix_norm:
            if not desc.lower().strip().startswith(region_prefix_norm):
                continue
        candidate = AsheRow(
            description=desc,
            code=row_code,
            jobs_thousands=_to_float(row[2] if len(row) > 2 else None),
            median=_to_float(row[3] if len(row) > 3 else None),
            mean=_to_float(row[5] if len(row) > 5 else None),
            percentiles={
                p: _to_float(row[col - 1] if len(row) >= col else None)
                for p, col in percentile_cols.items()
            },
        )
        # Prefer a row with at least one useful earnings value.
        if candidate.median is not None or candidate.mean is not None or any(
            v is not None for v in candidate.percentiles.values()
        ):
            best = candidate
            break
        if best is None:
            best = candidate

    if best is None:
        msg = f"ASHE code '{code_str}' not found in sheet '{sheet_name}'."
        if region_prefix:
            msg += f" Region prefix filter='{region_prefix}'."
        raise ValueError(msg)
    return best


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in {"", "x", "X", ":", ".."}:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _as_str(v: object) -> str:
    if v is None:
        return ""
    return str(v).strip()
