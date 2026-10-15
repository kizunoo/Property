# backend/roi.py
from typing import Literal, Optional, TypedDict

def clamp(n: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, n))

class RoiInputs(TypedDict):
    shifts: int
    headcountPerShift: float
    monthlyLaborCost: float

class RoiRobot(TypedDict, total=False):
    purchasePrice: Optional[float]
    leaseMonthly: Optional[float]

class RoiResult(TypedDict):
    monthlySavings: float
    netMonthly: float
    paybackMonths: Optional[float]
    threeYearRoiPct: Optional[float]

def compute_roi(i: dict, r: dict, mode: Literal["purchase", "lease"]) -> dict:
    shifts = clamp(round(i.get("shifts", 1)), 1, 3)
    heads = clamp(i.get("headcountPerShift", 0), 0, 500)
    labor = clamp(i.get("monthlyLaborCost", 0), 0, 1_000_000)
    monthly_savings = shifts * heads * labor

    if mode == "lease":
        lease = r.get("leaseMonthly") or 0
        net_monthly = monthly_savings - lease
        return {
            "monthlySavings": monthly_savings,
            "netMonthly": net_monthly,
            "paybackMonths": 0 if net_monthly > 0 else None,
            "threeYearRoiPct": ((net_monthly * 36) / (lease * 36) * 100) if lease > 0 else None,
        }
    
    price = r.get("purchasePrice") or 0
    net_monthly = monthly_savings
    return {
        "monthlySavings": monthly_savings,
        "netMonthly": net_monthly,
        "paybackMonths": (price / net_monthly) if (price > 0 and net_monthly > 0) else None,
        "threeYearRoiPct": (((net_monthly * 36 - price) / price) * 100) if price > 0 else None,
    }
