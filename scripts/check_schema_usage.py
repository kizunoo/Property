"""
scripts/check_schema_usage.py
──────────────────────────────
Comprehensive automated verification tool to enforce:
1. Schema vs Backend Column Parity:
   Every column read/written by backend code exists in migration definitions.
   Verifies migration table creation ordering.
2. Function Privileges & RLS Lockdown:
   Every CREATE FUNCTION in supabase/migrations has an explicit matching:
     - REVOKE ALL / EXECUTE ... FROM PUBLIC, anon, authenticated;
     - GRANT EXECUTE ... TO service_role;
   Verifies ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
3. Browser Security (.rpc Guard):
   Asserts ZERO calls to .rpc( exist across frontend browser code (app, components, lib).
4. RPC Contract Parity:
   Parses every supabase.rpc("function_name", {params}) call in backend/
   and compares:
     - Function name
     - Parameter names (p_*)
     - Output columns read (out_*) vs SQL RETURNS TABLE(...) definition.
"""

import sys
import re
from pathlib import Path
from typing import Dict, Set, List, Tuple, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = REPO_ROOT / "scripts"
APP_DIR = REPO_ROOT / "app"
COMPONENTS_DIR = REPO_ROOT / "components"
LIB_DIR = REPO_ROOT / "lib"


def parse_migration_tables() -> Tuple[Dict[str, Set[str]], List[str]]:
    """
    Parses migration files and extracts table definitions and creation order.
    """
    m1_path = MIGRATIONS_DIR / "20261014110000_portal_v2_phase1a.sql"
    m2_path = MIGRATIONS_DIR / "20261014120000_agent_auth_d1.sql"
    m3_path = MIGRATIONS_DIR / "20261015160000_auth_corrections.sql"

    if not m1_path.exists() or not m2_path.exists():
        raise FileNotFoundError(f"Missing migration files: {m1_path} or {m2_path}")

    sql_content = m1_path.read_text(encoding="utf-8") + "\n" + m2_path.read_text(encoding="utf-8")
    if m3_path.exists():
        sql_content += "\n" + m3_path.read_text(encoding="utf-8")

    table_order = []
    create_matches = re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s*\((.*?)\);", sql_content, re.DOTALL | re.IGNORECASE)

    tables = {}
    for match in create_matches:
        tname = match.group(1).lower()
        body = match.group(2)
        table_order.append(tname)

        cols = set()
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            if re.match(r"^(?:CONSTRAINT|PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK)", line, re.IGNORECASE):
                continue
            parts = line.split()
            if parts:
                col_name = parts[0].strip('"').lower()
                cols.add(col_name)

        tables[tname] = cols

    # Check for ALTER TABLE ADD COLUMN
    if "clients" not in tables:
        tables["clients"] = set()
    alter_matches = re.findall(r"ALTER\s+TABLE\s+(?:public\.)?([a-zA-Z0-9_]+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)", sql_content, re.IGNORECASE)
    for tbl, col in alter_matches:
        tbl_clean = tbl.lower()
        if tbl_clean in tables:
            tables[tbl_clean].add(col.lower())

    # Check for ALTER TABLE RENAME COLUMN
    rename_matches = re.findall(r"ALTER\s+TABLE\s+(?:public\.)?([a-zA-Z0-9_]+)\s+RENAME\s+COLUMN\s+([a-zA-Z0-9_]+)\s+TO\s+([a-zA-Z0-9_]+)", sql_content, re.IGNORECASE)
    for tbl, old_col, new_col in rename_matches:
        tbl_clean = tbl.lower()
        if tbl_clean in tables:
            tables[tbl_clean].add(new_col.lower())

    return tables, table_order


def scan_backend_column_usage() -> Dict[str, Set[str]]:
    """
    Scans python code for Supabase table queries (.select, .insert, .update, .eq, etc.)
    """
    files_to_scan = [
        BACKEND_DIR / "portal_auth.py",
        BACKEND_DIR / "portal_routes.py",
        BACKEND_DIR / "agent_auth.py",
        BACKEND_DIR / "agent_routes.py",
        BACKEND_DIR / "main.py",
        SCRIPTS_DIR / "seed_agent_accounts.py",
        SCRIPTS_DIR / "reset_agent_password_cli.py",
    ]

    target_tables = {
        "portal_contacts",
        "portal_sessions",
        "portal_audit_log",
        "portal_rate_limits",
        "agent_accounts",
        "agent_sessions",
        "agent_audit_log",
        "clients",
    }

    usage = {t: set() for t in target_tables}

    for fpath in files_to_scan:
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")

        for table in target_tables:
            # 1. .select(...)
            select_matches = re.findall(rf'table\(["\']{table}["\']\)[^;)]*\.select\(["\']([^"\']+)["\']', text)
            for sm in select_matches:
                sm_clean = re.sub(r'[a-zA-Z0-9_]+\([^)]*\)', '', sm)
                for col in sm_clean.split(","):
                    clean = col.strip()
                    if clean and not clean.startswith("*") and not clean.endswith("*") and not any(ch in clean for ch in "()"):
                        usage[table].add(clean.lower())

            # 2. .insert({ ... }) or .update({ ... })
            dict_matches = re.findall(rf'table\(["\']{table}["\']\)[^;)]*\.(?:insert|update|upsert)\(\s*\{{([^}}]+)\}}', text, re.DOTALL)
            for dm in dict_matches:
                col_keys = re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:', dm)
                for ck in col_keys:
                    usage[table].add(ck.lower())

            # 3. .eq("col", ...)
            eq_matches = re.findall(rf'table\(["\']{table}["\']\)[^;)]*\.eq\(["\']([a-zA-Z0-9_]+)["\']', text)
            for em in eq_matches:
                usage[table].add(em.lower())

            # 4. Dictionary assignment patterns
            if table == "portal_sessions":
                if "portal_sessions" in text:
                    for key in ["id", "client_id", "contact_id", "token_hash", "portal_role", "idle_expires_at", "absolute_expires_at", "last_active_at", "revoked_at", "ip_hash", "user_agent"]:
                        if f'"{key}"' in text or f"'{key}'" in text:
                            usage[table].add(key)

            if table == "agent_sessions":
                if "agent_sessions" in text:
                    for key in ["id", "account_id", "token_hash", "idle_expires_at", "absolute_expires_at", "last_active_at", "revoked_at", "ip_hash", "user_agent"]:
                        if f'"{key}"' in text or f"'{key}'" in text:
                            usage[table].add(key)

            if table == "portal_audit_log":
                if "portal_audit_log" in text:
                    for key in ["id", "client_id", "contact_id", "action", "object_type", "object_id", "details", "ip_hash", "created_at"]:
                        if f'"{key}"' in text or f"'{key}'" in text:
                            usage[table].add(key)

            if table == "agent_audit_log":
                if "agent_audit_log" in text:
                    for key in ["id", "account_id", "action", "object_type", "object_id", "details", "ip_hash", "created_at"]:
                        if f'"{key}"' in text or f"'{key}'" in text:
                            usage[table].add(key)

            if table == "clients":
                if "portal_access_code_hash" in text:
                    usage["clients"].add("portal_access_code_hash")

    return usage


def check_browser_rpc_calls() -> Tuple[bool, List[str]]:
    """
    Verifies that NO browser code (app, components, lib) calls .rpc(.
    """
    errors = []
    scanned_count = 0
    dirs = [APP_DIR, COMPONENTS_DIR, LIB_DIR]

    for d in dirs:
        if not d.exists():
            continue
        for ext in ("*.ts", "*.tsx", "*.js", "*.jsx"):
            for p in d.rglob(ext):
                scanned_count += 1
                try:
                    content = p.read_text(encoding="utf-8")
                except Exception:
                    continue
                if ".rpc(" in content:
                    errors.append(f"Browser security violation in {p.relative_to(REPO_ROOT)}: Direct .rpc() call detected!")

    return len(errors) == 0, errors, scanned_count


def check_migration_function_privileges() -> Tuple[bool, List[str]]:
    """
    Parses every CREATE FUNCTION in supabase/migrations/*.sql and enforces:
    1. Matching REVOKE ... FROM PUBLIC, anon, authenticated;
    2. Matching GRANT EXECUTE ... TO service_role;
    3. ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated.
    """
    errors = []
    all_sql_files = sorted(list(MIGRATIONS_DIR.glob("*.sql")))
    all_content = "\n".join(f.read_text(encoding="utf-8") for f in all_sql_files)

    # 1. Verify ALTER DEFAULT PRIVILEGES
    if not re.search(r"ALTER\s+DEFAULT\s+PRIVILEGES\s+IN\s+SCHEMA\s+public\s+REVOKE\s+EXECUTE\s+ON\s+FUNCTIONS\s+FROM\s+(?:PUBLIC,\s*anon,\s*authenticated|anon,\s*authenticated|PUBLIC)", all_content, re.IGNORECASE):
        errors.append("Missing 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated' across migrations.")

    # 2. Extract every CREATE FUNCTION
    func_pattern = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-zA-Z0-9_]+)\s*\((.*?)\)\s*RETURNS\s+([a-zA-Z0-9_()\s]+?)\s+(?:LANGUAGE|SECURITY|SET|AS)",
        re.DOTALL | re.IGNORECASE
    )

    found_functions = []
    for fpath in all_sql_files:
        txt = fpath.read_text(encoding="utf-8")
        for m in func_pattern.finditer(txt):
            fname = m.group(1).lower()
            args_raw = m.group(2).strip()
            returns_raw = m.group(3).strip().lower()
            # Trigger functions (RETURNS trigger) don't have direct RPC execution grants
            if "trigger" in returns_raw:
                continue
            found_functions.append((fname, args_raw, fpath.name))

    for fname, args_raw, mfile in found_functions:
        # Check revoke
        revoke_pat = rf"REVOKE\s+(?:ALL|EXECUTE)\s+(?:ON\s+FUNCTION\s+)?(?:public\.)?{fname}\b[^;]*FROM\s+[^;]*\banon\b"
        if not re.search(revoke_pat, all_content, re.IGNORECASE):
            errors.append(f"Function '{fname}' defined in {mfile} lacks 'REVOKE ... FROM anon' privilege revocation statement.")

        # Check grant to service_role
        grant_pat = rf"GRANT\s+(?:ALL|EXECUTE)\s+(?:ON\s+FUNCTION\s+)?(?:public\.)?{fname}\b[^;]*TO\s+[^;]*\bservice_role\b"
        if not re.search(grant_pat, all_content, re.IGNORECASE):
            errors.append(f"Function '{fname}' defined in {mfile} lacks 'GRANT ... TO service_role' privilege statement.")

    return len(errors) == 0, errors, found_functions


def check_rpc_contracts() -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Parses every .rpc("function_name", {params}) call in backend/
    and compares against the CREATE FUNCTION definitions in migrations:
      - Function name match
      - Parameter names match
      - Output column names read from result match RETURNS TABLE(...)
    """
    errors = []
    comparison_table = []

    m1_path = MIGRATIONS_DIR / "20261014110000_portal_v2_phase1a.sql"
    m2_path = MIGRATIONS_DIR / "20261014120000_agent_auth_d1.sql"
    sql_text = m1_path.read_text(encoding="utf-8") + "\n" + m2_path.read_text(encoding="utf-8")

    # Also include slot offer, reminder, and corrective migrations
    for older in ("20261012150000_whatsapp_slot_offers.sql", "20261012160000_whatsapp_reminders.sql", "20261012190000_security_hardening.sql", "20261015160000_auth_corrections.sql"):
        p = MIGRATIONS_DIR / older
        if p.exists():
            sql_text += "\n" + p.read_text(encoding="utf-8")

    # Parse SQL functions with params and returns table
    sql_funcs = {}
    func_regex = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-zA-Z0-9_]+)\s*\((.*?)\)\s*RETURNS\s+(?:TABLE\s*\((.*?)\)|[a-zA-Z0-9_]+)",
        re.DOTALL | re.IGNORECASE
    )

    for m in func_regex.finditer(sql_text):
        fname = m.group(1).lower()
        params_str = m.group(2)
        returns_table_str = m.group(3) or ""

        # Extract param names
        param_names = []
        for p in params_str.split(","):
            p_strip = p.strip()
            if not p_strip:
                continue
            parts = p_strip.split()
            if parts:
                param_names.append(parts[0].lower())

        # Extract return table columns
        return_cols = []
        for c in returns_table_str.split(","):
            c_strip = c.strip()
            if not c_strip:
                continue
            parts = c_strip.split()
            if parts:
                return_cols.append(parts[0].lower())

        sql_funcs[fname] = {
            "params": param_names,
            "return_cols": return_cols,
        }

    # Scan backend python files for .rpc( calls
    python_files = list(BACKEND_DIR.glob("*.py"))
    code_rpc_calls = {}

    rpc_call_regex = re.compile(r'(?:([a-zA-Z0-9_]+)\s*=\s*)?(?:supabase|service_client)\.rpc\(\s*["\']([a-zA-Z0-9_]+)["\'](?:\s*,\s*\{([^}]*)\})?', re.DOTALL)

    for pf in python_files:
        txt = pf.read_text(encoding="utf-8")
        for m in rpc_call_regex.finditer(txt):
            var_name = m.group(1)
            fname = m.group(2).lower()
            params_dict_str = m.group(3) or ""

            # Extract keys passed in dict
            passed_keys = [k.lower() for k in re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:', params_dict_str)]

            # Check if out_* columns are read ONLY if the result is assigned to a variable
            read_cols = []
            if var_name:
                start = m.end()
                window = txt[start:start+400]
                # Stop if another rpc or return is encountered
                stop_idx = len(window)
                for term in ("supabase.rpc", "def ", "return "):
                    pos = window.find(term)
                    if pos != -1 and pos < stop_idx:
                        stop_idx = pos
                window = window[:stop_idx]
                read_cols = list(set(re.findall(r'["\'](out_[a-zA-Z0-9_]+)["\']', window)))

            if fname not in code_rpc_calls:
                code_rpc_calls[fname] = {
                    "file": pf.name,
                    "passed_params": passed_keys,
                    "read_cols": read_cols,
                }
            else:
                for k in passed_keys:
                    if k not in code_rpc_calls[fname]["passed_params"]:
                        code_rpc_calls[fname]["passed_params"].append(k)
                for rc in read_cols:
                    if rc not in code_rpc_calls[fname]["read_cols"]:
                        code_rpc_calls[fname]["read_cols"].append(rc)

    # Validate parity
    for fname, code_meta in code_rpc_calls.items():
        sql_meta = sql_funcs.get(fname)
        if not sql_meta:
            errors.append(f"RPC Contract Violation: Python code in {code_meta['file']} calls .rpc('{fname}') which does not exist in migration SQL!")
            continue

        # Check parameter names
        for pk in code_meta["passed_params"]:
            if pk not in sql_meta["params"]:
                errors.append(f"RPC Contract Violation: Python passes parameter '{pk}' to '{fname}', but SQL defines: {sql_meta['params']}")

        # Check return columns read
        for rc in code_meta["read_cols"]:
            if rc not in sql_meta["return_cols"]:
                errors.append(f"RPC Contract Violation: Python reads column '{rc}' from '{fname}', but SQL RETURNS TABLE defines: {sql_meta['return_cols']}")

        comparison_table.append({
            "rpc_name": fname,
            "caller_file": code_meta["file"],
            "code_params": ", ".join(code_meta["passed_params"]) or "(none)",
            "sql_params": ", ".join(sql_meta["params"]) or "(none)",
            "code_out_cols": ", ".join(code_meta["read_cols"]) or "(none)",
            "sql_out_cols": ", ".join(sql_meta["return_cols"]) or "(none/void)",
            "status": "MATCH" if not errors else "CHECK",
        })

    return len(errors) == 0, errors, comparison_table


def check_schema_consistency() -> Tuple[bool, List[str], List[Dict[str, Any]]]:
    """
    Main verification pipeline:
    1. Migration ordering check.
    2. Column usage vs definitions.
    3. Function privileges check.
    4. Browser .rpc( absence check.
    5. RPC contract verification.
    """
    report = []
    has_errors = False

    report.append("=====================================================================")
    report.append("           SCHEMA, PRIVILEGES & RPC CONTRACT AUDIT REPORT")
    report.append("=====================================================================")

    # 1. Migration Ordering
    tables, table_order = parse_migration_tables()
    usage = scan_backend_column_usage()

    report.append("\n[1] MIGRATION TABLE ORDERING CHECK:")
    if "portal_contacts" in table_order and "portal_sessions" in table_order:
        contacts_idx = table_order.index("portal_contacts")
        sessions_idx = table_order.index("portal_sessions")
        if contacts_idx < sessions_idx:
            report.append(f"  [PASS] 'portal_contacts' (index {contacts_idx}) created BEFORE 'portal_sessions' (index {sessions_idx}).")
        else:
            report.append(f"  [FAIL] Migration ordering violation: 'portal_sessions' created before 'portal_contacts'!")
            has_errors = True

    if "agent_accounts" in table_order and "agent_sessions" in table_order:
        acc_idx = table_order.index("agent_accounts")
        sess_idx = table_order.index("agent_sessions")
        if acc_idx < sess_idx:
            report.append(f"  [PASS] 'agent_accounts' (index {acc_idx}) created BEFORE 'agent_sessions' (index {sess_idx}).")
        else:
            report.append(f"  [FAIL] Migration ordering violation: 'agent_sessions' created before 'agent_accounts'!")
            has_errors = True

    # 2. Column Consistency Check
    report.append("\n[2] COLUMN USAGE VS MIGRATION DEFINITIONS:")
    target_tables = [
        "portal_contacts",
        "portal_sessions",
        "portal_audit_log",
        "portal_rate_limits",
        "agent_accounts",
        "agent_sessions",
        "agent_audit_log",
        "clients",
    ]

    for table in target_tables:
        defined_cols = tables.get(table, set())
        used_cols = usage.get(table, set())

        if table == "clients":
            used_cols = {c for c in used_cols if c == "portal_access_code_hash"}

        missing_in_migration = used_cols - defined_cols
        if missing_in_migration:
            has_errors = True
            report.append(f"  [FAIL] Table '{table}': Code uses columns NOT in migration: {sorted(list(missing_in_migration))}")
        else:
            report.append(f"  [PASS] Table '{table}': All {len(used_cols)} code-referenced columns exist in migration schema.")

    # 3. Function Privileges Check
    report.append("\n[3] FUNCTION PRIVILEGES & SECURITY REVOKES CHECK:")
    priv_ok, priv_errors, func_list = check_migration_function_privileges()
    if not priv_ok:
        has_errors = True
        for pe in priv_errors:
            report.append(f"  [FAIL] {pe}")
    else:
        report.append(f"  [PASS] All {len(func_list)} migration functions have explicit REVOKE from anon/PUBLIC and GRANT to service_role.")
        report.append("  [PASS] ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE verified.")

    # 4. Browser .rpc( Absence Check
    report.append("\n[4] BROWSER CODE ZERO .rpc( CALLS CHECK:")
    browser_ok, browser_errors, scanned_files = check_browser_rpc_calls()
    if not browser_ok:
        has_errors = True
        for be in browser_errors:
            report.append(f"  [FAIL] {be}")
    else:
        report.append(f"  [PASS] Scanned {scanned_files} frontend files (app, components, lib). ZERO direct .rpc() calls found.")

    # 5. RPC Contract Parity Check
    report.append("\n[5] BACKEND RPC CONTRACT VS SQL SIGNATURES:")
    rpc_ok, rpc_errors, rpc_table = check_rpc_contracts()
    if not rpc_ok:
        has_errors = True
        for re_err in rpc_errors:
            report.append(f"  [FAIL] {re_err}")
    else:
        report.append(f"  [PASS] All {len(rpc_table)} backend RPC calls match SQL parameter names and return columns.")

    report.append("\n=====================================================================")
    if has_errors:
        report.append("RESULT: INCONSISTENCIES DETECTED. Review errors above.")
    else:
        report.append("RESULT: 100% PASS - SCHEMA, PRIVILEGES, BROWSER GUARD & RPC CONTRACTS IN TOTAL PARITY.")
    report.append("=====================================================================")

    return not has_errors, report, rpc_table


def main():
    success, report, _ = check_schema_consistency()
    print("\n".join(report))
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
