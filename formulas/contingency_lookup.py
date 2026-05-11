import csv
from functools import lru_cache
from pathlib import Path


def _norm_status(value: str) -> str:
    v = str(value).strip().lower()
    return {
        "working employed": "working_employed",
        "working unemployed": "working_unemployed",
        "not started career": "not_started_career",
        "retired": "retired",
        "no return": "no_return",
    }.get(v, v.replace(" ", "_"))


def _norm_education(value: str) -> str:
    v = str(value).strip().lower()
    return {
        "level 1": "level_1",
        "level 2": "level_2",
        "level 3": "level_3",
    }.get(v, v.replace(" ", "_"))


def _norm_disability(value: str) -> str:
    v = str(value).strip().lower()
    return {
        "not disabled": "not_disabled",
        "disabled": "disabled",
    }.get(v, v.replace(" ", "_"))


def _norm_gender(value: str) -> str:
    v = str(value).strip().lower()
    return "female" if v.startswith("f") else "male"


def _table_letter_for(gender: str, disability: str) -> str:
    g = _norm_gender(gender)
    d = _norm_disability(disability)
    if g == "male" and d == "not_disabled":
        return "A"
    if g == "male" and d == "disabled":
        return "B"
    if g == "female" and d == "not_disabled":
        return "C"
    return "D"


def _table_path_for(gender: str, disability: str, retirement_age: float | None = None) -> Path:
    letter = _table_letter_for(gender=gender, disability=disability)
    base = Path("data") / "tables_A-D"
    target_ra = 65 if _norm_gender(gender) == "male" else 60
    if retirement_age is not None:
        # Keep supported Ogden pension-age variants only.
        target_ra = 65 if float(retirement_age) >= 62.5 else 60
    preferred = base / f"reduction_{letter}_{_norm_gender(gender)}_{_norm_disability(disability)}_ra{target_ra}.csv"
    if preferred.exists():
        return preferred
    matches = sorted(base.glob(f"reduction_{letter}_*_ra*.csv"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"No contingency table file found for letter {letter}.")


@lru_cache(maxsize=8)
def _load_rows(path_str: str) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with open(path_str, "r", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            out: dict[str, float] = {}
            for k, v in row.items():
                key = str(k).strip()
                val = str(v).strip() if v is not None else ""
                if val == "":
                    continue
                out[key] = float(val)
            if "age_from" in out and "age_to" in out:
                rows.append(out)
    if not rows:
        raise ValueError(f"No contingency rows found in {path_str}.")
    rows.sort(key=lambda x: (x["age_from"], x["age_to"]))
    return rows


def _column_for(status: str, education: str) -> str:
    s = _norm_status(status)
    e = _norm_education(education)
    prefix = "employed" if s in {"working_employed", "not_started_career"} else "non_employed"
    suffix = {
        "level_1": "level1",
        "level_2": "level2",
        "level_3": "level3",
    }.get(e, "level2")
    return f"{prefix}_{suffix}"


def _pick_age(
    *,
    status: str,
    claimant_age: float | None,
    age_to_start_working: float | None,
) -> float:
    # PI-observed behavior: for Not Started Career, contingency follows start-work age path.
    if _norm_status(status) == "not_started_career" and age_to_start_working is not None:
        return float(age_to_start_working)
    if claimant_age is not None:
        return float(claimant_age)
    return 45.0


def _lookup_value(rows: list[dict[str, float]], age: float, column: str) -> float:
    # Inclusive range lookup with endpoint clamping.
    first = rows[0]
    last = rows[-1]
    if age < first["age_from"]:
        age = first["age_from"]
    if age > last["age_to"]:
        age = last["age_to"]
    for row in rows:
        if row["age_from"] <= age <= row["age_to"]:
            if column in row:
                return float(row[column])
            break
    # fallback nearest available row/column
    for row in reversed(rows):
        if column in row:
            return float(row[column])
    raise ValueError(f"Column {column} not present in contingency table.")


def lookup_contingency(
    *,
    working_status: str,
    education_level: str,
    disability: str,
    age_to_start_working: float | None = None,
    claimant_age: float | None = None,
    gender: str = "male",
    retirement_age: float | None = None,
    fallback: float = 0.87,
) -> float:
    try:
        table_path = _table_path_for(gender=gender, disability=disability, retirement_age=retirement_age)
        rows = _load_rows(str(table_path))
        age = _pick_age(
            status=working_status,
            claimant_age=claimant_age,
            age_to_start_working=age_to_start_working,
        )
        column = _column_for(status=working_status, education=education_level)
        return _lookup_value(rows=rows, age=age, column=column)
    except Exception:
        return float(fallback)
