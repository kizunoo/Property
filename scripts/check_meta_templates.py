import os
import requests
from dotenv import load_dotenv

load_dotenv("backend/.env", override=True)

token = os.getenv("WHATSAPP_ACCESS_TOKEN") or os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_ACCESS_TOKEN")
phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or os.getenv("WHATSAPP_WABA_ID")

print("Keys check:")
print("token set:", bool(token))
print("phone_id set:", bool(phone_id))
print("waba_id set:", bool(waba_id))

if not token:
    exit(1)

if not waba_id and phone_id:
    res = requests.get(
        f"https://graph.facebook.com/v21.0/{phone_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "whatsapp_business_account"}
    )
    data = res.json()
    waba_id = data.get("whatsapp_business_account", {}).get("id")
    print("waba_id resolved:", bool(waba_id))

if waba_id:
    res = requests.get(
        f"https://graph.facebook.com/v21.0/{waba_id}/message_templates",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = res.json()
    if "data" in data:
        print(f"Found {len(data['data'])} templates:")
        for t in data["data"]:
            print(f" - {t.get('name')} ({t.get('language')}): {t.get('status')}")
    else:
        print("Error querying templates:", data.get("error", {}).get("message"))
