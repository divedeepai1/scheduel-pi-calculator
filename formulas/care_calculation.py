from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple, Any
import calendar


_TIME_INCREMENTS = {
    "Over_Period",
    "Per_Day",
    "Per_Week",
    "Per_Month",
    "Per_Year",
    "Per_Weekday",
    "Per_Weekend",
    "Per_Monday",
    "Per_Tuesday",
    "Per_Wednesday",
    "Per_Thursday",
    "Per_Friday",
    "Per_Saturday",
    "Per_Sunday",
    "Per_Day_Specify",
    "Per_Week_Specify",
    "Per_Month_Specify",
    "Per_Weekday_Specify",
    "Per_Weekend_Specify",
}

_SPECIFY_INCREMENTS = {
    "Over_Period_Specify",
    "Per_Week_Specify",
    "Per_Month_Specify",
    "Per_Year_Specify",
}

_CARE_RATE_TYPES = {
    "Aggregate_Rate",
    "Basic_Rate",
    "Evening_Rate",
    "Weekend_Rate",
    "Saturday_Rate",
    "Sunday_Rate",
    "Aggregate_Day_Rate",
    "Specify_Rate",
}

_DAYS_PER_YEAR = 365.25
_WEEKS_PER_YEAR = 52.0
_MONTHS_PER_YEAR = 12.0
_WEEKDAYS_PER_YEAR = 260.0
_WEEKENDS_PER_YEAR = 104.0
_SINGLE_DAY_PER_YEAR = _DAYS_PER_YEAR / 7.0


@dataclass
class CareCalculation:
    """
    Annualise hours and cost for care periods.

    Supports both age-based and date-based period inputs.
    """

    def calculate(
        self,
        number_of_hours: float,
        time_increment: str,
        care_rate_type: str,
        age_at_start: Optional[float] = None,
        age_at_end: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        rate_values: Optional[Dict[str, float]] = None,
        percentage_less: float = 0.0,
        manual_rate: Optional[float] = None,
        specify_increment: Optional[str] = None,
        number_days_specify: Optional[float] = None,
        number_weeks_specify: Optional[float] = None,
        number_months_specify: Optional[float] = None,
        include_public_holidays: bool = True,
        public_holidays_per_year: float = 8.0,
    ) -> Dict[str, float | str | List[str]]:
        trace: List[str] = []

        period_years, period_source = self._resolve_period_years(
            age_at_start=age_at_start,
            age_at_end=age_at_end,
            start_date=start_date,
            end_date=end_date,
        )
        trace.append(f"DEBUG: Period Source = {period_source}")
        trace.append(f"DEBUG: Period Years = {period_years:.8f}")

        if number_of_hours < 0:
            raise ValueError("number_of_hours must be non-negative.")
        if percentage_less < 0 or percentage_less > 100:
            raise ValueError("percentage_less must be between 0 and 100.")
        if public_holidays_per_year < 0:
            raise ValueError("public_holidays_per_year must be non-negative.")

        if time_increment not in _TIME_INCREMENTS:
            raise ValueError(f"Unsupported time_increment '{time_increment}'.")
        if care_rate_type not in _CARE_RATE_TYPES:
            raise ValueError(f"Unsupported care_rate_type '{care_rate_type}'.")

        effective_rate, rate_source = self._resolve_effective_rate(
            care_rate_type=care_rate_type,
            rate_values=rate_values or {},
            percentage_less=percentage_less,
            manual_rate=manual_rate,
        )
        trace.append(f"DEBUG: Rate Source = {rate_source}")
        trace.append(f"DEBUG: Effective Rate = {effective_rate:.8f}")

        annualised_hours = self._annualised_hours(
            period_years=period_years,
            number_of_hours=number_of_hours,
            time_increment=time_increment,
            specify_increment=specify_increment,
            number_days_specify=number_days_specify,
            number_weeks_specify=number_weeks_specify,
            number_months_specify=number_months_specify,
            include_public_holidays=include_public_holidays,
            public_holidays_per_year=public_holidays_per_year,
            trace=trace,
        )

        annualised_cost = annualised_hours * effective_rate
        trace.append(f"DEBUG: Annualised Cost = annualised_hours * effective_rate = {annualised_hours:.8f} * {effective_rate:.8f} = {annualised_cost:.8f}")

        return {
            "period_years": period_years,
            "annualised_hours": annualised_hours,
            "effective_rate": effective_rate,
            "annualised_cost": annualised_cost,
            "time_increment": time_increment,
            "care_rate_type": care_rate_type,
            "trace": trace,
        }

    def _resolve_period_years(
        self,
        age_at_start: Optional[float],
        age_at_end: Optional[float],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Tuple[float, str]:
        use_age = age_at_start is not None and age_at_end is not None
        use_date = start_date is not None and end_date is not None

        if use_age and use_date:
            raise ValueError("Provide either age inputs or date inputs, not both.")
        if not use_age and not use_date:
            raise ValueError("Provide either age_at_start/age_at_end or start_date/end_date.")

        if use_age:
            period_years = float(age_at_end) - float(age_at_start)
            if period_years <= 0:
                raise ValueError(
                    f"Invalid age period: age_at_end ({age_at_end}) must be greater than age_at_start ({age_at_start})."
                )
            return period_years, f"age ({age_at_start} -> {age_at_end})"

        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
        day_span = (end - start).days
        if day_span <= 0:
            raise ValueError(
                f"Invalid date period: end_date ({end_date}) must be after start_date ({start_date})."
            )
        return float(day_span) / _DAYS_PER_YEAR, f"date ({start_date} -> {end_date})"

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        year = d.year + (d.month - 1 + months) // 12
        month = (d.month - 1 + months) % 12 + 1
        day = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _lookup_counts_for_date_period(
        self,
        start: date,
        end: date,
        include_public_holidays: bool,
        public_holidays_per_year: float,
    ) -> Dict[str, float]:
        day_count = float((end - start).days)
        week_count = day_count / 7.0

        weekday_count = 0.0
        weekend_count = 0.0
        day_name_counts = {
            "Per_Monday": 0.0,
            "Per_Tuesday": 0.0,
            "Per_Wednesday": 0.0,
            "Per_Thursday": 0.0,
            "Per_Friday": 0.0,
            "Per_Saturday": 0.0,
            "Per_Sunday": 0.0,
        }
        current = start
        while current < end:
            wd = current.weekday()  # Monday=0 ... Sunday=6
            if wd < 5:
                weekday_count += 1.0
            else:
                weekend_count += 1.0
            if wd == 0:
                day_name_counts["Per_Monday"] += 1.0
            elif wd == 1:
                day_name_counts["Per_Tuesday"] += 1.0
            elif wd == 2:
                day_name_counts["Per_Wednesday"] += 1.0
            elif wd == 3:
                day_name_counts["Per_Thursday"] += 1.0
            elif wd == 4:
                day_name_counts["Per_Friday"] += 1.0
            elif wd == 5:
                day_name_counts["Per_Saturday"] += 1.0
            elif wd == 6:
                day_name_counts["Per_Sunday"] += 1.0
            current = current.fromordinal(current.toordinal() + 1)

        period_years = day_count / _DAYS_PER_YEAR if day_count > 0 else 0.0
        if not include_public_holidays:
            weekday_count = max(0.0, weekday_count - (public_holidays_per_year * period_years))

        # Exact-ish month count: whole months + fractional remainder in current month.
        whole_months = 0
        cursor = start
        while True:
            nxt = self._add_months(cursor, 1)
            if nxt <= end:
                whole_months += 1
                cursor = nxt
            else:
                break
        rem_days = (end - cursor).days
        denom = calendar.monthrange(cursor.year, cursor.month)[1]
        month_count = float(whole_months) + (float(rem_days) / float(denom) if denom > 0 else 0.0)

        counts = {
            "Per_Day": day_count,
            "Per_Week": week_count,
            "Per_Month": month_count,
            "Per_Year": period_years,
            "Per_Weekday": weekday_count,
            "Per_Weekend": weekend_count,
            "NumberOfWeeksInPeriod": week_count,
            "NumberOfMonthsInPeriod": month_count,
        }
        counts.update(day_name_counts)
        return counts

    def _resolve_effective_rate(
        self,
        care_rate_type: str,
        rate_values: Dict[str, float],
        percentage_less: float,
        manual_rate: Optional[float],
    ) -> Tuple[float, str]:
        if care_rate_type == "Specify_Rate":
            if manual_rate is None:
                raise ValueError("manual_rate is required when care_rate_type is Specify_Rate.")
            base_rate = float(manual_rate)
            source = "manual_rate"
        else:
            if care_rate_type not in rate_values:
                raise ValueError(
                    f"rate_values must include '{care_rate_type}' when care_rate_type is not Specify_Rate."
                )
            base_rate = float(rate_values[care_rate_type])
            source = f"rate_values['{care_rate_type}']"

        if base_rate < 0:
            raise ValueError("Resolved care rate must be non-negative.")

        discount_factor = 1.0 - (float(percentage_less) / 100.0)
        return base_rate * discount_factor, source

    def _annualised_hours(
        self,
        period_years: float,
        number_of_hours: float,
        time_increment: str,
        specify_increment: Optional[str],
        number_days_specify: Optional[float],
        number_weeks_specify: Optional[float],
        number_months_specify: Optional[float],
        include_public_holidays: bool,
        public_holidays_per_year: float,
        trace: List[str],
    ) -> float:
        period_dates = None
        if "date (" in trace[0]:
            # Parse date source from first trace line format: date (YYYY-MM-DD -> YYYY-MM-DD)
            # Keep robust fallback: if parsing fails, use constant-year mode.
            try:
                source = trace[0].split("date (", 1)[1].rstrip(")")
                s, e = [x.strip() for x in source.split("->")]
                period_dates = (date.fromisoformat(s), date.fromisoformat(e))
            except Exception:
                period_dates = None

        if time_increment == "Over_Period":
            annualised = number_of_hours / period_years
            trace.append(
                f"DEBUG: Over_Period Annualised Hours = {number_of_hours} / {period_years:.8f} = {annualised:.8f}"
            )
            return annualised

        if period_dates is not None and time_increment in {
            "Per_Day",
            "Per_Week",
            "Per_Month",
            "Per_Year",
            "Per_Weekday",
            "Per_Weekend",
            "Per_Monday",
            "Per_Tuesday",
            "Per_Wednesday",
            "Per_Thursday",
            "Per_Friday",
            "Per_Saturday",
            "Per_Sunday",
        }:
            counts = self._lookup_counts_for_date_period(
                period_dates[0],
                period_dates[1],
                include_public_holidays=include_public_holidays,
                public_holidays_per_year=public_holidays_per_year,
            )
            annualised = (number_of_hours * counts[time_increment]) / period_years
            trace.append(
                f"DEBUG: {time_increment} (date lookup) Annualised Hours = (number_of_hours * count_in_period) / period_years = ({number_of_hours} * {counts[time_increment]:.8f}) / {period_years:.8f} = {annualised:.8f}"
            )
            return annualised

        weekday_frequency = _WEEKDAYS_PER_YEAR if include_public_holidays else max(
            0.0, _WEEKDAYS_PER_YEAR - float(public_holidays_per_year)
        )
        counts_per_year = {
            "Per_Day": _DAYS_PER_YEAR,
            "Per_Week": _WEEKS_PER_YEAR,
            "Per_Month": _MONTHS_PER_YEAR,
            "Per_Year": 1.0,
            "Per_Weekday": weekday_frequency,
            "Per_Weekend": _WEEKENDS_PER_YEAR,
            "Per_Monday": _SINGLE_DAY_PER_YEAR,
            "Per_Tuesday": _SINGLE_DAY_PER_YEAR,
            "Per_Wednesday": _SINGLE_DAY_PER_YEAR,
            "Per_Thursday": _SINGLE_DAY_PER_YEAR,
            "Per_Friday": _SINGLE_DAY_PER_YEAR,
            "Per_Saturday": _SINGLE_DAY_PER_YEAR,
            "Per_Sunday": _SINGLE_DAY_PER_YEAR,
        }
        if time_increment in counts_per_year:
            annualised = number_of_hours * counts_per_year[time_increment]
            if time_increment == "Per_Weekday":
                trace.append(
                    f"DEBUG: Per_Weekday include_public_holidays={include_public_holidays}, public_holidays_per_year={public_holidays_per_year}"
                )
            trace.append(
                f"DEBUG: {time_increment} Annualised Hours = number_of_hours * frequency_per_year = {number_of_hours} * {counts_per_year[time_increment]:.8f} = {annualised:.8f}"
            )
            return annualised

        if time_increment == "Per_Day_Specify":
            date_counts = None
            if period_dates is not None:
                date_counts = self._lookup_counts_for_date_period(
                    period_dates[0],
                    period_dates[1],
                    include_public_holidays=include_public_holidays,
                    public_holidays_per_year=public_holidays_per_year,
                )
            return self._annualised_specify(
                specify_kind="days",
                base_count=number_days_specify,
                number_of_hours=number_of_hours,
                period_years=period_years,
                specify_increment=specify_increment,
                trace=trace,
                date_counts=date_counts,
            )

        if time_increment in {"Per_Week_Specify", "Per_Weekday_Specify", "Per_Weekend_Specify"}:
            date_counts = None
            if period_dates is not None:
                date_counts = self._lookup_counts_for_date_period(
                    period_dates[0],
                    period_dates[1],
                    include_public_holidays=include_public_holidays,
                    public_holidays_per_year=public_holidays_per_year,
                )
            return self._annualised_specify(
                specify_kind="weeks",
                base_count=number_weeks_specify,
                number_of_hours=number_of_hours,
                period_years=period_years,
                specify_increment=specify_increment,
                trace=trace,
                weekday_multiplier=(5.0 if time_increment == "Per_Weekday_Specify" else 1.0),
                date_counts=date_counts,
            )

        if time_increment == "Per_Month_Specify":
            date_counts = None
            if period_dates is not None:
                date_counts = self._lookup_counts_for_date_period(
                    period_dates[0],
                    period_dates[1],
                    include_public_holidays=include_public_holidays,
                    public_holidays_per_year=public_holidays_per_year,
                )
            return self._annualised_specify(
                specify_kind="months",
                base_count=number_months_specify,
                number_of_hours=number_of_hours,
                period_years=period_years,
                specify_increment=specify_increment,
                trace=trace,
                date_counts=date_counts,
            )

        raise ValueError(f"No annualisation rule implemented for time_increment '{time_increment}'.")

    def _annualised_specify(
        self,
        specify_kind: str,
        base_count: Optional[float],
        number_of_hours: float,
        period_years: float,
        specify_increment: Optional[str],
        trace: List[str],
        weekday_multiplier: float = 1.0,
        date_counts: Optional[Dict[str, float]] = None,
    ) -> float:
        if base_count is None:
            raise ValueError(f"Missing specify count for {specify_kind}.")
        if base_count < 0:
            raise ValueError(f"{specify_kind} specify count must be non-negative.")
        if specify_increment not in _SPECIFY_INCREMENTS:
            raise ValueError(
                f"Unsupported specify_increment '{specify_increment}'. Expected one of {_SPECIFY_INCREMENTS}."
            )

        if specify_kind == "days":
            if specify_increment == "Over_Period_Specify":
                total_hours = base_count * number_of_hours
            elif specify_increment == "Per_Week_Specify":
                weeks_in_period = date_counts["NumberOfWeeksInPeriod"] if date_counts else (period_years * _WEEKS_PER_YEAR)
                total_hours = weeks_in_period * base_count * number_of_hours
            elif specify_increment == "Per_Month_Specify":
                months_in_period = date_counts["NumberOfMonthsInPeriod"] if date_counts else (period_years * _MONTHS_PER_YEAR)
                total_hours = months_in_period * base_count * number_of_hours
            else:  # Per_Year_Specify
                total_hours = period_years * base_count * number_of_hours
            annualised = total_hours / period_years
            trace.append(
                f"DEBUG: Per_Day_Specify Annualised Hours = (total_hours / period_years) = ({total_hours:.8f} / {period_years:.8f}) = {annualised:.8f}"
            )
            return annualised

        if specify_kind == "weeks":
            if specify_increment == "Per_Week_Specify":
                raise ValueError(
                    "Invalid combination: Per_Week_Specify/Per_Weekday_Specify/Per_Weekend_Specify with Per_Week_Specify is not supported."
                )
            if specify_increment == "Over_Period_Specify":
                total_hours = base_count * number_of_hours * weekday_multiplier
            elif specify_increment == "Per_Month_Specify":
                months_in_period = date_counts["NumberOfMonthsInPeriod"] if date_counts else (period_years * _MONTHS_PER_YEAR)
                total_hours = months_in_period * base_count * number_of_hours * weekday_multiplier
            else:  # Per_Year_Specify
                total_hours = period_years * base_count * number_of_hours * weekday_multiplier
            annualised = total_hours / period_years
            trace.append(
                f"DEBUG: {specify_kind.capitalize()}_Specify Annualised Hours = (total_hours / period_years) = ({total_hours:.8f} / {period_years:.8f}) = {annualised:.8f}"
            )
            return annualised

        if specify_kind == "months":
            if specify_increment in {"Per_Week_Specify", "Per_Month_Specify"}:
                raise ValueError(
                    "Invalid combination: Per_Month_Specify cannot be paired with Per_Week_Specify or Per_Month_Specify."
                )
            if specify_increment == "Over_Period_Specify":
                total_hours = base_count * number_of_hours
            else:  # Per_Year_Specify
                total_hours = period_years * base_count * number_of_hours
            annualised = total_hours / period_years
            trace.append(
                f"DEBUG: Per_Month_Specify Annualised Hours = (total_hours / period_years) = ({total_hours:.8f} / {period_years:.8f}) = {annualised:.8f}"
            )
            return annualised

        raise ValueError(f"Unknown specify_kind '{specify_kind}'.")


@dataclass
class CareSplitCalculation:
    """
    Compute total annualised care cost across ordered non-overlapping split periods.
    """

    care_calculation: CareCalculation

    def calculate_split(
        self,
        periods: List[Dict[str, Any]],
        require_contiguous: bool = True,
        tolerance: float = 1e-9,
    ) -> Dict[str, Any]:
        if not periods:
            raise ValueError("periods cannot be empty.")

        normalised: List[Tuple[float, float, Dict[str, Any]]] = []
        results: List[Dict[str, Any]] = []
        total = 0.0

        for index, period in enumerate(periods):
            start = period.get("age_at_start")
            end = period.get("age_at_end")
            if start is None or end is None:
                raise ValueError("Each split period requires age_at_start and age_at_end for ordering checks.")
            start_f = float(start)
            end_f = float(end)
            if end_f <= start_f:
                raise ValueError(f"Split period {index + 1} has invalid range {start_f} -> {end_f}.")
            normalised.append((start_f, end_f, period))

        normalised.sort(key=lambda x: x[0])
        for i in range(len(normalised) - 1):
            curr_end = normalised[i][1]
            next_start = normalised[i + 1][0]
            if next_start < curr_end - tolerance:
                raise ValueError(
                    f"Split periods overlap: period ending at {curr_end} overlaps next start {next_start}."
                )
            if require_contiguous and abs(next_start - curr_end) > tolerance:
                raise ValueError(
                    f"Split periods are not contiguous: expected next start {curr_end}, got {next_start}."
                )

        for start, end, period in normalised:
            calc_result = self.care_calculation.calculate(
                age_at_start=start,
                age_at_end=end,
                number_of_hours=float(period["number_of_hours"]),
                time_increment=str(period["time_increment"]),
                care_rate_type=str(period["care_rate_type"]),
                rate_values=period.get("rate_values"),
                percentage_less=float(period.get("percentage_less", 0.0)),
                manual_rate=period.get("manual_rate"),
                specify_increment=period.get("specify_increment"),
                number_days_specify=period.get("number_days_specify"),
                number_weeks_specify=period.get("number_weeks_specify"),
                number_months_specify=period.get("number_months_specify"),
                include_public_holidays=bool(period.get("include_public_holidays", True)),
                public_holidays_per_year=float(period.get("public_holidays_per_year", 8.0)),
            )
            total += float(calc_result["annualised_cost"])
            results.append(calc_result)

        return {
            "period_results": results,
            "total_split_annualised_cost": total,
        }
