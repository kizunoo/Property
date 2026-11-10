"""quote_logic.py

Pure business logic for simulated supplier quotes (rep console only).
Standard library only (hashlib, math, re, datetime, typing, __future__).
No network, no external I/O, no file access, no clock reads: time is always passed in.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta
from typing import Optional

SIM_LABEL = "SIMULATED SUPPLIER"
SIM_FOOTER = "SIMULATED: demo system. Not sent to any manufacturer. Not a real offer."

QUOTE_VALIDITY_DAYS = 14
REPLY_DELAY_MIN_S = 0
REPLY_DELAY_MAX_S = 0
MIN_MULT = 0.4  # same bounds as lib/market-sim.ts MIN_MULT / MAX_MULT
MAX_MULT = 2.5
DISCOUNTS = (0.0, 0.02, 0.03, 0.05)
REQUOTE_EXTRA_DISCOUNT = 0.02
LEAD_TIMES = (6, 8, 10, 12)
TERMS = (
    "Delivery and installation quoted separately. 12-month warranty.",
    "Lease option available on request. 12-month warranty.",
    "Includes on-site commissioning. Training for two staff included.",
    "Payment 50% on order, 50% on delivery. 12-month warranty.",
)


def _h(*parts: object) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _pick(options: tuple, *seed: object):
    return options[_h(*seed) % len(options)]


def _valid_price(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def reply_delay_seconds(request_id: str) -> int:
    span = REPLY_DELAY_MAX_S - REPLY_DELAY_MIN_S + 1
    return REPLY_DELAY_MIN_S + _h("delay", request_id) % span


def market_price_ok(market: object, indicative: object) -> bool:
    """The browser tells us the market price it showed. Accept it only if it is
    inside the same bounds the simulator uses around the catalog indicative price."""
    if not (_valid_price(market) and _valid_price(indicative)):
        return False
    return indicative * MIN_MULT <= market <= indicative * MAX_MULT


def _rm(n: int) -> str:
    return f"{int(n):,}"


def build_draft(
    kind: str,
    company: dict,
    robot: dict,
    facts: dict,
    previous_price: Optional[int] = None,
) -> tuple[str, str]:
    """Returns (subject, body). `facts` is a flat dict of label -> value taken from the
    existing facility profile builder (no emails, no phones). The market price is
    NEVER put in the draft."""
    robot_name = robot.get("name") or "the listed robot"
    maker = robot.get("manufacturer") or "the manufacturer"
    company_name = company.get("name") or "a prospective customer"
    if kind == "requote":
        subject = f"[{SIM_LABEL}] Requote request: {robot_name}"
        opening = (
            f"Hello {maker} sales team,\n\n"
            f"We are asking you to review your earlier quote for {robot_name}"
            + (f" (RM {_rm(previous_price)})" if _valid_price(previous_price) else "")
            + f" for {company_name}. Market conditions have moved since it was issued."
        )
    else:
        subject = f"[{SIM_LABEL}] Quote request: {robot_name}"
        opening = (
            f"Hello {maker} sales team,\n\n"
            f"We would like a quote for 1 unit of {robot_name} for {company_name}."
        )
    fact_lines = "\n".join(f"- {k}: {v}" for k, v in facts.items() if v not in (None, ""))
    body = (
        f"{opening}\n\n"
        + (f"Facility details:\n{fact_lines}\n\n" if fact_lines else "")
        + "Please reply with: unit price (MYR), lead time (weeks), how long the quote is "
        "valid (days), and any terms.\n\n"
        f"{SIM_FOOTER}"
    )
    return subject, body


def mock_reply(
    request_id: str,
    kind: str,
    robot_name: str,
    market_price: float,
    previous_price: Optional[int] = None,
) -> str:
    """Scripted supplier reply. Price = live market price less a small seeded deal
    factor, rounded to the nearest RM 100. Deterministic hashing only."""
    disc = _pick(DISCOUNTS, "disc", request_id)
    if kind == "requote":
        disc += REQUOTE_EXTRA_DISCOUNT
    price = int(market_price * (1 - disc) / 100 + 0.5) * 100
    if kind == "requote" and _valid_price(previous_price):
        price = min(price, int(previous_price))
    lead = _pick(LEAD_TIMES, "lead", request_id)
    terms = _pick(TERMS, "terms", request_id)
    return (
        f"[{SIM_LABEL}] Re: Quote request - {robot_name}\n"
        "Hello, thanks for your enquiry.\n"
        f"Quoted price (MYR): {_rm(price)}\n"
        f"Lead time (weeks): {lead}\n"
        f"Validity (days): {QUOTE_VALIDITY_DAYS}\n"
        f"Terms: {terms}\n"
        "This is a simulated reply from the demo system. Not a real offer."
    )


_PRICE_RE = re.compile(r"Quoted price \(MYR\):\s*([0-9][0-9,]*)")
_LEAD_RE = re.compile(r"Lead time \(weeks\):\s*(\d{1,2})")
_VALID_RE = re.compile(r"Validity \(days\):\s*(\d{1,3})")
_TERMS_RE = re.compile(r"Terms:\s*(.+)")


def parse_reply(text: str) -> Optional[dict]:
    """A price is accepted only if it literally appears in the reply text, exactly
    once (or repeated with the same value). Anything else returns None."""
    if not isinstance(text, str):
        return None
    prices = {int(m.replace(",", "")) for m in _PRICE_RE.findall(text)}
    if len(prices) != 1:
        return None
    price = prices.pop()
    if price <= 0:
        return None
    lead_m = _LEAD_RE.search(text)
    valid_m = _VALID_RE.search(text)
    terms_m = _TERMS_RE.search(text)
    validity = int(valid_m.group(1)) if valid_m else QUOTE_VALIDITY_DAYS
    validity = max(1, min(60, validity))
    return {
        "price_myr": price,
        "lead_time_weeks": int(lead_m.group(1)) if lead_m else None,
        "validity_days": validity,
        "terms": terms_m.group(1).strip() if terms_m else None,
    }


def quote_in_bounds(price: int, indicative: object) -> bool:
    return _valid_price(price) and _valid_price(indicative) and (
        indicative * MIN_MULT <= price <= indicative * MAX_MULT
    )


def make_quote_record(parsed: dict, issued_at: datetime) -> dict:
    return {
        "price_myr": parsed["price_myr"],
        "lead_time_weeks": parsed["lead_time_weeks"],
        "terms": parsed["terms"],
        "issued_at": issued_at,
        "expires_at": issued_at + timedelta(days=parsed["validity_days"]),
        "is_simulated": True,
    }


def due_requests(items: list, now: datetime) -> list:
    """Requests whose simulated reply is ready. Pure: the caller does the writes."""
    out = []
    for r in items:
        due = r.get("reply_due_at")
        if r.get("status") == "sent" and due is not None and due <= now:
            out.append(r)
    return out

