"""scripts/fetch_bursa_profiles.py  (reference for PHASE 10A; place unchanged)

Pulls PUBLIC company-level profile data (address, switchboard, website) for Bursa-listed companies from
Yahoo Finance via the yfinance library and writes rows in the b2b_companies.csv format.
Company-level data only: no contact names, emails or personal profiles. Never invents a value:
anything Yahoo does not return stays blank, and a row without a valid phone is skipped and reported.

Usage (from the repo root, inside the backend venv):
  pip install yfinance
  python scripts/fetch_bursa_profiles.py                       # writes data/real/b2b_companies.candidates.csv
  python scripts/fetch_bursa_profiles.py --merge               # also appends new rows to data/real/b2b_companies.csv (makes a .bak)
  python scripts/fetch_bursa_profiles.py --selftest            # offline parser tests, no network
Output prints company names and counts only, never phone numbers.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path

COLUMNS = ("company_name,industry,facility_location,facility_size_sqft,contact_name,contact_role,contact_email,"
           "contact_phone_e164,company_phone_e164,website,source_url,estimated_budget,target_use_case,crm_stage,"
           "assigned_agent_email").split(",")

# ADAPT-ME: industry wording must match what the importer already maps for your first six rows
# (check the distinct industry values already in data/real/b2b_companies.csv and reuse them exactly).
LOG = "Logistics / warehousing"
MFG = "Manufacturing"
HEALTH = "Healthcare / hospitals"

# code -> (expected name fragment for a sanity check, our industry label). Fragments are matched case-insensitively
# against the name Yahoo returns; a mismatch means the code is wrong and the row is skipped, not guessed.
CANDIDATES: dict[str, tuple[str, str]] = {
    "7117": ("CENTURY", LOG),
    "4634": ("POS", LOG),
    "5246": ("WESTPORTS", LOG),
    "5032": ("BINTULU", LOG),
    "5908": ("DKSH", LOG),
    "7081": ("PHARMANIAGA", LOG),
    "5225": ("IHH", HEALTH),
    "7113": ("TOP GLOVE", MFG),
    "5168": ("HARTALEGA", MFG),
    "7153": ("KOSSAN", MFG),
    "7106": ("SUPERMAX", MFG),
    "0166": ("INARI", MFG),
    "5005": ("UNISEM", MFG),
    "6963": ("VS INDUSTRY", MFG),  # Yahoo name is "V.S. Industry Berhad"
    "3719": ("PANASONIC", MFG),
    "8869": ("PRESS METAL", MFG),
    "4707": ("NESTL", MFG),  # Yahoo drops the accent: "Nestl (Malaysia) Berhad"
    "3026": ("DUTCH LADY", MFG),
    "3689": ("FRASER", MFG),
    "2836": ("CARLSBERG", MFG),
    "6633": ("LEONG HUP", MFG),
    "2658": ("AJINOMOTO", MFG),
    "0208": ("GREATECH", MFG),
}


def to_e164_my(raw) -> str:
    """'60 3 3385 5888' / '+60 3-3385 5888' / '03-3385 5888' -> '+60333855888'. Blank if it cannot be trusted."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return ""
    if digits.startswith("60"):
        n = digits
    elif digits.startswith("0"):
        n = "60" + digits[1:]
    else:
        return ""  # no country code and no trunk 0: do not guess
    return "+" + n if 10 <= len(n) <= 12 else ""


def squash(s: str) -> str:
    """Letters and digits only, accents removed, lower case: 'V.S. Industry' -> 'vsindustry'."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_name(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", str(s or "").lower())
    s = re.sub(r"\b(berhad|bhd|sdn|holdings?|group|corporation|corp|malaysia|industries|the)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def is_duplicate(name: str, existing_norms: set[str]) -> bool:
    n = norm_name(name)
    return any(n == e or (len(n) >= 6 and (n in e or e in n)) for e in existing_norms if e)


def title_case_place(s: str) -> str:
    return " ".join(w.capitalize() for w in str(s or "").split())


def build_row(code: str, info: dict, industry: str) -> tuple[dict | None, str]:
    """Returns (row, reason). row is None when it must be skipped; reason says why (no values printed)."""
    name = (info.get("longName") or info.get("shortName") or "").strip()
    phone = to_e164_my(info.get("phone"))
    if not name:
        return None, "no company name returned"
    if not phone:
        return None, "no usable phone"
    place = " ".join(p for p in (title_case_place(info.get("city")), title_case_place(info.get("state"))) if p)
    row = {c: "" for c in COLUMNS}
    row.update(
        company_name=name,
        industry=industry,
        facility_location=place,
        company_phone_e164=phone,
        website=(info.get("website") or "").strip(),
        source_url=f"https://finance.yahoo.com/quote/{code}.KL/profile",
    )
    return row, "ok"


def fetch_info(code: str) -> dict:
    import yfinance as yf  # imported lazily so --selftest needs no network or package
    return yf.Ticker(f"{code}.KL").get_info() or {}


def read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def run(out_dir: Path, merge: bool, fetch=fetch_info, sleep_s: float = 1.0) -> int:
    existing_path = out_dir / "b2b_companies.csv"
    existing = read_existing(existing_path)
    existing_norms = {norm_name(r.get("company_name", "")) for r in existing}
    existing_urls = " ".join((r.get("source_url") or "") for r in existing)

    new_rows: list[dict] = []
    skipped: list[str] = []
    for code, (frag, industry) in CANDIDATES.items():
        if f"{code}.KL" in existing_urls:
            skipped.append(f"{code}: already in b2b_companies.csv")
            continue
        try:
            info = fetch(code)
        except Exception as e:  # network, rate limit, bad code
            skipped.append(f"{code}: fetch failed ({type(e).__name__})")
            continue
        name = (info.get("longName") or info.get("shortName") or "")
        if squash(frag) not in squash(name):
            skipped.append(f"{code}: name check failed (got '{name[:40]}')")
            continue
        row, why = build_row(code, info, industry)
        if row is None:
            skipped.append(f"{code}: {why}")
        elif is_duplicate(row["company_name"], existing_norms | {norm_name(r['company_name']) for r in new_rows}):
            skipped.append(f"{code}: duplicate of an existing company")
        else:
            new_rows.append(row)
        time.sleep(sleep_s)

    cand = out_dir / "b2b_companies.candidates.csv"
    with cand.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(new_rows)
    print(f"candidates written: {len(new_rows)} new, {len(existing)} already present, {len(skipped)} skipped")
    for r in new_rows:
        print("  +", r["company_name"], "|", r["industry"])
    for s in skipped:
        print("  -", s)

    if merge and new_rows:
        shutil.copyfile(existing_path, existing_path.with_suffix(".csv.bak"))
        with existing_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writerows(new_rows)
        print(f"merged {len(new_rows)} rows into b2b_companies.csv (backup: b2b_companies.csv.bak). Total now {len(existing) + len(new_rows)}")
    return 0


def selftest() -> int:
    assert to_e164_my("60 3 3385 5888") == "+60333855888"
    assert to_e164_my("+60 3-2267 2267") == "+60322672267"
    assert to_e164_my("03-3385 5888") == "+60333855888"
    assert squash("V.S. Industry Berhad").find(squash("VS INDUSTRY")) >= 0
    assert squash("Nestl (Malaysia) Berhad").find(squash("NESTL")) >= 0 and squash("Nestl\u00e9 (Malaysia) Berhad").find(squash("NESTL")) >= 0
    assert squash("Top Glove").find(squash("HARTALEGA")) < 0
    assert to_e164_my("3385 5888") == ""          # no country code: not guessed
    assert to_e164_my("") == "" and to_e164_my(None) == ""
    assert to_e164_my("12345") == ""
    assert is_duplicate("FM Global Logistics Holdings Berhad", {norm_name("FM Global Logistics Holdings Bhd")})
    assert not is_duplicate("Top Glove Corporation Bhd", {norm_name("KPJ Healthcare Berhad")})
    row, why = build_row("7117", {"longName": "CJ Century Logistics Holdings Berhad", "phone": "60 3 3385 5888",
                                  "city": "KLANG", "state": "Selangor", "website": "https://www.cjcentury.com"}, LOG)
    assert row and row["company_phone_e164"] == "+60333855888" and row["facility_location"] == "Klang Selangor"
    assert build_row("1", {"longName": "X", "phone": ""}, LOG)[0] is None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        with (d / "b2b_companies.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader()
            w.writerow({**{c: "" for c in COLUMNS}, "company_name": "KPJ Healthcare Berhad", "source_url": "https://finance.yahoo.com/quote/5878.KL"})
        fake = {"7117": {"longName": "CJ Century Logistics Holdings Berhad", "phone": "60 3 3385 5888", "city": "Klang", "state": "Selangor"},
                "4634": {"longName": "Pos Malaysia Berhad", "phone": "+60 3 2267 2267", "city": "Kuala Lumpur", "state": ""},
                "7113": {"longName": "WRONG COMPANY", "phone": "60 3 1111 2222"},           # name check must reject
                "5225": {"longName": "IHH Healthcare Berhad", "phone": ""}}               # no phone must skip
        run(d, merge=True, fetch=lambda c: fake.get(c, {}), sleep_s=0)
        got = read_existing(d / "b2b_companies.csv")
        names = [r["company_name"] for r in got]
        assert names == ["KPJ Healthcare Berhad", "CJ Century Logistics Holdings Berhad", "Pos Malaysia Berhad"], names
        assert (d / "b2b_companies.csv.bak").exists()
    print("selftest OK")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/real")
    ap.add_argument("--merge", action="store_true", help="append new rows to b2b_companies.csv (backs up first)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run(Path(a.dir), a.merge))
