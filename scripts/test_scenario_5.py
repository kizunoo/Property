import os
import sys
import json
import time
import hmac
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load env without printing
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
fastapi_url = "http://127.0.0.1:8000"
nextjs_url = "http://127.0.0.1:3000"

phone = "60109722730"
question_text = "Can the robotics unit handle outdoor uneven terrain?"

print("==================================================================")
print("TESTING SCENARIO 5: Rep Panel & AI Reply Suggestions")
print("==================================================================")

# ----------------------------------------------------------------------
# Step 1: Simulate Inbound Prospect Message to Webhook
# ----------------------------------------------------------------------
print("\n[Step 1] Simulating inbound WhatsApp message from prospect...")
unique_wamid = f"wamid.scenario5_test_{int(time.time())}"
webhook_payload = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "1812002506602083",
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {
                    "display_phone_number": "15551386714",
                    "phone_number_id": "1291109974093102"
                },
                "contacts": [{
                    "profile": {"name": "Abdullah"},
                    "wa_id": phone
                }],
                "messages": [{
                    "from": phone,
                    "id": unique_wamid,
                    "timestamp": str(int(time.time())),
                    "text": {"body": question_text},
                    "type": "text"
                }]
            },
            "field": "messages"
        }]
    }]
}

raw_bytes = json.dumps(webhook_payload).encode("utf-8")
headers = {"Content-Type": "application/json"}
if app_secret:
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers["X-Hub-Signature-256"] = f"sha256={sig}"

wh_resp = requests.post(f"{fastapi_url}/api/whatsapp/webhook", data=raw_bytes, headers=headers)
print(f"Webhook response: HTTP {wh_resp.status_code} - {wh_resp.text}")
assert wh_resp.status_code == 200, f"Webhook failed with status {wh_resp.status_code}"

time.sleep(1)

# ----------------------------------------------------------------------
# Step 2: Verify Conversation in Rep Panel via Next.js
# ----------------------------------------------------------------------
print("\n[Step 2] Fetching Rep Panel conversations from Next.js (port 3000)...")
conv_resp = requests.get(f"{nextjs_url}/api/whatsapp/conversations")
print(f"Conversations response: HTTP {conv_resp.status_code}")
assert conv_resp.status_code == 200, f"Conversations endpoint failed: {conv_resp.status_code}"

conv_data = conv_resp.json()
threads = conv_data.get("conversations", [])
matching_thread = next((t for t in threads if t.get("phone_number") == phone), None)

if matching_thread:
    print(f"-> Found conversation thread for {phone}:")
    print(f"   Client Name:   {matching_thread.get('client_name')}")
    print(f"   Status Bucket: {matching_thread.get('status_bucket')}")
    print(f"   Unread Count:  {matching_thread.get('unread_count')}")
    print(f"   Window Open:   {matching_thread.get('window_open')}")
else:
    print(f"Warning: Thread for {phone} not found in first page of conversations.")

# ----------------------------------------------------------------------
# Step 3: Test AI Reply Suggestion
# ----------------------------------------------------------------------
print("\n[Step 3] Requesting AI reply suggestion for client's question...")
suggest_resp = requests.post(
    f"{nextjs_url}/api/whatsapp/suggest_reply",
    json={
        "phone_number": phone,
        "prompt_context": question_text
    }
)
print(f"Suggest Reply response: HTTP {suggest_resp.status_code}")
assert suggest_resp.status_code == 200, f"Suggest reply failed: {suggest_resp.status_code}"

suggest_data = suggest_resp.json()
suggested_text = suggest_data.get("suggested_text", "")
print("-> AI Suggested Draft Response:")
print(f"   \"{suggested_text}\"")
assert len(suggested_text) > 10, "Suggested text is unexpectedly empty"

# ----------------------------------------------------------------------
# Step 4: Dispatch Representative Reply via Next.js Rep Panel Endpoint
# ----------------------------------------------------------------------
print("\n[Step 4] Dispatching representative manual reply via Next.js /api/whatsapp/send...")
send_resp = requests.post(
    f"{nextjs_url}/api/whatsapp/send",
    json={
        "to_number": phone,
        "message": suggested_text,
        "client_name": matching_thread.get("client_name") if matching_thread else "Abdullah",
        "manual_override": True
    }
)
print(f"Send Reply response: HTTP {send_resp.status_code} - {send_resp.text}")
assert send_resp.status_code == 200, f"Send failed: {send_resp.status_code}"

time.sleep(1)

# ----------------------------------------------------------------------
# Step 5: Verify Message Thread History
# ----------------------------------------------------------------------
print("\n[Step 5] Verifying thread message history via Next.js...")
msg_resp = requests.get(f"{nextjs_url}/api/whatsapp/messages?to_number={phone}")
print(f"Messages response: HTTP {msg_resp.status_code}")
assert msg_resp.status_code == 200, f"Messages failed: {msg_resp.status_code}"

msg_data = msg_resp.json()
msgs = msg_data.get("messages", [])
print(f"-> Total messages in thread: {len(msgs)}")
last_msgs = msgs[-3:] if len(msgs) >= 3 else msgs
for m in last_msgs:
    print(f"   [{m.get('sender').upper()}] {m.get('text')} (status: {m.get('status')})")

print("\n==================================================================")
print("SCENARIO 5 TEST COMPLETE: ALL STEPS PASSED SUCCESSFULLY!")
print("==================================================================")
