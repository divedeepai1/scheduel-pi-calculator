from dataclasses import dataclass
from typing import Dict, List


@dataclass
class EarningsAwardCalculation:
    def calculate(self, award_amount: float) -> Dict[str, float | List[str]]:
        if award_amount < 0:
            raise ValueError("award_amount must be non-negative.")
        trace = [
            "DEBUG: Earnings Award is treated as one-off non-taxable payment.",
            f"DEBUG: Total Award = {award_amount:.8f}",
        ]
        return {"total_award": float(award_amount), "trace": trace}
