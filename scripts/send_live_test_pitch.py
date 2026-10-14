import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

from main import send_pitch_via_whatsapp, is_within_24h_window

phone = "60109722730"
print("Window open check for", phone, ":", is_within_24h_window(phone))

payload = {
    "client_id": "8cd99c1f-3e31-42d5-80fa-2831bf350b9e",
    "property_id": "998a6ad3-7d3a-4861-adc1-ff5146ad0a4e",
    "to_number": phone,
    "draft_text": "Hello Abdullah! Following up from PIPELINE.EV regarding our AgroHarvest Picker Bot. Would your team be open to an on-site demonstration? Please choose a time below that works best for your team:",
    "slots": [
        {"index": 1, "date": "2026-10-15", "time": "10:00", "label": "Thu 15 Oct, 10:00 AM"},
        {"index": 2, "date": "2026-10-15", "time": "14:30", "label": "Thu 15 Oct, 2:30 PM"},
        {"index": 3, "date": "2026-10-16", "time": "11:00", "label": "Fri 16 Oct, 11:00 AM"}
    ]
}

try:
    res = send_pitch_via_whatsapp(payload)
    print("SEND RESULT SUCCESS:")
    print(json.dumps(res, indent=2))
except Exception as e:
    print("SEND RESULT ERROR:", e)
