import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from triage_rules import (Facts, classify_by_rules, compute_priority, escalate_only,
                          parse_ai_output, sanitize_text)

NONE = Facts()


def test_classification_keywords():
    assert classify_by_rules("How much is the cleaning robot?")[0] == "pricing_quote"
    assert classify_by_rules("Can we book a demo next week?")[0] == "demo_request"
    assert classify_by_rules("The robot is not working since Monday")[0] == "complaint_issue"
    assert classify_by_rules("What is the payload and battery life?")[0] == "technical_question"
    assert classify_by_rules("Thanks for the call yesterday")[0] == "general"
    assert classify_by_rules("??")[0] == "unclear"

def test_malay_keywords():
    assert classify_by_rules("Boleh bagi sebut harga?")[0] == "pricing_quote"
    assert classify_by_rules("Robot rosak, perlu segera")[0:2] == ("complaint_issue", True)

def test_time_sensitivity():
    assert classify_by_rules("We need a quote ASAP")[1] is True
    assert classify_by_rules("We need a quote sometime")[1] is False

def test_base_priorities():
    assert compute_priority("pricing_quote", False, NONE)[0] == "high"
    assert compute_priority("technical_question", False, NONE)[0] == "normal"
    assert compute_priority("unclear", False, NONE)[0] == "low"

def test_bumps_and_cap():
    p, reasons = compute_priority("pricing_quote", True, Facts(has_open_quote=True))
    assert p == "urgent" and "Has an open quote" in reasons
    p, _ = compute_priority("complaint_issue", True,
                            Facts(has_open_quote=True, prior_unanswered=True, inquiries_last_7d=5))
    assert p == "urgent"                      # capped at urgent
    p, _ = compute_priority("general", False, Facts(prior_unanswered=True))
    assert p == "high"

def test_open_quote_only_matters_for_quote_or_complaint():
    assert compute_priority("technical_question", False, Facts(has_open_quote=True))[0] == "normal"

def test_ai_can_only_escalate():
    assert escalate_only("high", "low") == "high"
    assert escalate_only("normal", "urgent") == "urgent"
    assert escalate_only("urgent", "normal") == "urgent"

def test_parse_ai_output_valid_and_fenced():
    raw = 'Sure!\n```json\n{"category":"demo_request","time_sensitive":true,"summary":"Wants a demo Friday"}\n```'
    ai = parse_ai_output(raw)
    assert ai and ai.category == "demo_request" and ai.time_sensitive is True

def test_parse_ai_output_rejects_bad_input():
    assert parse_ai_output(None) is None
    assert parse_ai_output("no json here") is None
    assert parse_ai_output('{"category":"hack","time_sensitive":true,"summary":"x"}') is None
    assert parse_ai_output('{"category":"general","time_sensitive":"yes","summary":"x"}') is None
    assert parse_ai_output('{"category":"general","time_sensitive":false,"summary":""}') is None

def test_sanitize_strips_control_chars_and_clips():
    assert sanitize_text("a\x00b\n\nc   d") == "a b c d"
    assert len(sanitize_text("x" * 999, 50)) == 50
