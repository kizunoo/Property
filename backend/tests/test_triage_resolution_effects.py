import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import triage_service as ts
from copilot_tools import Identity
from test_triage_service import iso, make
from triage_rules import AiTriage, Facts, classify_by_rules, compute_priority, merge_label

REPEAT = Facts(inquiries_last_7d=3)


def test_weight_question_is_technical_by_rules():
    assert classify_by_rules("What is the weight of the robot?")[0] == "technical_question"
    assert classify_by_rules("What is the warranty and top speed?")[0] == "technical_question"

def test_tie_prefers_the_ais_more_informative_category():
    cat, tsens = classify_by_rules("how heavy is it")           # rules: general
    pri, category, _ = merge_label(cat, tsens, AiTriage("technical_question", False, "x"), REPEAT)
    assert category == "technical_question" and pri == "high"

def test_tie_keeps_problem_category_from_rules():
    cat, tsens = classify_by_rules("Is it safe? Any injury risk?")   # rules: complaint_issue -> high
    pri, category, _ = merge_label(cat, tsens, AiTriage("pricing_quote", False, "x"), Facts())
    assert category == "complaint_issue"

def test_resolved_inquiries_do_not_inflate_repeat_contact():
    db, _ = make()
    db.t["client_inquiries"] += [{"id": f"r{k}", "client_id": "c1", "status": "answered",
                                  "created_at": iso(days=2), "resolved_at": iso(days=1)} for k in range(3)]
    assert ts.gather_facts(db, "c1", "i1").inquiries_last_7d == 1       # only the unresolved current one
    for r in db.t["client_inquiries"]:
        r["resolved_at"] = None
    assert ts.gather_facts(db, "c1", "i1").inquiries_last_7d == 4

def test_resolved_inquiry_is_not_prior_unanswered():
    db, _ = make()
    db.t["client_inquiries"].append({"id": "old", "client_id": "c1", "status": "open",
                                     "created_at": iso(days=3), "resolved_at": iso(days=1)})
    assert ts.gather_facts(db, "c1", "i1").prior_unanswered is False
    db.t["client_inquiries"][-1]["resolved_at"] = None
    assert ts.gather_facts(db, "c1", "i1").prior_unanswered is True

def test_priority_list_hides_resolved():
    db, _ = make()
    db.t["client_inquiries"] = [
        {"id": "a", "client_id": "c1", "status": "open", "created_at": iso(hours=1), "triage_priority": "high",
         "triage_summary": "s", "triage_reasons": [], "resolved_at": None},
        {"id": "b", "client_id": "c1", "status": "open", "created_at": iso(hours=1), "triage_priority": "urgent",
         "triage_summary": "s", "triage_reasons": [], "resolved_at": iso(minutes=5)},
    ]
    out = ts.list_priority_inquiries(db, Identity("repA", False))
    assert [r["inquiry_id"] for r in out] == ["a"]
