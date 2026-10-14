#!/usr/bin/env python3
"""
scripts/rotate_legacy_access_codes.py
──────────────────────────────────────
One-time rotation script for legacy company portal access codes.

Features:
- Migrates plaintext clients.portal_access_code into clients.portal_access_code_hash (HMAC-SHA256).
- Sets clients.portal_access_code = NULL in database.
- Outputs newly generated codes to terminal stdout ONCE for administrative dispatch.
- Zero logging to disk or files.
- Uses obviously fictional company names for documentation and dry-run samples.

Usage:
  python scripts/rotate_legacy_access_codes.py [--dry-run] [--sample]
"""

import os
import sys
import argparse
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")
load_dotenv()

from portal_auth import get_code_pepper, hash_code, generate_secure_code

FICTIONAL_SAMPLES = [
    {"name": "AeroForge Robotics Sdn Bhd", "code": "K9X7-M2P4"},
    {"name": "Apex Automation Dynamics Bhd", "code": "R3T8-W5Y2"},
    {"name": "CyberJaya Robot Fleet Systems", "code": "B6D4-H7J9"},
    {"name": "Vanguard AMRs & Cobots Malaysia", "code": "E2L8-N4P5"},
]


def print_table(rows):
    col1_w = max(len(r["name"]) for r in rows) + 2
    col2_w = 26
    total_w = col1_w + col2_w + 3

    print("=" * total_w)
    print(f"{'Company Name':<{col1_w}} | {'New Legacy Access Code':<{col2_w}}")
    print("-" * total_w)
    for r in rows:
        print(f"{r['name']:<{col1_w}} | {r['code']:<{col2_w}}")
    print("=" * total_w)
    print("\nIMPORTANT: These codes are shown ONCE and will not be displayed again.")
    print("They are stored in the database exclusively as HMAC-SHA256 hashes.\n")


def main():
    parser = argparse.ArgumentParser(description="Rotate legacy company access codes")
    parser.add_argument("--dry-run", action="store_true", help="Generate and display codes without writing to DB")
    parser.add_argument("--sample", action="store_true", help="Display sample output with fictional companies")
    args = parser.parse_args()

    if args.sample:
        print("\n--- SAMPLE ROTATION OUTPUT (FICTIONAL COMPANIES) ---")
        print_table(FICTIONAL_SAMPLES)
        return

    # Check pepper
    try:
        pepper = get_code_pepper()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY")
    )

    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment.", file=sys.stderr)
        sys.exit(1)

    from supabase import create_client
    supabase = create_client(supabase_url, supabase_key)

    try:
        clients_res = supabase.table("clients").select("id, name, portal_access_code").execute()
        clients = clients_res.data or []
    except Exception as exc:
        print(f"Database query failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not clients:
        print("No clients found in database.")
        return

    results = []
    for client in clients:
        client_id = client["id"]
        company_name = client.get("name") or "Unknown Company"
        new_code = generate_secure_code(8)
        new_hash = hash_code(new_code)

        if not args.dry_run:
            supabase.table("clients").update({
                "portal_access_code": None,
                "portal_access_code_hash": new_hash,
            }).eq("id", client_id).execute()

        results.append({"name": company_name, "code": new_code})

    mode_label = "[DRY RUN] " if args.dry_run else ""
    print(f"\n--- {mode_label}ONE-TIME ACCESS CODE ROTATION RESULTS ---")
    print_table(results)


if __name__ == "__main__":
    main()
