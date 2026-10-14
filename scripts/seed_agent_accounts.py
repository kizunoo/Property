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
  # Seed an admin account (not linked to an agents row)
  python scripts/seed_agent_accounts.py --email admin@pipeline-ev.com --name "System Administrator" --role admin

  # Seed an agent account linked to an existing agents row by ID
  python scripts/seed_agent_accounts.py --email rep1@pipeline-ev.com --name "Ahmad Zaki" --role agent --agent-id 11111111-2222-3333-4444-555555555555

  # Seed an agent account matched automatically by name against public.agents
  python scripts/seed_agent_accounts.py --email rep1@pipeline-ev.com --name "Ahmad Zaki" --role agent --match-name "Ahmad Zaki"

  # Seed defaults from database agents table
  python scripts/seed_agent_accounts.py --seed-defaults
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from agent_auth import generate_enrollment_code, hash_enrollment_code, hash_password


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
            print(f"Matched representative '{res.data[0]['name']}' (ID: {res.data[0]['id']})")
            return res.data[0]["id"]
        else:
            print(f"WARNING: No representative in 'agents' matched name '{match_name}'.")

    return None


def provision_agent(
    supabase_client,
    email: str,
    name: str,
    role: str = "agent",
    agent_id: Optional[str] = None,
    match_name: Optional[str] = None,
):
    email_clean = email.strip().lower()
    name_clean = name.strip()
    role_clean = role.strip().lower()

    if role_clean not in ("admin", "agent"):
        print(f"Error: Role must be 'admin' or 'agent'. Got '{role_clean}'.")
        return False

    # Resolve linked representative row if role is agent or if explicitly requested
    linked_agent_id = resolve_agent_rep_id(supabase_client, agent_id, match_name or name_clean if role_clean == "agent" else None)

    # Check if this agent_id is already assigned to another account (1:1 constraint)
    if linked_agent_id:
        existing_rep = supabase_client.table("agent_accounts").select("id, email").eq("agent_id", linked_agent_id).limit(1).execute()
        if existing_rep.data and existing_rep.data[0]["email"] != email_clean:
            print(f"ERROR: Representative ID {linked_agent_id} is already linked to account {existing_rep.data[0]['email']}.")
            return False

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=48)
    code = generate_enrollment_code()
    code_h = hash_enrollment_code(code)

    # Check if account already exists
    res = supabase_client.table("agent_accounts").select("id, email, status").eq("email", email_clean).limit(1).execute()
    if res.data:
        acc = res.data[0]
        if acc["status"] == "active":
            print(f"Agent account '{email_clean}' is already active. Use password reset flow if needed.")
            return False
        # Update enrollment code for pending account
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
        # Create new pending enrollment account with temporary placeholder password hash
        row = {
            "email": email_clean,
            "name": name_clean,
            "role": role_clean,
            "agent_id": linked_agent_id,
            "password_hash": hash_password(code + "_placeholder_pending"),
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


def main_cli():
    parser = argparse.ArgumentParser(description="Seed and provision agent accounts.")
    parser.add_argument("--email", help="Agent corporate email address")
    parser.add_argument("--name", help="Agent full name")
    parser.add_argument("--role", default="agent", choices=["admin", "agent"], help="Account role")
    parser.add_argument("--agent-id", help="UUID of existing row in public.agents table")
    parser.add_argument("--match-name", help="Match name against public.agents table")
    parser.add_argument("--seed-defaults", action="store_true", help="Seed default administrative and rep accounts from public.agents")

    args = parser.parse_args()

    import main
    supabase = main.supabase

    if args.seed_defaults:
        print("Seeding administrative account...")
        provision_agent(supabase, "admin@pipeline-ev.internal", "System Administrator", "admin", agent_id=None)

        print("\nQuerying existing representatives from public.agents...")
        try:
            agents_res = supabase.table("agents").select("id, name").order("name").execute()
            reps = agents_res.data or []
            print(f"Found {len(reps)} representatives in 'agents' table.")
            for rep in reps:
                rep_name = rep["name"]
                # Formulate corporate email
                slug = rep_name.lower().replace(" ", ".").replace("'", "")
                rep_email = f"{slug}@pipeline-ev.internal"
                provision_agent(supabase, rep_email, rep_name, "agent", agent_id=rep["id"])
        except Exception as exc:
            print(f"Error querying agents table: {exc}")

    elif args.email and args.name:
        provision_agent(
            supabase,
            args.email,
            args.name,
            args.role,
            agent_id=args.agent_id,
            match_name=args.match_name,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main_cli()
