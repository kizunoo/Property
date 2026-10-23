"""Read-only validator for data/real/robots_catalog.csv.
Mirrors the importer's rules so problems show up BEFORE Phase 9.
Prints row labels (sku_code) and column names only, never other cell contents.
Usage: python scripts/validate_robots_catalog.py [path]   (default data/real/robots_catalog.csv)
Exit code 1 if any BLOCKER is found.
"""
import csv
import sys
from pathlib import Path

EXPECTED = ("sku_code,name,manufacturer,category,price,lease_monthly,payload_kg,"
            "battery_hours,weight_kg,dimensions,speed_mps,warranty_months,"
            "key_specs,target_industries,image_url").split(",")
REQUIRED = ("sku_code", "name", "manufacturer", "category")
NUMERIC = ("price", "lease_monthly", "payload_kg", "battery_hours",
           "weight_kg", "speed_mps", "warranty_months")
# Columns whose absence only weakens AI answers ("Not in the catalog"), not blockers.
WANTED = ("weight_kg", "dimensions", "price")


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"BLOCKER: {p} not found")
        return 1
    with p.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    blockers, warnings = [], []
    if list(header) != EXPECTED:
        missing = [c for c in EXPECTED if c not in header]
        extra = [c for c in header if c not in EXPECTED]
        blockers.append(f"header mismatch: missing={missing} extra={extra}")
    if not rows:
        blockers.append("no data rows")

    seen = set()
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        sku = (r.get("sku_code") or "").strip()
        label = sku or f"line {i}"
        if sku.upper().startswith("EXAMPLE"):
            blockers.append(f"{label}: template row (sku starts with EXAMPLE)")
        if sku in seen:
            blockers.append(f"{label}: duplicate sku_code")
        seen.add(sku)
        for col in REQUIRED:
            if not (r.get(col) or "").strip():
                blockers.append(f"{label}: missing required '{col}'")
        for col in NUMERIC:
            v = (r.get(col) or "").strip()
            if not v:
                continue
            try:
                if float(v) < 0:
                    blockers.append(f"{label}: '{col}' is negative")
            except ValueError:
                blockers.append(f"{label}: '{col}' is not a number")
        for col in WANTED:
            if not (r.get(col) or "").strip():
                warnings.append(f"{label}: '{col}' empty (AI replies will say 'not in the catalog')")

    print(f"rows: {len(rows)}")
    for w in warnings:
        print("WARN   ", w)
    for b in blockers:
        print("BLOCKER", b)
    print("RESULT:", "FAIL" if blockers else "OK")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/real/robots_catalog.csv"))
