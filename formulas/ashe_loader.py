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


def load_ashe_row_by_prefix(
    workbook_path: str,
    dataset: str,
    code_prefix: str,
) -> AsheRow:
    dataset_key = dataset.strip().lower()
    if dataset_key not in _DATASET_TO_SHEET:
        raise ValueError(f"Unsupported ASHE dataset '{dataset}'.")
    sheet_name = _DATASET_TO_SHEET[dataset_key]

    wb = load_workbook(workbook_path, data_only=True, read_only=True)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found in {workbook_path}.")
    ws = wb[sheet_name]

    header_row = [ws.cell(5, c).value for c in range(1, 60)]
    percentile_cols: Dict[int, int] = {}
    for idx, val in enumerate(header_row, start=1):
        if isinstance(val, (int, float)):
            percentile_cols[int(val)] = idx

    prefix = str(code_prefix).strip()
    if not prefix:
        raise ValueError("ASHE code prefix cannot be blank.")

    # Aggregate all matching rows across regions for PI-style major/sub-major views.
    total_jobs = 0.0
    mean_acc = 0.0
    median_acc = 0.0
    percentile_acc: Dict[int, float] = {p: 0.0 for p in percentile_cols.keys()}
    has_mean = False
    has_median = False
    has_pct: Dict[int, bool] = {p: False for p in percentile_cols.keys()}
    matched = 0
    sample_profession = ""

    for row in ws.iter_rows(min_row=6, max_row=200000, values_only=True):
        if not row:
            continue
        row_code = _as_str(row[1] if len(row) > 1 else None)
        if not row_code.startswith(prefix):
            continue
        desc = _as_str(row[0] if len(row) > 0 else None)
        if not desc:
            continue
        matched += 1
        if not sample_profession:
            sample_profession = _strip_region_prefix(desc)

        jobs = _to_float(row[2] if len(row) > 2 else None) or 0.0
        mean_v = _to_float(row[5] if len(row) > 5 else None)
        median_v = _to_float(row[3] if len(row) > 3 else None)
        pct_vals = {
            p: _to_float(row[col - 1] if len(row) >= col else None)
            for p, col in percentile_cols.items()
        }

        if jobs > 0:
            total_jobs += jobs
            if mean_v is not None:
                mean_acc += mean_v * jobs
                has_mean = True
            if median_v is not None:
                median_acc += median_v * jobs
                has_median = True
            for p, v in pct_vals.items():
                if v is not None:
                    percentile_acc[p] += v * jobs
                    has_pct[p] = True

    if matched == 0:
        raise ValueError(f"ASHE code prefix '{prefix}' not found in sheet '{sheet_name}'.")

    # If jobs are missing, fallback to simple mean across matched rows.
    if total_jobs <= 0:
        return load_ashe_row(workbook_path, dataset, prefix)

    mean_out = (mean_acc / total_jobs) if has_mean else None
    median_out = (median_acc / total_jobs) if has_median else None
    pct_out: Dict[int, float] = {}
    for p, _ in percentile_cols.items():
        pct_out[p] = (percentile_acc[p] / total_jobs) if has_pct[p] else None

    return AsheRow(
        description=sample_profession or f"Code {prefix}",
        code=prefix,
        jobs_thousands=total_jobs,
        median=median_out,
        mean=mean_out,
        percentiles=pct_out,
    )


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


def _strip_region_prefix(desc: str) -> str:
    if "," in desc:
        return desc.split(",", 1)[1].strip()
    return desc.strip()
