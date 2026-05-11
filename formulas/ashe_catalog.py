from pathlib import Path


_TABLE_CODE_TO_LABEL = {
    "1": "Weekly pay - Gross",
    "2": "Weekly pay - Excluding overtime",
    "3": "Basic Pay - Including other pay",
    "4": "Overtime pay",
    "5": "Hourly pay - Gross",
    "6": "Hourly pay - Excluding overtime",
    "7": "Annual pay - Gross",
    "8": "Annual pay - Incentive",
    "9": "Paid hours worked - Total",
    "10": "Paid hours worked - Basic",
    "11": "Paid hours worked - Overtime",
}

_TABLE_LABEL_TO_CODE = {v.lower(): k for k, v in _TABLE_CODE_TO_LABEL.items()}


def ashe_table_labels() -> list[str]:
    return [v for _, v in sorted(_TABLE_CODE_TO_LABEL.items(), key=lambda kv: int(kv[0]))]


def resolve_ashe_workbook_path(
    year: int,
    table_label: str,
    soc_granularity: int = 3,
    provisional: bool = True,
    cv_variant: bool = False,
) -> str:
    if year != 2025:
        raise ValueError("Only ASHE year 2025 is currently bundled in local data.")
    if soc_granularity not in {3, 4}:
        raise ValueError("soc_granularity must be 3 or 4.")

    code = _TABLE_LABEL_TO_CODE.get(table_label.strip().lower())
    if code is None:
        raise ValueError(f"Unsupported ASHE table '{table_label}'.")

    suffix = "b" if cv_variant else "a"
    cv_part = " CV" if cv_variant else ""
    prov_prefix = "PROV - " if provisional else ""
    prov_dir = f"ASHE Table 15 ({soc_granularity}) 2025 Provisional"
    file_name = (
        f"{prov_prefix}Work Region Occupation SOC20 ({soc_granularity}) Table 15 ({soc_granularity})."
        f"{code}{suffix}   { _TABLE_CODE_TO_LABEL[code] } 2025{cv_part}.xlsx"
    )

    path = Path("data") / "ashetable152025provisional" / prov_dir / file_name
    if not path.exists():
        raise ValueError(f"Resolved ASHE workbook was not found: {path}")
    return str(path).replace("\\", "/")

