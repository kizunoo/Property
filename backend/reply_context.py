"""
Grounded context for AI reply suggestions. Pure/DB code, no AI here.

Safety design:
  * The model only ever sees what this module returns: the conversation (customer text marked
    untrusted_text), the company name + facility profile, and PRODUCT FACT SHEETS built from a fixed
    allow-list of catalog fields. Budgets, scores, tiers, rep notes and other companies are never included,
    so a manipulated model has nothing internal to leak.
  * finalize_suggestion() checks the model's output against those same facts: numbers that are not in the
    catalog or the conversation are flagged, and "facts used" the model cannot prove are dropped.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import inquiry_detail
from copilot_tools import (CLIENT_NAME_COL, CLIENT_TABLE, EV_COL, EVAL_CLIENT_COL, EVAL_TABLE,
                           ROBOT_NAME_COL, ROBOT_PRICE_COL, ROBOT_TABLE, UNTRUSTED_NOTE, Identity)
from inquiry_detail import clean_message
from triage_rules import sanitize_text

# ADAPT-ME: column on pipeline_evaluations that points at the product (properties.id)
EVAL_PROPERTY_COL = "property_id"

SCALAR_FACTS = (("manufacturer", "Manufacturer"), ("property_type", "Category"),
                ("description", "Description"))
SPEC_LABELS = {
    "payload_kg": "Payload capacity (kg)", "weight_kg": "Robot weight (kg)",
    "battery_hours": "Battery life (hours)", "lease_monthly": "Lease (RM per month)",
    "speed_mps": "Max speed (m/s)", "dimensions": "Dimensions",
    "warranty_months": "Warranty (months)", "key_specs": "Key specs",
    "target_industries": "Target industries",
}
MAX_DRAFT = 1500
MAX_FACT_VALUE = 200


def _fmt(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ""
    return sanitize_text(value, MAX_FACT_VALUE)


def product_sheet(row: dict, why: str = "") -> dict:
    facts: list[dict] = []

    def add(label: str, value) -> None:
        text = _fmt(value)
        if text:
            facts.append({"label": label, "value": text})

    for col, label in SCALAR_FACTS:
        add(label, row.get(col))
    add("Unit cost (RM)", row.get(ROBOT_PRICE_COL))
    specs = row.get("specs") if isinstance(row.get("specs"), dict) else {}
    for key, value in specs.items():
        add(SPEC_LABELS.get(key, str(key).replace("_", " ").capitalize()), value)
    return {
        "product_id": str(row.get("id")),
        "name": sanitize_text(row.get(ROBOT_NAME_COL), 120),
        "source": "demo data (not a real product)" if row.get("data_source") == "seed" else "catalog",
        "why_relevant": why,
        "facts": facts[:20],
    }


def _name_keys(name: str) -> set:
    n = (name or "").lower().strip()
    keys = {n} if len(n) >= 4 else set()
    for tok in re.findall(r"[a-z0-9][a-z0-9\-\.]*", n):
        if any(c.isdigit() for c in tok) and len(tok) >= 3:
            keys.add(tok)  # model codes such as "amr-4000"
    return keys


def candidate_products(db, client_id: str, conversation_text: str, roi=None, limit: int = 3) -> list:
    catalog = db.table(ROBOT_TABLE).select("*").limit(300).execute().data or []
    by_id = {str(r.get("id")): r for r in catalog}
    picked: list = []
    seen: set = set()

    def add(row, why):
        pid = str(row.get("id"))
        if pid not in seen and len(picked) < limit:
            seen.add(pid)
            picked.append(product_sheet(row, why))

    text = (conversation_text or "").lower()
    for r in catalog:
        if any(k in text for k in _name_keys(str(r.get(ROBOT_NAME_COL) or ""))):
            add(r, "named in the customer's messages")
    if isinstance(roi, dict):
        for key in ("property_id", "robot_id", "product_id", "unit_id"):
            if roi.get(key) and str(roi[key]) in by_id:
                add(by_id[str(roi[key])], "selected in the customer's ROI scenario")
    try:
        best = (db.table(EVAL_TABLE).select(EVAL_PROPERTY_COL).eq(EVAL_CLIENT_COL, client_id)
                .order(EV_COL, desc=True).limit(1).execute().data) or []
        if best and str(best[0].get(EVAL_PROPERTY_COL)) in by_id:
            add(by_id[str(best[0][EVAL_PROPERTY_COL])], "closest match on file for this company")
    except Exception:  # noqa: BLE001
        pass
    return picked


def find_products(db, query: str, limit: int = 5) -> list:
    q = re.sub(r"[%_\\]", " ", str(query or "")).strip()[:60]
    if len(q) < 2:
        return []
    rows = db.table(ROBOT_TABLE).select("*").ilike(ROBOT_NAME_COL, f"%{q}%").limit(limit).execute().data or []
    return [product_sheet(r, "found by search") for r in rows]


def build_context(db, identity: Identity, inquiry_id: str) -> Optional[dict]:
    detail = inquiry_detail.get_inquiry_detail(db, identity, inquiry_id)  # scoped; None if not yours
    if detail is None:
        return None
    inq = detail["inquiry"]
    client = (db.table(CLIENT_TABLE).select("*").eq("id", inq["client_id"]).limit(1).execute().data
              or [{}])[0]
    roi = (db.table(inquiry_detail.INQUIRY_TABLE).select("roi_scenario").eq("id", inquiry_id)
           .limit(1).execute().data or [{}])[0].get("roi_scenario")
    conversation = [{"from": "company", "untrusted_text": detail["original_message"]}]
    conversation += [{"from": m["sender"],
                      ("untrusted_text" if m["sender"] == "company" else "text"): m["body"]}
                     for m in detail["messages"]]
    all_text = " ".join(c.get("untrusted_text") or c.get("text") or "" for c in conversation)
    return {
        "note": UNTRUSTED_NOTE,
        "company": inq["company"],
        "facility_profile": client.get("facility_profile") or {},
        "conversation": conversation,
        "candidate_products": candidate_products(db, inq["client_id"], all_text, roi),
    }


# ----------------------------- model output handling -----------------------------
def parse_suggestion(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    draft = clean_message(data.get("draft"), MAX_DRAFT)
    if not draft:
        return None

    def pairs(v):
        out = []
        for item in (v if isinstance(v, list) else [])[:8]:
            if isinstance(item, dict) and item.get("label") and item.get("value") is not None:
                out.append({"label": sanitize_text(item["label"], 60), "value": sanitize_text(item["value"], 120)})
        return out

    missing = [sanitize_text(m, 140) for m in (data.get("missing") if isinstance(data.get("missing"), list) else [])[:6]
               if sanitize_text(m, 140)]
    product = sanitize_text(data.get("product"), 120) if data.get("product") else None
    return {"draft": draft, "product": product, "facts_used": pairs(data.get("facts_used")), "missing": missing}


_NUM = re.compile(r"\d[\d,]*\.?\d*")


def ungrounded_numbers(draft: str, corpus: list) -> list:
    hay = " ".join(corpus).lower().replace(",", "")
    bad: list = []
    for m in _NUM.findall(draft or ""):
        n = m.replace(",", "").rstrip(".")
        if n and n not in hay and n not in bad:
            bad.append(n)
    return bad


def finalize_suggestion(parsed: dict, sheets: list, conversation: list, company: str) -> dict:
    corpus = [company]
    corpus += [(c.get("untrusted_text") or c.get("text") or "") for c in conversation]
    known = []
    for s in sheets:
        corpus.append(s["name"])
        for f in s["facts"]:
            corpus.append(f["value"])
            known.append((f["label"].lower(), f["value"].lower()))

    verified, dropped = [], 0
    for f in parsed["facts_used"]:
        lbl, val = f["label"].lower(), f["value"].lower()
        if any(lbl == kl and val and (val in kv or kv in val) for kl, kv in known):
            verified.append(f)
        else:
            dropped += 1

    warnings = []
    bad = ungrounded_numbers(parsed["draft"], corpus)
    if bad:
        warnings.append("The draft contains figures that are not in the catalog or the conversation: "
                        + ", ".join(bad) + ". Check them before sending.")
    if dropped:
        warnings.append(f"{dropped} fact(s) the AI listed could not be verified and were hidden.")

    product = parsed.get("product")
    match = next((s for s in sheets if product and s["name"].lower() == product.lower()), None)
    pool = [match] if match else sheets
    uses_demo = any(s["source"].startswith("demo") for s in pool)
    return {"draft": parsed["draft"], "product": product, "facts_used": verified,
            "missing": parsed["missing"], "warnings": warnings, "uses_demo_data": uses_demo}
