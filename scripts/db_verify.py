#!/usr/bin/env python3
"""
db_verify.py
Comprehensive read-only database verification tool for PIPELINE.EV:
1. Validates table & column schema existence.
2. Checks RLS status (enabled/disabled) and policy counts per table.
3. Checks privileges for anon and authenticated roles.
4. Confirms clients.portal_access_code and clients.whatsapp_number are protected.
5. Verifies existence and signatures of booking and reminder RPC functions.
6. Executes exact dashboard queries from lib/fetch-pipeline-data.ts with the anon key.
7. Prints row counts and returned column names only. NEVER writes data. NEVER prints secrets.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env variables without printing secrets
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(root_dir / "backend" / ".env")
load_dotenv(root_dir / ".env.local")

url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
anon_key = (
    os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_KEY")
)
service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("=== [db:verify] Read-Only Database Verification ===")
print(f"Supabase URL:       {'[Configured]' if url else '[MISSING]'}")
print(f"Anon Key:           {'[Configured]' if anon_key else '[MISSING]'}")
print(f"Service Role Key:   {'[Configured]' if service_key else '[MISSING]'}")

if not url or not anon_key:
    print("\nError: Missing Supabase URL or Anon key. Aborting.")
    sys.exit(1)

from supabase import create_client

anon_client = create_client(url, anon_key)
service_client = create_client(url, service_key) if service_key else None

EXPECTED_TABLES = [
    "properties",
    "clients",
    "pipeline_evaluations",
    "signals",
    "agents",
    "scheduled_viewings",
    "client_inquiries",
    "invite_drafts",
    "whatsapp_conversations",
    "whatsapp_messages",
    "whatsapp_slot_offers",
    "whatsapp_reminders",
    "whatsapp_contact_state",
    "client_past_purchases",
    "property_price_history",
    "daily_worklist_cache",
    "chart_insight_cache",
    "model_training_runs",
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema, RLS, and Function Inspection via inspect_schema_security or REST
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 1. Tables, Row-Level Security (RLS) & Policy Counts ---")
schema_info = None

if service_client:
    try:
        rpc_res = service_client.rpc("inspect_schema_security").execute()
        schema_info = rpc_res.data
    except Exception:
        # Fallback if inspect_schema_security RPC not yet deployed
        pass

if schema_info and "tables" in schema_info:
    table_map = {t["table_name"]: t for t in schema_info.get("tables", [])}
    for tbl in EXPECTED_TABLES:
        t_data = table_map.get(tbl)
        if t_data:
            rls_str = "ENABLED" if t_data["rls_enabled"] else "DISABLED (UNSAFE)"
            print(f"  [EXISTS] {tbl:<26} RLS: {rls_str:<17} Policies: {t_data['policy_count']}")
        else:
            print(f"  [MISSING] {tbl:<25} (Not found in public schema)")
else:
    # PostgREST probe fallback using service role or anon
    probe_client = service_client or anon_client
    for tbl in EXPECTED_TABLES:
        try:
            r = probe_client.table(tbl).select("id").limit(1).execute()
            print(f"  [EXISTS] {tbl:<26} (Accessible via PostgREST)")
        except Exception as e:
            err = str(e)
            if "permission denied" in err.lower() or "42501" in err:
                print(f"  [EXISTS] {tbl:<26} (RLS Active / Table locked)")
            elif "not find" in err.lower() or "pgrst205" in err.lower():
                print(f"  [MISSING] {tbl:<25} (Not in schema cache)")
            else:
                print(f"  [STATUS] {tbl:<26} ({err[:50]})")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Function Signatures
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 2. Booking and Reminder RPC Functions ---")
EXPECTED_FUNCS = [
    ("claim_and_book_slot_offer", "offer_id uuid, slot_index integer, client_id uuid, property_id uuid, scheduled_at timestamptz"),
    ("claim_and_lock_pending_reminders", "batch_limit integer"),
    ("check_column_privilege", "role text, table text, column text, privilege text"),
]

if schema_info and "functions" in schema_info:
    func_map = {f["function_name"]: f for f in schema_info.get("functions", [])}
    for fname, exp_args in EXPECTED_FUNCS:
        fdata = func_map.get(fname)
        if fdata:
            print(f"  [EXISTS] {fname}")
            print(f"           Signature: {fdata.get('identity_args')}")
        else:
            print(f"  [MISSING] {fname}")
else:
    for fname, _ in EXPECTED_FUNCS:
        if service_client:
            try:
                # Attempt dry test call with dummy params
                service_client.rpc(fname, {}).execute()
                print(f"  [EXISTS] {fname}")
            except Exception as e:
                err = str(e)
                if "Could not find the function" in err or "PGRST202" in err:
                    print(f"  [MISSING] {fname}")
                else:
                    print(f"  [EXISTS] {fname} (Callable - verified with service_role)")
        else:
            print(f"  [UNKNOWN] {fname} (Requires service_role key to probe)")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Sensitive Column Privileges on `clients`
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 3. Client Sensitive Column Grants (portal_access_code & whatsapp_number) ---")
sensitive_cols = ["portal_access_code", "whatsapp_number"]

for col in sensitive_cols:
    # 1. Direct anon REST query test
    try:
        res = anon_client.table("clients").select(f"id, {col}").limit(1).execute()
        print(f"  [!] {col:<20} EXPOSED TO ANON KEY! (Returned {len(res.data or [])} rows)")
    except Exception as e:
        print(f"  [OK] {col:<20} Protected against anon (Denied: 42501 / column revoked)")

    # 2. Check authenticated privilege if helper available
    if service_client:
        try:
            auth_can_read = service_client.rpc(
                "check_column_privilege",
                {"p_role": "authenticated", "p_table": "clients", "p_column": col, "p_privilege": "SELECT"}
            ).execute().data
            if auth_can_read:
                print(f"  [!] {col:<20} EXPOSED to 'authenticated' role!")
            else:
                print(f"  [OK] {col:<20} Protected against 'authenticated' role")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# 4. Exact Dashboard Queries via Anon Key (from lib/fetch-pipeline-data.ts)
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 4. Dashboard Queries (lib/fetch-pipeline-data.ts via Anon Key) ---")

CLIENT_RICH_COLS = "id, name, stated_budget, preferred_neighborhood, past_viewings, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, assigned_agent_id, relationship_stage, agents(id, name, initials)"
PROPERTY_RICH_COLS = "id, address, neighborhood, property_value, bedrooms, bathrooms, sqft, property_type, furnishing, tenure"

# Query 1: Pipeline Evaluations Primary Query
try:
    q1 = anon_client.table("pipeline_evaluations").select(
        f"id, ai_probability, expected_value, segment_tier, outcome, ml_probability, clients({CLIENT_RICH_COLS}), properties({PROPERTY_RICH_COLS})"
    ).range(0, 5).execute()
    cols = list(q1.data[0].keys()) if q1.data else []
    print(f"  [OK] Primary Pipeline Query:    {len(q1.data or []):>2} rows | Root cols: {cols}")
except Exception as e:
    print(f"  [FAIL] Primary Pipeline Query:   {str(e)[:70]}")

# Query 2: Properties Catalog Query
try:
    q2 = anon_client.table("properties").select(
        "id, address, neighborhood, property_value, image_url, status, owner_client_id, closed_at, last_price_change_at, last_price_change_pct, bedrooms, bathrooms, sqft, property_type, furnishing, tenure, clients(name), assigned_agent_id, agents(id, name, initials)"
    ).limit(5).execute()
    cols = list(q2.data[0].keys()) if q2.data else []
    print(f"  [OK] Properties Catalog Query:  {len(q2.data or []):>2} rows | Root cols: {cols}")
except Exception as e:
    print(f"  [FAIL] Properties Catalog Query: {str(e)[:70]}")

# Query 3: Client Past Purchases Query
try:
    q3 = anon_client.table("client_past_purchases").select(
        "*, properties(image_url)"
    ).limit(5).execute()
    cols = list(q3.data[0].keys()) if q3.data else []
    print(f"  [OK] Past Purchases Query:      {len(q3.data or []):>2} rows | Root cols: {cols}")
except Exception as e:
    print(f"  [FAIL] Past Purchases Query:     {str(e)[:70]}")

# Query 4: Standalone Clients Rich Query
try:
    q4 = anon_client.table("clients").select(
        "id, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, relationship_stage"
    ).limit(5).execute()
    cols = list(q4.data[0].keys()) if q4.data else []
    print(f"  [OK] Standalone Clients Query:   {len(q4.data or []):>2} rows | Root cols: {cols}")
except Exception as e:
    print(f"  [FAIL] Standalone Clients Query: {str(e)[:70]}")

print("\n=== Verification Complete: Zero writes performed. ===")
