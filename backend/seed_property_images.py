import os
import json
import time
import urllib.request
import urllib.parse
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

if not PEXELS_API_KEY:
    raise RuntimeError("PEXELS_API_KEY must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# High quality luxury interior search query pool for varied results
LUXURY_SEARCH_QUERIES = [
    "luxury penthouse interior design",
    "modern luxury apartment living room",
    "exclusive luxury villa interior",
    "contemporary luxury condominium",
    "modern architectural luxury residence",
    "high end luxury estate interior",
    "modern minimalist luxury penthouse",
    "luxury dining room interior design",
    "scandinavian luxury apartment interior",
    "luxury master bedroom interior",
    "modern luxury kitchen design",
    "luxury oceanfront villa interior",
]


def fetch_pexels_image(query: str, offset: int = 0) -> str | None:
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page=15&page=1&orientation=landscape"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": PEXELS_API_KEY,
            "User-Agent": "PIPELINE.EV/1.0 (RealEstateDashboard)",
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            photos = data.get("photos", [])
            # Filter out black-and-white photos so all properties receive vibrant full-color source images
            color_photos = [
                p
                for p in photos
                if not any(
                    bw_term in (p.get("alt") or "").lower()
                    for bw_term in ["black and white", "monochrome", "b&w", "grayscale", "monochromatic"]
                )
            ]
            if color_photos:
                idx = offset % len(color_photos)
                return color_photos[idx]["src"]["large"]
            elif photos:
                idx = offset % len(photos)
                return photos[idx]["src"]["large"]
    except Exception as exc:
        print(f"  [FAIL] Pexels API error for query '{query}': {exc}")
    return None


def main():
    print("Fetching properties from Supabase...")
    res = supabase.table("properties").select("*").execute()
    properties = res.data or []
    print(f"Found {len(properties)} properties in Supabase.")

    if not properties:
        print("No properties found.")
        return

    updated_count = 0
    column_missing = False

    for idx, prop in enumerate(properties):
        address = prop.get("address", "")
        neighborhood = prop.get("neighborhood", "")

        # Try specific search query first
        query = f"luxury interior {neighborhood}"
        image_url = fetch_pexels_image(query, offset=idx)

        # Fallback to general luxury queries if search yielded no image
        if not image_url:
            fallback_query = LUXURY_SEARCH_QUERIES[idx % len(LUXURY_SEARCH_QUERIES)]
            image_url = fetch_pexels_image(fallback_query, offset=0)

        if not image_url:
            print(f"  [FAIL] Could not fetch image for '{address}' ({neighborhood})")
            continue

        try:
            supabase.table("properties").update({"image_url": image_url}).eq("id", prop["id"]).execute()
            print(f"  [OK] [{idx+1}/{len(properties)}] Updated '{address}' ({neighborhood})")
            updated_count += 1
        except Exception as exc:
            err_str = str(exc)
            if "image_url" in err_str or "PGRST204" in err_str:
                column_missing = True
                print("  [FAIL] Column 'image_url' is missing in 'properties' table.")
                break
            else:
                print(f"  [FAIL] Failed to update property '{address}': {exc}")

        time.sleep(0.2)

    if column_missing:
        print("\n" + "=" * 70)
        print("IMPORTANT: The 'image_url' column does not exist in 'properties' table yet.")
        print("Please run this command in your Supabase SQL Editor:")
        print("  ALTER TABLE properties ADD COLUMN IF NOT EXISTS image_url text;")
        print("Then re-run: python seed_property_images.py")
        print("=" * 70)
    else:
        print(f"\nDone! Successfully updated {updated_count}/{len(properties)} properties with Pexels images.")


if __name__ == "__main__":
    main()
