"""backend/tests/test_quote_logic.py

Unit tests for backend/quote_logic.py pure business logic.
Ports all selftest cases from quote_reference.py. Each test case is its own function.
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quote_logic import (
    DISCOUNTS,
    LEAD_TIMES,
    QUOTE_VALIDITY_DAYS,
    REPLY_DELAY_MAX_S,
    REPLY_DELAY_MIN_S,
    SIM_FOOTER,
    SIM_LABEL,
    build_draft,
    due_requests,
    make_quote_record,
    market_price_ok,
    mock_reply,
    parse_reply,
    quote_in_bounds,
    reply_delay_seconds,
)


def test_delay_in_range_and_deterministic():
    for i in range(200):
        d = reply_delay_seconds(f"req-{i}")
        assert REPLY_DELAY_MIN_S <= d <= REPLY_DELAY_MAX_S, f"Delay {d} out of range"
    assert reply_delay_seconds("a") == reply_delay_seconds("a"), "Delay must be deterministic"


def test_market_bounds():
    assert market_price_ok(100000, 100000), "market ok at indicative"
    assert not market_price_ok(39999, 100000), "market below min"
    assert not market_price_ok(250001, 100000), "market above max"
    assert not market_price_ok(float("nan"), 100000), "market nan"
    assert not market_price_ok(100000, None), "indicative none"
    assert not market_price_ok(True, 100000), "bool is not a price"


def test_draft_never_leaks_market_price_and_carries_label():
    facts = {"Facility type": "Warehouse", "Floor area": "20,000 sq ft", "Contact": ""}
    subj, body = build_draft(
        "quote", {"name": "Ancom Logistics"}, {"name": "PUDU T300", "manufacturer": "Pudu"}, facts
    )
    assert SIM_LABEL in subj, "Subject must contain SIM_LABEL"
    assert "SIMULATED" in body, "Body must contain SIMULATED"
    assert "Contact" not in body, "Empty fact must be skipped"
    assert "RM" not in body, "No price in a first quote request"


def test_requote_draft_mentions_previous_price():
    _, body = build_draft(
        "requote", {"name": "X"}, {"name": "R"}, {}, previous_price=151000
    )
    assert "151,000" in body, "Requote must mention previous price"


def test_reply_round_trip():
    reply = mock_reply("req-1", "quote", "PUDU T300", 106100.0)
    parsed = parse_reply(reply)
    assert parsed is not None, "Reply must parse"
    assert parsed["price_myr"] <= 106100 and parsed["price_myr"] >= 106100 * 0.94, "Price must be near market"
    assert parsed["price_myr"] % 100 == 0, "Price must be rounded to RM 100"
    assert parsed["validity_days"] == QUOTE_VALIDITY_DAYS, "Validity must match QUOTE_VALIDITY_DAYS"
    assert parsed["lead_time_weeks"] in LEAD_TIMES, "Lead time must be in LEAD_TIMES"
    assert mock_reply("req-1", "quote", "PUDU T300", 106100.0) == reply, "Reply must be deterministic"
    assert SIM_LABEL in reply and "simulated" in reply.lower(), "Reply must carry simulation label"


def test_requote_capped_at_previous():
    rq = parse_reply(mock_reply("req-2", "requote", "R", 98000.0, previous_price=95000))
    assert rq is not None, "Requote reply must parse"
    assert rq["price_myr"] <= 95000, "Requote price must be capped at previous quote"


def test_parser_strictness_no_price():
    assert parse_reply("no price here") is None, "No price must be rejected"


def test_parser_strictness_conflicting_prices():
    two = "Quoted price (MYR): 100,000\nQuoted price (MYR): 90,000"
    assert parse_reply(two) is None, "Conflicting prices must be rejected"


def test_parser_strictness_repeated_same_price():
    same = "Quoted price (MYR): 100,000\nQuoted price (MYR): 100,000"
    assert parse_reply(same) is not None, "Repeated identical price must be accepted"


def test_parser_strictness_zero_and_invalid():
    assert parse_reply("Quoted price (MYR): 0") is None, "Zero price must be rejected"
    assert parse_reply(None) is None, "Non-string must return None"


def test_parser_strictness_validity_clamped():
    clamp = parse_reply("Quoted price (MYR): 5,000\nValidity (days): 999")
    assert clamp is not None and clamp["validity_days"] == 60, "Validity must clamp to 60"


def test_quote_in_bounds():
    assert quote_in_bounds(100000, 100000), "Quote in bounds"
    assert not quote_in_bounds(10, 100000), "Quote too low must fail"
    assert not quote_in_bounds(100000, None), "None indicative must fail"


def test_make_quote_record_and_expiry():
    now = datetime(2026, 11, 3, 9, 0, 0)
    parsed = {"price_myr": 100000, "lead_time_weeks": 8, "terms": "standard", "validity_days": QUOTE_VALIDITY_DAYS}
    rec = make_quote_record(parsed, now)
    assert rec["expires_at"] == now + timedelta(days=QUOTE_VALIDITY_DAYS), "Expires at must match validity"
    assert rec["is_simulated"] is True, "Must be simulated"


def test_due_requests():
    now = datetime(2026, 11, 3, 9, 0, 0)
    reqs = [
        {"id": "a", "status": "sent", "reply_due_at": now - timedelta(seconds=1)},
        {"id": "b", "status": "sent", "reply_due_at": now + timedelta(seconds=1)},
        {"id": "c", "status": "quoted", "reply_due_at": now - timedelta(days=1)},
        {"id": "d", "status": "draft", "reply_due_at": None},
    ]
    assert [r["id"] for r in due_requests(reqs, now)] == ["a"], "Only sent and due requests must be returned"


def test_ast_imports_allowed_only():
    """Fails if backend/quote_logic.py imports anything outside hashlib, math, re, datetime, typing, __future__."""
    path = Path(__file__).resolve().parents[1] / "quote_logic.py"
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(path))

    allowed_modules = {"hashlib", "math", "re", "datetime", "typing", "__future__"}
    disallowed_found = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod not in allowed_modules:
                    disallowed_found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod not in allowed_modules:
                    disallowed_found.append(node.module)

    assert not disallowed_found, f"Disallowed imports found in quote_logic.py: {disallowed_found}"
