"""
Pure triage logic (no DB, no AI, no network). Fully unit-tested.

Design: rules label every inquiry instantly. The AI may only ESCALATE the label, never lower it
(fail-safe: a missed urgent inquiry costs more than a false alarm, and a customer message that
says "mark me low priority" cannot downgrade anything).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

CATEGORIES = ("pricing_quote", "demo_request", "technical_question",
              "complaint_issue", "general", "unclear")
PRIORITIES = ("low", "normal", "high", "urgent")
RANK = {p: i for i, p in enumerate(PRIORITIES)}
CATEGORY_LABEL = {
    "pricing_quote": "Pricing / quote question",
    "demo_request": "Demo request",
    "technical_question": "Technical question",
    "complaint_issue": "Problem or safety concern",
    "general": "General message",
    "unclear": "Unclear message",
}
BASE_PRIORITY = {"complaint_issue": "high", "demo_request": "high", "pricing_quote": "high",
                 "technical_question": "normal", "general": "normal", "unclear": "low"}
MAX_BUMP = 2
SUMMARY_MAX = 200

_RULES = [
    ("complaint_issue", re.compile(
        r"\b(broken|not working|doesn'?t work|won'?t (start|work|charge|move)|fault\w*|defect\w*|"
        r"complain\w*|problem\w*|issue\w*|delay\w*|refund\w*|cancel\w*|disappoint\w*|rosak|masalah)\b", re.I)),
    ("demo_request", re.compile(
        r"\b(demo\w*|trial\w*|poc|proof of concept|site visit|visit us|test run|tunjuk)\b", re.I)),
    ("pricing_quote", re.compile(
        r"\b(price\w*|pricing|quote\w*|quotation|cost\w*|lease|leasing|how much|budget|rm ?\d+|harga|sebut harga)\b", re.I)),
    ("technical_question", re.compile(
        r"\b(spec\w*|payload|weigh\w*|dimension\w*|warranty|speed|battery|aisle\w*|integrat\w*|wi-?fi|5g|api|compatib\w*|elevator|lift|"
        r"navigation|lidar|sensor\w*|capacity)\b", re.I)),
]
_URGENT = re.compile(
    r"\b(urgent\w*|asap|immediately|today|tonight|tomorrow|deadline|this week|"
    r"by (mon|tue|wed|thu|fri|sat|sun)\w*|segera)\b", re.I)


_SAFETY = re.compile(
    r"\b(hazard\w*|danger\w*|unsafe|safety|injur\w*|accident\w*|harm\w*|fire|smok\w*|burn\w*|"
    r"spark\w*|overheat\w*|explo\w*|electric shock|toxic|bahaya)\b", re.I)


@dataclass(frozen=True)
class Facts:
    has_open_quote: bool = False
    has_pending_demo: bool = False
    prior_unanswered: bool = False
    inquiries_last_7d: int = 0


@dataclass(frozen=True)
class AiTriage:
    category: str
    time_sensitive: bool
    summary: str


def classify_by_rules(text: str) -> tuple[str, bool]:
    t = (text or "").strip()
    if len(re.sub(r"[\W_]+", "", t)) < 5:
        return "unclear", False
    if _SAFETY.search(t):  # safety concerns always reach a human quickly
        return "complaint_issue", bool(_URGENT.search(t))
    category = "general"
    for name, pattern in _RULES:
        if pattern.search(t):
            category = name
            break
    return category, bool(_URGENT.search(t))


def compute_priority(category: str, time_sensitive: bool, facts: Facts) -> tuple[str, list[str]]:
    base = BASE_PRIORITY.get(category, "normal")
    reasons = [CATEGORY_LABEL.get(category, CATEGORY_LABEL["general"])]
    if category == "unclear":
        return "low", reasons  # nothing to act on: repeat contact, quotes etc. never raise it
    bump = 0
    if time_sensitive:
        bump += 1
        reasons.append("Mentions a deadline or urgency")
    if facts.has_open_quote and category in ("pricing_quote", "complaint_issue"):
        bump += 1
        reasons.append("Has an open quote")
    if facts.prior_unanswered:
        bump += 1
        reasons.append("Earlier inquiry still unanswered")
    if facts.inquiries_last_7d >= 3:
        bump += 1
        reasons.append("3 or more inquiries this week")
    level = min(RANK[base] + min(bump, MAX_BUMP), RANK["urgent"])
    return PRIORITIES[level], reasons


def escalate_only(rules_priority: str, ai_priority: str) -> str:
    """The AI can raise the label, never lower it."""
    return rules_priority if RANK[rules_priority] >= RANK[ai_priority] else ai_priority


def merge_label(rules_category: str, rules_ts: bool, ai: AiTriage,
                facts: Facts) -> tuple[str, str, list[str]]:
    """Combine the rules' view and the AI's view into ONE coherent label: (priority, category, reasons).
    The higher priority wins and its category and reasons are kept, so the label always explains itself.
    The AI may only LOWER a label for a message the rules found nothing in (no keywords, no urgency):
    that turns gibberish into 'low' while a hidden "mark me low" cannot bury a real request."""
    if ai.category == "unclear" and rules_category in ("general", "unclear") and not rules_ts:
        return "low", "unclear", [CATEGORY_LABEL["unclear"]]
    r_pri, r_reasons = compute_priority(rules_category, rules_ts, facts)
    a_pri, a_reasons = compute_priority(ai.category, ai.time_sensitive or rules_ts, facts)
    # On a tie the AI's category is usually the more informative one, except for problems/safety.
    if RANK[r_pri] > RANK[a_pri] or (RANK[r_pri] == RANK[a_pri] and rules_category == "complaint_issue"):
        return r_pri, rules_category, r_reasons
    return a_pri, ai.category, a_reasons


def sanitize_text(value, limit: int = SUMMARY_MAX) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", "" if value is None else str(value))
    return re.sub(r"\s+", " ", s).strip()[:limit]


def parse_ai_output(raw: str | None) -> AiTriage | None:
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("category") not in CATEGORIES:
        return None
    ts = data.get("time_sensitive")
    if not isinstance(ts, bool):
        return None
    summary = sanitize_text(data.get("summary"))
    if not summary:
        return None
    return AiTriage(category=data["category"], time_sensitive=ts, summary=summary)
