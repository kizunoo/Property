# backend/portal_models.py
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, model_validator, ConfigDict

class RoiScenarioInputs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shifts: int = Field(1, ge=1, le=3)
    headcountPerShift: float = Field(0, ge=0, le=500)
    monthlyLaborCost: float = Field(0, ge=0, le=1_000_000)
    mode: Literal["purchase", "lease"] = "purchase"
    enteredPrice: Optional[float] = Field(None, ge=0, le=100_000_000)

    @model_validator(mode="before")
    @classmethod
    def check_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "headcount_per_shift" in d and "headcountPerShift" not in d:
                d["headcountPerShift"] = d["headcount_per_shift"]
            if "monthly_labor_cost" in d and "monthlyLaborCost" not in d:
                d["monthlyLaborCost"] = d["monthly_labor_cost"]
            if "entered_price" in d and "enteredPrice" not in d:
                d["enteredPrice"] = d["entered_price"]
            return d
        return data

class FacilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility_type: Optional[Literal["warehouse", "manufacturing", "healthcare", "cleaning", "retail_hospitality"]] = None
    floor_area_sqm: Optional[float] = Field(None, ge=0, le=10_000_000)
    environment_notes: Optional[str] = Field(None, max_length=1000)
    primary_use_case: Optional[Literal["transport", "cleaning", "palletizing", "security", "delivery"]] = None
    timeline: Optional[Literal["0-3m", "3-6m", "6-12m", "12m+"]] = None
    budget_band: Optional[Literal["<50k", "50-150k", "150-500k", "500k+"]] = None
