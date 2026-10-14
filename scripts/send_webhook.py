#!/usr/bin/env python3
"""
Helper utility to dispatch signed WhatsApp webhook payloads to the backend.
Computes X-Hub-Signature-256 using WHATSAPP_APP_SECRET from environment.
Does NOT print or leak secret values.

Usage:
    python scripts/send_webhook.py --payload '{"entry":[...]}'
    python scripts/send_webhook.py --file path/to/payload.json
"""

import os
import sys
import json
import hmac
import hashlib
import argparse
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load env without printing
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
target_url = os.getenv("WEBHOOK_TARGET_URL", "http://localhost:8000/api/whatsapp/webhook")


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    if not secret:
        return ""
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


import time


def main():
    parser = argparse.ArgumentParser(description="Send signed WhatsApp webhook payload")
    parser.add_argument("--wamid", type=str, help="WhatsApp Message ID (wamid) to simulate status for")
    parser.add_argument("--status", type=str, choices=["sent", "delivered", "read", "failed"], help="Status to update to")
    parser.add_argument("--error-code", type=int, help="Optional Meta error code (e.g. 131026)")
    parser.add_argument("--error-title", type=str, default="Message Undeliverable", help="Optional Meta error title")
    parser.add_argument("--recipient-id", type=str, default="60109722730", help="Recipient phone number")
    parser.add_argument("--payload", type=str, help="Raw JSON payload string")
    parser.add_argument("--file", type=str, help="Path to JSON file")
    parser.add_argument("--url", type=str, default=target_url, help="Backend webhook URL")
    args = parser.parse_args()

    if args.wamid and args.status:
        status_obj = {
            "id": args.wamid,
            "status": args.status,
            "timestamp": str(int(time.time())),
            "recipient_id": args.recipient_id,
        }
        if args.error_code:
            status_obj["errors"] = [{
                "code": args.error_code,
                "title": args.error_title or "Message Undeliverable",
            }]

        sample = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "statuses": [status_obj],
                            },
                            "field": "messages",
                        }
                    ]
                }
            ],
        }
        raw_text = json.dumps(sample)
    elif args.payload:
        raw_text = args.payload
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        # Default sample delivery status payload
        sample = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.test_sample_001",
                                        "status": "delivered",
                                        "recipient_id": "60109722730",
                                        "timestamp": str(int(time.time())),
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        raw_text = json.dumps(sample)

    payload_bytes = raw_text.encode("utf-8")
    headers = {"Content-Type": "application/json"}

    sig = compute_signature(payload_bytes, app_secret)
    if sig:
        headers["X-Hub-Signature-256"] = sig
        print(f"[*] Attached X-Hub-Signature-256 (computed from environment secret)")
    else:
        print("[*] WHATSAPP_APP_SECRET empty or unset; sending without signature header (requires ENFORCE_WA_SIGNATURE=false)")

    try:
        resp = requests.post(args.url, data=payload_bytes, headers=headers, timeout=10)
        print(f"[*] Response Status: {resp.status_code}")
        print(f"[*] Response Body:   {resp.text}")
    except Exception as exc:
        print(f"[!] Request failed: {exc}")


if __name__ == "__main__":
    main()
