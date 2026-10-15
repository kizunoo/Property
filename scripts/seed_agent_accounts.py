"""
scripts/seed_agent_accounts.py
──────────────────────────────
Part D Stage D1: CLI provisioning tool for agent accounts.
Generates single-use enrollment codes (valid 48h) for initial agent access.
The enrollment code is printed ONCE to stdout and stored only as an HMAC-SHA256 hash.
Agents redeem the code via POST /api/agent/enroll to set their initial Argon2id password.

Links agent accounts to existing representatives in public.agents via agent_id FK.
Admin accounts that map to no agents row are permitted (agent_id = NULL).

Usage:
  # Provision an admin account directly
  python scripts/seed_agent_accounts.py --email admin@example.com --name "System Administrator" --role admin

  # Provision an agent representative by linking to their agents table row
  python scripts/seed_agent_accounts.py --email zaki@example.com --name "Ahmad Zaki" --role agent --match-name "Ahmad Zaki"

  # Batch provision from a CSV file (email, name, role, match_name)
  python scripts/seed_agent_accounts.py --csv agents.csv

  # Dry-run validation (does not write to database or consume codes)
  python scripts/seed_agent_accounts.py --csv agents.csv --dry-run
"""

import sys
import os
import csv
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Set

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from agent_auth import generate_enrollment_code, hash_enrollment_code


def resolve_agent_rep_id(supabase_client, agent_id: Optional[str], match_name: Optional[str]) -> Optional[str]:
    """Resolves and validates a representative from the public.agents table."""
    if agent_id:
        res = supabase_client.table("agents").select("id, name").eq("id", agent_id).limit(1).execute()
        if not res.data:
            print(f"ERROR: No representative found in 'agents' table with ID: {agent_id}")
            return None
        return res.data[0]["id"]

    if match_name:
        res = supabase_client.table("agents").select("id, name").ilike("name", match_name.strip()).limit(1).execute()
        if res.data:
            return res.data[0]["id"]
        else:
            print(f"WARNING: No representative in 'agents' table matched name '{match_name}'.")

    return None


def provision_agent(
    supabase_client,
    email: str,
    name: str,
    role: str = "agent",
    agent_id: Optional[str] = None,
    match_name: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    email_clean = email.strip().lower()
    name_clean = name.strip()
    role_clean = role.strip().lower()

    if role_clean not in ("admin", "agent"):
        print(f"Error: Role must be 'admin' or 'agent'. Got '{role_clean}'.")
        return False

    linked_agent_id = resolve_agent_rep_id(
        supabase_client,
        agent_id,
        match_name or (name_clean if role_clean == "agent" else None)
    )

    if dry_run:
        print("\n" + "-" * 64)
        print(f"[DRY-RUN] Would provision agent account: {name_clean} <{email_clean}>")
        print(f"  Role:                {role_clean.upper()}")
        print(f"  Linked Rep ID:       {linked_agent_id or 'None (Admin Global Visibility)'}")
        print(f"  Enrollment Code:     [SIMULATED - 48h validity]")
        print("-" * 64)
        return True

    # Check 1:1 agent_id link constraint
    if linked_agent_id:
        existing_rep = supabase_client.table("agent_accounts").select("id, email").eq("agent_id", linked_agent_id).limit(1).execute()
        if existing_rep.data and existing_rep.data[0]["email"] != email_clean:
            print(f"ERROR: Representative ID {linked_agent_id} is already linked to account {existing_rep.data[0]['email']}.")
            return False

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=48)
    code = generate_enrollment_code()
    code_h = hash_enrollment_code(code)

    res = supabase_client.table("agent_accounts").select("id, email, status").eq("email", email_clean).limit(1).execute()
    if res.data:
        acc = res.data[0]
        if acc["status"] == "active":
            print(f"Agent account '{email_clean}' is already active. Use password reset flow if needed.")
            return False
        update_data = {
            "name": name_clean,
            "role": role_clean,
            "enrollment_code_hash": code_h,
            "enrollment_code_expires_at": exp.isoformat(),
            "updated_at": now.isoformat(),
        }
        if linked_agent_id:
            update_data["agent_id"] = linked_agent_id
        supabase_client.table("agent_accounts").update(update_data).eq("id", acc["id"]).execute()
        acc_id = acc["id"]
    else:
        row = {
            "email": email_clean,
            "name": name_clean,
            "role": role_clean,
            "agent_id": linked_agent_id,
            "password_hash": None,
            "status": "pending_enrollment",
            "enrollment_code_hash": code_h,
            "enrollment_code_expires_at": exp.isoformat(),
        }
        res_ins = supabase_client.table("agent_accounts").insert(row).execute()
        acc_id = res_ins.data[0]["id"] if res_ins.data else "new"

    print("\n" + "=" * 64)
    print(f"AGENT ACCOUNT PROVISIONED: {name_clean} <{email_clean}>")
    print(f"Account ID:          {acc_id}")
    print(f"Linked Rep ID:       {linked_agent_id or 'None (Admin Global Visibility)'}")
    print(f"Role:                {role_clean.upper()}")
    print(f"One-Time Code:       {code}")
    print(f"Expires At:          {exp.isoformat()} (48 hours)")
    print("=" * 64)
    print("ACTION REQUIRED:")
    print("Deliver this one-time code to the agent over a secure out-of-band channel.")
    print("The agent must navigate to /login and submit this code under 'Redeem Enrollment Code'.")
    print("This code cannot be retrieved again.\n")
    return True


def process_csv_provisioning(supabase_client, csv_path: Path, dry_run: bool = False):
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    seen_emails: Set[str] = set()
    records: List[Dict[str, str]] = []

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            email = (row.get("email") or "").strip().lower()
            name = (row.get("name") or "").strip()
            role = (row.get("role") or "agent").strip().lower()
            agent_id = (row.get("agent_id") or "").strip() or None
            match_name = (row.get("match_name") or row.get("name") or "").strip() or None

            if not email or not name:
                print(f"Row {idx}: Skipping row with missing email or name.")
                continue

            if email in seen_emails:
                print(f"ERROR: Duplicate email detected in CSV at row {idx}: '{email}'. Aborting.")
                sys.exit(1)

            seen_emails.add(email)
            records.append({
                "email": email,
                "name": name,
                "role": role,
                "agent_id": agent_id,
                "match_name": match_name,
            })

    print(f"Parsed {len(records)} unique agent records from {csv_path.name}.")
    for r in records:
        provision_agent(
            supabase_client,
            email=r["email"],
            name=r["name"],
            role=r["role"],
            agent_id=r["agent_id"],
            match_name=r["match_name"],
            dry_run=dry_run,
        )


def main_cli():
    parser = argparse.ArgumentParser(description="Seed and provision agent accounts.")
    parser.add_argument("--email", help="Agent corporate email address")
    parser.add_argument("--name", help="Agent full name")
    parser.add_argument("--role", default="agent", choices=["admin", "agent"], help="Account role")
    parser.add_argument("--agent-id", help="UUID of existing row in public.agents table")
    parser.add_argument("--match-name", help="Match name against public.agents table")
    parser.add_argument("--csv", help="Path to CSV file with columns: email, name, role, [agent_id], [match_name]")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without modifying database")
    parser.add_argument("--seed-defaults", action="store_true", help="Seed accounts from CSV or reject if no CSV provided")

    args = parser.parse_args()

    import main
    supabase = main.supabase

    if args.csv:
        process_csv_provisioning(supabase, Path(args.csv), dry_run=args.dry_run)
    elif args.seed_defaults:
        print("ERROR: The 'public.agents' table contains representatives (name, role, initials) but NO corporate emails.")
        print("To provision accounts without inventing fictitious emails, specify a CSV file:")
        print("  python scripts/seed_agent_accounts.py --csv <path-to-agents.csv>")
        print("Or provision individual accounts using:")
        print("  python scripts/seed_agent_accounts.py --email agent@company.com --name 'Rep Name' --match-name 'Rep Name'")
        sys.exit(1)
    elif args.email and args.name:
        provision_agent(
            supabase,
            email=args.email,
            name=args.name,
            role=args.role,
            agent_id=args.agent_id,
            match_name=args.match_name,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main_cli()
