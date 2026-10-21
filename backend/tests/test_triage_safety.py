import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from triage_rules import CATEGORY_LABEL, Facts, classify_by_rules, compute_priority


def test_hazard_question_is_high_priority():
    cat, ts = classify_by_rules("Is the unit hazardous to human health?")
    assert cat == "complaint_issue"
    assert compute_priority(cat, ts, Facts())[0] == "high"

def test_other_safety_wording_is_caught():
    for text in ["Any risk of injury to our staff?", "The battery seems to overheat",
                 "Smoke came from the robot", "What safety certifications does it have?",
                 "Adakah ia bahaya untuk pekerja?"]:
        assert classify_by_rules(text)[0] == "complaint_issue", text

def test_safety_plus_urgency_is_urgent():
    cat, ts = classify_by_rules("Smoke from the robot, we need help today")
    assert compute_priority(cat, ts, Facts())[0] == "urgent"

def test_ordinary_technical_question_is_not_escalated():
    cat, ts = classify_by_rules("What is the weight of the robot?")
    assert compute_priority(cat, ts, Facts())[0] == "normal"

def test_label_mentions_safety():
    assert CATEGORY_LABEL["complaint_issue"] == "Problem or safety concern"
