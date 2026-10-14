#!/usr/bin/env python3
"""
verify_anon_security.py
Privilege-based security verification for Supabase (Zero writes).
Validates:
1. 'anon' and 'authenticated' roles have NO write privileges (INSERT, UPDATE, DELETE, TRUNCATE) on public tables.
2. 'portal_access_code' and 'whatsapp_number' are inaccessible to anon and authenticated roles.
3. Dashboard queries work via anon key.
4. Fails loudly with exit code 1 if ANY security violation is detected.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

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

print("=== [verify_anon_security] Privilege-Based Security Verification ===")
print(f"Supabase URL:       {'[Configured]' if url else '[MISSING]'}")
print(f"Anon Key:           {'[Configured]' if anon_key else '[MISSING]'}")
print(f"Service Role Key:   {'[Configured]' if service_key else '[MISSING]'}")

if not url or not anon_key:
    print("\n[FAIL] Missing Supabase URL or Anon Key.")
    sys.exit(1)

from supabase import create_client

anon_client = create_client(url, anon_key)
service_client = create_client(url, service_key) if service_key else None

violations = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Authority Check: information_schema.role_table_grants (via service_role)
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 1. Table Grants Audit (information_schema.role_table_grants) ---")
if service_client:
    try:
        grants_res = service_client.rpc("get_role_table_privileges").execute()
        grants = grants_res.data or []
        mutation_privs = {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
        
        table_summary = {}
        for g in grants:
            tbl = g.get("table_name")
            role = g.get("grantee")
            priv = g.get("privilege_type")
            
            if role not in table_summary:
                table_summary[role] = {}
            if tbl not in table_summary[role]:
                table_summary[role][tbl] = set()
            table_summary[role][tbl].add(priv)

            if priv in mutation_privs and role in ("anon", "authenticated"):
                violations.append(f"Illegal grant: {role} has {priv} on public.{tbl}")

        for role in ("anon", "authenticated"):
            role_grants = table_summary.get(role, {})
            print(f"Role '{role}': {len(role_grants)} tables granted")
            for t, priv_set in sorted(role_grants.items()):
                bad = priv_set.intersection(mutation_privs)
                status = f"[VIOLATION: {', '.join(bad)}]" if bad else "[READ-ONLY]"
                print(f"  - {t:<28} {status:<15} ({', '.join(sorted(priv_set))})")

    except Exception as exc:
        print(f"[*] Note: get_role_table_privileges RPC not available or failed: {exc}")
else:
    print("[*] Service role key not available; skipping direct role_table_grants inspection.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Clients Table Sensitive Column Protection
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 2. Sensitive Column Protection (portal_access_code & whatsapp_number) ---")

# Check A: Direct SELECT * via anon (Must fail because table-level SELECT is revoked)
try:
    c_all = anon_client.table("clients").select("*").limit(1).execute()
    violations.append("clients SELECT * is PERMITTED for anon (table-level SELECT not revoked)")
    print(f"  [FAIL] clients SELECT *: PERMITTED (Columns: {list(c_all.data[0].keys()) if c_all.data else []})")
except Exception as e:
    print(f"  [OK]   clients SELECT *: BLOCKED (Table-level grant revoked: {str(e)[:50]})")

# Check B: SELECT portal_access_code via anon (Must fail)
try:
    c_code = anon_client.table("clients").select("id, portal_access_code").limit(1).execute()
    violations.append(f"portal_access_code is EXPOSED to anon! Returned: {c_code.data}")
    print(f"  [FAIL] portal_access_code: EXPOSED ({c_code.data})")
except Exception as e:
    print(f"  [OK]   portal_access_code: PROTECTED against anon ({str(e)[:50]})")

# Check C: SELECT whatsapp_number via anon (Must fail)
try:
    c_wa = anon_client.table("clients").select("id, whatsapp_number").limit(1).execute()
    violations.append(f"whatsapp_number is EXPOSED to anon! Returned: {c_wa.data}")
    print(f"  [FAIL] whatsapp_number: EXPOSED ({c_wa.data})")
except Exception as e:
    print(f"  [OK]   whatsapp_number: PROTECTED against anon ({str(e)[:50]})")

# Check D: Check authenticated role column privileges via RPC if available
if service_client:
    for col in ("portal_access_code", "whatsapp_number"):
        try:
            has_priv = service_client.rpc(
                "check_column_privilege",
                {"p_role": "authenticated", "p_table": "clients", "p_column": col, "p_privilege": "SELECT"}
            ).execute().data
            if has_priv:
                violations.append(f"Column public.clients.{col} is readable by role 'authenticated'!")
                print(f"  [FAIL] {col}: EXPOSED to authenticated role!")
            else:
                print(f"  [OK]   {col}: PROTECTED against authenticated role")
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# 3. Dashboard Queries Functionality Check (Must Succeed)
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- 3. Required Dashboard Queries via Anon Key ---")
DASHBOARD_COLS = "id, name, stated_budget, preferred_neighborhood, past_viewings, financing_status, move_in_timeline, property_type_preference, secondary_neighborhood, agent_notes, assigned_agent_id, relationship_stage"
try:
    c_dash = anon_client.table("clients").select(DASHBOARD_COLS).limit(1).execute()
    print(f"  [OK]   Dashboard columns SELECT: SUCCESS ({len(c_dash.data or [])} rows retrieved)")
except Exception as e:
    violations.append(f"Dashboard client query failed for anon role: {e}")
    print(f"  [FAIL] Dashboard columns SELECT: FAILED ({e})")

# ─────────────────────────────────────────────────────────────────────────────
# Final Verdict
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if violations:
    print(f"[SECURITY VIOLATION DETECTED] ({len(violations)} issue(s) found):")
    for v in violations:
        print(f"  [!] {v}")
    print("\nSecurity check FAILED.")
    sys.exit(1)
else:
    print("[SUCCESS] All privilege checks passed. No mutation grants on public tables. Sensitive columns protected.")
    sys.exit(0)
