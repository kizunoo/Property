"""
Backfill realistic property specifications (sqft, bedrooms, bathrooms) based on property_value.

Heuristics:
- sqft: roughly property_value / 3000 to property_value / 2000 (varies per property, rounded to nearest 50)
- bedrooms: 2-3 for properties under RM3M, 3-4 for RM3M-6M, 4-5 for above RM6M
- bathrooms: bedrooms minus 0 or 1, with randomness
"""

import os
import random
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://tppzkfhhcnmdbwnamgqr.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_S5xiNz08pnHyzT21MSXf_Q_4VIwsU_p")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def backfill():
    print("Fetching properties from Supabase...")
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/properties?select=id,address,neighborhood,property_value&order=property_value.desc",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    if r.status_code != 200:
        raise RuntimeError(f"Failed to fetch properties: {r.status_code} {r.text}")

    properties = r.json()
    print(f"Found {len(properties)} properties to backfill.\n")

    updated = []
    for prop in properties:
        pid = prop["id"]
        val = float(prop["property_value"])
        addr = prop.get("address", "Unknown")
        neigh = prop.get("neighborhood", "")

        # Deterministic seed per property ID so results are stable & reproducible
        seed_val = int(pid.replace("-", "")[:8], 16)
        rng = random.Random(seed_val)

        # 1. sqft: property_value / (2000 to 3000), rounded to nearest 50
        psf_factor = rng.uniform(2000, 3000)
        raw_sqft = val / psf_factor
        sqft = int(round(raw_sqft / 50.0) * 50)
        # Ensure minimum plausible luxury size
        if sqft < 600:
            sqft = 600

        # 2. bedrooms: tiered by price
        if val < 3_000_000:
            bedrooms = rng.choice([2, 3])
        elif val <= 6_000_000:
            bedrooms = rng.choice([3, 4])
        else:
            bedrooms = rng.choice([4, 5])

        # 3. bathrooms: bedrooms minus 0 or 1
        baths_delta = rng.choice([0, 1])
        bathrooms = max(1, bedrooms - baths_delta)

        # PATCH row
        patch_res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/properties?id=eq.{pid}",
            headers=headers,
            json={
                "sqft": sqft,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms
            }
        )

        if patch_res.status_code not in (200, 204):
            print(f"FAILED to update {pid} ({addr}): {patch_res.status_code} {patch_res.text}")
        else:
            rm_per_sqft = round(val / sqft)
            updated.append({
                "id": pid,
                "address": addr,
                "neighborhood": neigh,
                "val": val,
                "sqft": sqft,
                "beds": bedrooms,
                "baths": bathrooms,
                "psf": rm_per_sqft
            })

    print(f"\nSuccessfully updated {len(updated)}/{len(properties)} properties.\n")
    print(f"{'ID':<9} {'Address':<32} {'Value (RM)':>12} {'SqFt':>7} {'Beds':>5} {'Baths':>6} {'RM/SqFt':>9}")
    print("-" * 88)
    for u in updated:
        print(f"{u['id'][:8]+'..':<9} {u['address'][:31]:<32} {u['val']:>12,.0f} {u['sqft']:>7,d} {u['beds']:>5} {u['baths']:>6} {u['psf']:>9,d}")

    # Verification query
    print("\n--- Verification Query ---")
    verify_res = requests.get(
        f"{SUPABASE_URL}/rest/v1/properties?select=id,address,bedrooms,bathrooms,sqft&or=(bedrooms.is.null,bathrooms.is.null,sqft.is.null)",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    unseeded = verify_res.json()
    print(f"SELECT count(*) FROM properties WHERE bedrooms IS NULL OR bathrooms IS NULL OR sqft IS NULL;")
    print(f"Result count: {len(unseeded)}")
    if len(unseeded) == 0:
        print("PASS: All 20 properties have non-null bedrooms, bathrooms, and sqft!")
    else:
        print(f"FAIL: {len(unseeded)} properties still have null specs: {unseeded}")

if __name__ == "__main__":
    backfill()
