#!/usr/bin/env python3
"""
Real-data importer for PIPELINE.EV (B2B robotics). Idempotent. Never prints emails/phones.

  python scripts/import_real_data.py --dir data/templates --dry-run   # validate only, no DB access
  python scripts/import_real_data.py --dry-run                        # validate data/real/*
  python scripts/import_real_data.py --purge-dummy --dry-run          # show what would be deleted
  python scripts/import_real_data.py --purge-dummy --confirm-purge    # delete seed rows (data_source='seed')
  python scripts/import_real_data.py --import                         # upsert robots + companies + contacts

Safety: refuses ENVIRONMENT=production unless --force-prod-init; never touches agent tables;
refuses to import template/placeholder rows; aborts before any write if an agent email is unknown.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# ADAPT-ME: logical field -> real column name. Verify against supabase/migrations/.
# Edit ONLY these constants; do not change the logic below.
# ---------------------------------------------------------------------------
PROPERTY_COLS = {"name": "address", "price": "property_value", "description": "specs",
                 "category": "category", "image_url": "image_url"}
CLIENT_COLS = {"name": "name", "email": "email", "phone": "phone", "budget": "stated_budget",
               "location": "preferred_neighborhood", "size_sqft": "facility_size_sqm",
               "assigned_agent": "assigned_agent_id", "crm_stage": "relationship_stage"}
CONTACT_TABLE = "portal_contacts"
CONTACT_COLS = {"client_id": "client_id", "name": "name", "email": "email",
                "phone": "whatsapp_number", "role": "title"}
AGENT_TABLE, AGENT_EMAIL_COL, AGENT_ID_COL = "agent_accounts", "email", "agent_id"
ENV_URL, ENV_KEY = "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"

# Delete order for --purge-dummy (children first). Starting point: verify against the FK graph.
CLIENT_CHILD_TABLES = [
    "whatsapp_reminders", "whatsapp_slot_offers", "whatsapp_messages", "whatsapp_contact_state",
    "signals", "portal_unit_feedback", "portal_quotes", "inquiry_messages", "client_inquiries",
    "portal_profile_audit", "scheduled_viewings", "pipeline_evaluations", "portal_contacts",
]
PROPERTY_CHILD_TABLES = [
    "pipeline_evaluations", "scheduled_viewings", "portal_quotes", "portal_unit_feedback",
    "price_history", "past_purchases",
]
PROTECTED_TABLES = {"agent_accounts", "agent_sessions", "agent_audit_log"}

# ---------------------------------------------------------------------------
ROBOT_REQUIRED = ["sku_code", "name", "manufacturer", "category", "price"]
ROBOT_OPTIONAL_NUM = ["lease_monthly", "payload_kg", "battery_hours", "weight_kg", "speed_mps",
                      "warranty_months"]
COMPANY_REQUIRED = ["company_name", "industry", "assigned_agent_email"]
# Contact person fields are OPTIONAL (public sources only give a company main line).
# Without contact_email no portal contact is created: add it after you speak to someone.
COMPANY_OPTIONAL_NUM = ["facility_size_sqft", "estimated_budget"]
PLACEHOLDER_DOMAINS = {"example.com", "example.org", "test.com"}

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

FACILITY_TYPES = [("logist", "warehouse"), ("3pl", "warehouse"), ("warehouse", "warehouse"),
                  ("manufactur", "manufacturing"), ("factory", "manufacturing"),
                  ("hospital", "healthcare"), ("health", "healthcare"), ("clean", "cleaning"),
                  ("mall", "retail_hospitality"), ("retail", "retail_hospitality"),
                  ("hotel", "retail_hospitality"), ("hospitality", "retail_hospitality")]
USE_CASES = [("palletiz", "palletizing"), ("pallet", "transport"), ("transport", "transport"),
             ("clean", "cleaning"), ("secur", "security"), ("inspect", "security"),
             ("deliver", "delivery")]


# ----------------------------- CSV + validation -----------------------------
def load_csv(path: Path, required: list[str]):
    if not path.exists():
        return [], [f"missing file: {path}"]
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = [c.strip() for c in (reader.fieldnames or [])]
        missing = [c for c in required if c not in cols]
        if missing:
            return [], [f"{path.name}: missing columns {missing}"]
        rows = []
        for r in reader:
            row = {k.strip(): (v or "").strip() for k, v in r.items() if k}
            if any(row.values()):
                rows.append(row)
    return rows, []


def num(s: str):
    return float(s.replace(",", "")) if s else None


def check_nums(r, cols, line, errors):
    for c in cols:
        if r.get(c):
            try:
                if num(r[c]) < 0:
                    errors.append(f"line {line}: {c} must be >= 0")
            except ValueError:
                errors.append(f"line {line}: {c} is not a number")


def validate_robots(rows):
    errors, placeholders, seen = [], [], set()
    for i, r in enumerate(rows, start=2):
        for c in ROBOT_REQUIRED:
            if not r.get(c):
                errors.append(f"line {i}: {c} is required")
        check_nums(r, ["price"] + ROBOT_OPTIONAL_NUM, i, errors)
        sku = r.get("sku_code", "")
        if sku in seen:
            errors.append(f"line {i}: duplicate sku_code {sku}")
        seen.add(sku)
        if r.get("image_url") and not r["image_url"].startswith("http"):
            errors.append(f"line {i}: image_url must start with http")
        if sku.upper().startswith("EXAMPLE"):
            placeholders.append(f"line {i}: template row ({sku})")
    return errors, placeholders


def validate_companies(rows):
    errors, placeholders, seen = [], [], set()
    for i, r in enumerate(rows, start=2):
        for c in COMPANY_REQUIRED:
            if not r.get(c):
                errors.append(f"line {i}: {c} is required")
        check_nums(r, COMPANY_OPTIONAL_NUM, i, errors)
        for col in ("contact_email", "assigned_agent_email"):
            if r.get(col) and not EMAIL.match(r[col]):
                errors.append(f"line {i}: {col} is not a valid email")
        for col in ("company_phone_e164", "contact_phone_e164"):
            if r.get(col) and not E164.match(r[col]):
                errors.append(f"line {i}: {col} must be E.164 like +60123456789 "
                              "(Excel drops the '+': format the column as Text)")
        if not (r.get("company_phone_e164") or r.get("contact_phone_e164")):
            errors.append(f"line {i}: need company_phone_e164 or contact_phone_e164")
        if r.get("contact_email") and not r.get("contact_name"):
            errors.append(f"line {i}: contact_name required when contact_email is given")
        if r.get("website") and not r["website"].startswith("http"):
            errors.append(f"line {i}: website must start with http")
        key = r.get("company_name", "").lower()
        if key in seen:
            errors.append(f"line {i}: duplicate company_name")
        seen.add(key)
        domain = r.get("contact_email", "").split("@")[-1].lower()
        if domain in PLACEHOLDER_DOMAINS or r.get("company_name", "").upper().startswith("EXAMPLE"):
            placeholders.append(f"line {i}: template row ({r.get('company_name', '')})")
    return errors, placeholders


# ------------------------------- row builders -------------------------------
def keyword_map(text: str, table):
    t = (text or "").lower()
    for k, v in table:
        if k in t:
            return v
    return None


def build_robot_row(r):
    specs = {k: (num(r[k]) if k in ROBOT_OPTIONAL_NUM else r[k])
             for k in ROBOT_OPTIONAL_NUM + ["key_specs", "target_industries", "dimensions"] if r.get(k)}
    return {
        PROPERTY_COLS["name"]: r["name"],
        PROPERTY_COLS["price"]: num(r["price"]),
        PROPERTY_COLS["description"]: r.get("key_specs", ""),
        PROPERTY_COLS["category"]: r["category"],
        PROPERTY_COLS["image_url"]: r.get("image_url") or None,
        "sku_code": r["sku_code"], "manufacturer": r["manufacturer"],
        "specs": specs, "data_source": "real",
    }


def build_client_row(r, agent_id):
    row = {
        CLIENT_COLS["name"]: r["company_name"],
        CLIENT_COLS["phone"]: r.get("contact_phone_e164") or r["company_phone_e164"],
        CLIENT_COLS["assigned_agent"]: agent_id,
        "data_source": "real",
    }
    if r.get("contact_email"):
        row[CLIENT_COLS["email"]] = r["contact_email"].lower()
    if r.get("estimated_budget"):
        row[CLIENT_COLS["budget"]] = num(r["estimated_budget"])
    if r.get("facility_location"):
        row[CLIENT_COLS["location"]] = r["facility_location"]
    if r.get("facility_size_sqft"):
        row[CLIENT_COLS["size_sqft"]] = num(r["facility_size_sqft"])
    if r.get("crm_stage"):
        row[CLIENT_COLS["crm_stage"]] = r["crm_stage"]
    profile = {}
    ft = keyword_map(r.get("industry"), FACILITY_TYPES)
    uc = keyword_map(r.get("target_use_case"), USE_CASES)
    if ft:
        profile["facility_type"] = ft
    if uc:
        profile["primary_use_case"] = uc
    if r.get("facility_size_sqft"):
        profile["floor_area_sqm"] = round(num(r["facility_size_sqft"]) * 0.092903, 1)
    if r.get("target_use_case"):
        profile["environment_notes"] = r["target_use_case"][:1000]
    if profile:
        row["facility_profile"] = profile
    return row


def build_contact_row(r, client_id):
    row = {
        CONTACT_COLS["client_id"]: client_id,
        CONTACT_COLS["name"]: r.get("contact_name") or r["company_name"],
        CONTACT_COLS["email"]: r["contact_email"].lower(),
        CONTACT_COLS["phone"]: r.get("contact_phone_e164") or r["company_phone_e164"],
    }
    if r.get("contact_role"):
        row[CONTACT_COLS["role"]] = r["contact_role"]
    return row


# ---------------------------------- DB ----------------------------------
def guard_env(args):
    if os.getenv("ENVIRONMENT", "development").lower() == "production" and not args.force_prod_init:
        sys.exit("Refusing: ENVIRONMENT=production (pass --force-prod-init to override).")


def get_db():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend" / ".env")
    except ImportError:
        pass
    from supabase import create_client
    url, key = os.getenv(ENV_URL), os.getenv(ENV_KEY)
    if not url or not key:
        sys.exit(f"Set {ENV_URL} and {ENV_KEY} (backend/.env).")
    print(f"Target Supabase host: {url.split('//')[-1].split('/')[0]}")
    return create_client(url, key)


def chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def seed_ids(sb, table):
    ids, start = [], 0
    while True:
        batch = (sb.table(table).select("id").eq("data_source", "seed")
                 .range(start, start + 999).execute().data)
        ids += [b["id"] for b in batch]
        if len(batch) < 1000:
            return ids
        start += 1000


def purge_step(sb, table, col, ids, dry, critical=False):
    if table in PROTECTED_TABLES:
        sys.exit(f"Refusing to touch protected table {table}")
    total = 0
    try:
        for ch in chunks(ids, 100):
            q = sb.table(table)
            if dry:
                total += q.select(col, count="exact").in_(col, ch).execute().count or 0
            else:
                total += len(q.delete().in_(col, ch).execute().data or [])
    except Exception as e:  # noqa: BLE001
        if critical:
            raise
        return f"  {table}.{col}: skipped ({type(e).__name__}: {str(e)[:100]})"
    return f"  {table}: {total} {'would be ' if dry else ''}deleted"


def do_purge(sb, dry):
    clients, props = seed_ids(sb, "clients"), seed_ids(sb, "properties")
    print(f"Seed clients: {len(clients)} | seed properties: {len(props)} (agent tables untouched)")
    steps = ([(t, "client_id", clients, False) for t in CLIENT_CHILD_TABLES]
             + [(t, "property_id", props, False) for t in PROPERTY_CHILD_TABLES]
             + [("clients", "id", clients, True), ("properties", "id", props, True)])
    for table, col, ids, critical in steps:
        print(purge_step(sb, table, col, ids, dry, critical))


def upsert(sb, table, match: dict, row: dict):
    q = sb.table(table).select("id")
    for k, v in match.items():
        q = q.eq(k, v)
    found = q.limit(1).execute().data
    if found:
        sb.table(table).update(row).eq("id", found[0]["id"]).execute()
        return found[0]["id"], "updated"
    return sb.table(table).insert(row).execute().data[0]["id"], "inserted"


def run_scoring(sb, client_ids):
    """WIRE-ME: call the EXISTING scoring pipeline that fills pipeline_evaluations
    (scoring_engine.score / ml_inference / existing recompute endpoint) for each client id.
    Do not reimplement scoring here."""
    sys.path.insert(0, str(ROOT / "backend"))
    from scoring_engine import score as score_pair
    try:
        from ml_inference import predict_probability
    except Exception:
        predict_probability = lambda c, p: None

    if not client_ids:
        return

    clients_res = sb.table("clients").select("*").in_("id", client_ids).execute()
    clients = clients_res.data or []
    props_res = sb.table("properties").select("*").execute()
    properties = props_res.data or []

    if not properties:
        print("[run_scoring] No properties/robots in catalog yet; skipping evaluation computation.")
        return

    evaluations = []
    for client in clients:
        client_profile = {
            "budget": client.get("stated_budget"),
            "preferred_neighborhood": client.get("preferred_neighborhood"),
            "engagement_history": client.get("past_viewings", 0),
            "source": client.get("source"),
            "financing_status": client.get("financing_status"),
            "move_in_timeline": client.get("move_in_timeline"),
            "property_type_preference": client.get("property_type_preference"),
            "secondary_neighborhood": client.get("secondary_neighborhood"),
        }
        for prop in properties:
            prop_data = {
                "neighborhood": prop.get("neighborhood") or "",
                "property_value": float(prop.get("property_value") or 0),
                "property_type": prop.get("property_type"),
            }
            res = score_pair(client_profile, prop_data)
            ml_prob = None
            try:
                ml_prob = predict_probability(client_profile, prop_data)
            except Exception:
                pass
            evaluations.append({
                "client_id": client["id"],
                "property_id": prop["id"],
                "ai_probability": res["probability"],
                "expected_value": res["expected_value"],
                "segment_tier": res["tier"],
                "ml_probability": ml_prob,
            })

    for batch in chunks(evaluations, 100):
        try:
            sb.table("pipeline_evaluations").upsert(batch, on_conflict="client_id,property_id").execute()
        except Exception as exc:
            if "ml_probability" in str(exc):
                for b in batch:
                    b.pop("ml_probability", None)
                sb.table("pipeline_evaluations").upsert(batch, on_conflict="client_id,property_id").execute()
            else:
                raise


def agent_email_for(r, default_agent):
    return (r.get("assigned_agent_email") or default_agent or "").lower()


def do_import(sb, robots, companies, skip_scoring, default_agent=None):
    agents = {}
    if any(not agent_email_for(r, default_agent) for r in companies):
        sys.exit("Some companies have no assigned_agent_email; pass --default-agent-email. Nothing written.")
    for e in sorted({agent_email_for(r, default_agent) for r in companies}):
        res = (sb.table(AGENT_TABLE).select(AGENT_ID_COL)
               .ilike(AGENT_EMAIL_COL, e).limit(1).execute().data)
        if not res:
            sys.exit("An assigned_agent_email has no agent account. Nothing was written. "
                     "Seed that agent first (scripts/seed_agent_accounts.py).")
        agents[e] = res[0][AGENT_ID_COL]

    stats = {"robots": {"inserted": 0, "updated": 0}, "companies": {"inserted": 0, "updated": 0},
             "contacts": {"inserted": 0, "updated": 0}}
    for r in robots:
        _, how = upsert(sb, "properties", {"sku_code": r["sku_code"], "data_source": "real"},
                        build_robot_row(r))
        stats["robots"][how] += 1
    client_ids = []
    for r in companies:
        agent_id = agents[agent_email_for(r, default_agent)]
        cid, how = upsert(sb, "clients",
                          {CLIENT_COLS["name"]: r["company_name"], "data_source": "real"},
                          build_client_row(r, agent_id))
        stats["companies"][how] += 1
        client_ids.append(cid)
        if r.get("contact_email"):
            _, how = upsert(sb, CONTACT_TABLE,
                            {CONTACT_COLS["client_id"]: cid,
                             CONTACT_COLS["email"]: r["contact_email"].lower()},
                            build_contact_row(r, cid))
            stats["contacts"][how] += 1
    print("Import done:", stats)
    if skip_scoring:
        print("Scoring skipped (--skip-scoring).")
        return
    try:
        run_scoring(sb, client_ids)
        print(f"Scoring ran for {len(client_ids)} companies.")
    except NotImplementedError as e:
        print(f"WARNING: {e}. Data imported but pipeline_evaluations NOT populated.")
        sys.exit(2)


# ---------------------------------- main ----------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--dir", default="data/real", help="folder with robots_catalog.csv + b2b_companies.csv")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--import", dest="do_import", action="store_true")
    p.add_argument("--purge-dummy", action="store_true")
    p.add_argument("--confirm-purge", action="store_true")
    p.add_argument("--force-prod-init", action="store_true")
    p.add_argument("--skip-scoring", action="store_true")
    p.add_argument("--default-agent-email", help="rep used when a row has no assigned_agent_email")
    p.add_argument("--default-agent", help="agent email used for rows with empty assigned_agent_email")
    args = p.parse_args()
    if not (args.dry_run or args.do_import or args.purge_dummy):
        p.error("choose --dry-run, --import and/or --purge-dummy")

    if args.purge_dummy:
        if not args.dry_run:
            if not args.confirm_purge:
                sys.exit("--purge-dummy needs --confirm-purge (or --dry-run to preview).")
            guard_env(args)
        do_purge(get_db(), args.dry_run)

    if args.do_import or (args.dry_run and not args.purge_dummy):
        base = Path(args.dir)
        base = base if base.is_absolute() else ROOT / base
        if (base / "robots_catalog.csv").exists():
            robots, e1 = load_csv(base / "robots_catalog.csv", ROBOT_REQUIRED)
        else:
            robots, e1 = [], []
            print("Note: no robots_catalog.csv found; importing companies only.")
        companies, e2 = load_csv(base / "b2b_companies.csv", COMPANY_REQUIRED)
        if args.default_agent:
            for r in companies:
                r["assigned_agent_email"] = r.get("assigned_agent_email") or args.default_agent
        v1, ph1 = validate_robots(robots)
        v2, ph2 = validate_companies(companies)
        errors, placeholders = e1 + e2 + v1 + v2, ph1 + ph2
        print(f"Robots: {len(robots)} rows | Companies: {len(companies)} rows")
        for m in errors:
            print("ERROR:", m)
        for m in placeholders:
            print("PLACEHOLDER:", m)
        if errors:
            sys.exit(1)
        if args.dry_run or not args.do_import:
            print("Dry run OK: would upsert "
                  f"{len(robots)} robots, {len(companies)} companies + primary contacts, "
                  "then run scoring. No database access was made.")
            return
        if placeholders:
            sys.exit("Refusing to import template/placeholder rows. Replace them with real data.")
        guard_env(args)
        do_import(get_db(), robots, companies, args.skip_scoring, args.default_agent_email)


if __name__ == "__main__":
    main()
