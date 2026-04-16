from dataclasses import dataclass
from typing import List, Tuple
import math


@dataclass
class CareWholeLifeCalculation:
    """
    Whole-life multiplier interpolation from Ogden Table 1/2 at 0.5%.

    Each table row is expected as: [age, multiplier].
    """

    male_table: List[Tuple[float, float]]
    female_table: List[Tuple[float, float]]

    @staticmethod
    def _value_at_age(table: List[Tuple[float, float]], age_int: int) -> float:
        for row_age, row_value in table:
            if int(row_age) == int(age_int):
                return float(row_value)
        if not table:
            raise ValueError("Whole-life table is empty.")
        first_age, first_value = table[0]
        last_age, last_value = table[-1]
        if age_int <= int(first_age):
            return float(first_value)
        if age_int >= int(last_age):
            return float(last_value)
        raise ValueError(f"Age {age_int} not found in table and cannot be interpolated.")

    def multiplier(self, claimant_age: float, gender: str) -> float:
        if claimant_age < 0:
            raise ValueError("claimant_age must be non-negative.")
        g = (gender or "").strip().lower()
        if g not in {"male", "female"}:
            raise ValueError("gender must be either 'male' or 'female'.")

        table = self.male_table if g == "male" else self.female_table
        age_lower = int(math.floor(claimant_age))
        age_upper = int(math.ceil(claimant_age))

        m_lower = self._value_at_age(table, age_lower)
        if age_lower == age_upper:
            return m_lower
        m_upper = self._value_at_age(table, age_upper)
        return ((age_upper - claimant_age) * m_lower) + ((claimant_age - age_lower) * m_upper)
