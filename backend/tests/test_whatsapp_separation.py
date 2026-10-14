import hashlib
import hmac
import json
import os
import sys
import uuid
import pytest
from starlette.testclient import TestClient

# Ensure test mode / memory store is active during pytest execution
os.environ["WHATSAPP_TEST_MODE"] = "true"
os.environ["WHATSAPP_USE_MEMORY_STORE"] = "true"
os.environ["ENABLE_WA_SIMULATOR"] = "true"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    app,
    WHATSAPP_MESSAGE_HISTORY,
    WHATSAPP_APP_SECRET,
    WHATSAPP_SLOT_OFFERS,
)


def compute_sig(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


class TestWhatsAppSeparation:
    @pytest.fixture(autouse=True)
    def setup_client_and_store(self, monkeypatch):
        self.client = TestClient(app)
        self.app_secret = WHATSAPP_APP_SECRET or "25381f8b46e30b6f917548c41ec352a9"
        monkeypatch.setenv("WHATSAPP_APP_SECRET", self.app_secret)
        monkeypatch.setenv("WHATSAPP_TEST_MODE", "true")
        monkeypatch.setenv("WHATSAPP_USE_MEMORY_STORE", "true")
        WHATSAPP_MESSAGE_HISTORY.clear()
        WHATSAPP_SLOT_OFFERS.clear()

    def test_two_agent_same_phone_separation_and_webhook_idempotency(self, monkeypatch):
        test_phone = "60109722730"
        agent_a_id = f"agent-{uuid.uuid4()}"
        agent_b_id = f"agent-{uuid.uuid4()}"
        client_x_id = f"client-{uuid.uuid4()}"
        client_y_id = f"client-{uuid.uuid4()}"

        # 1. Mock Supabase calls to simulate clean test environment
        class MockResult:
            data = []
            def execute(self):
                return self

        class MockQuery:
            def __init__(self, table_name):
                self.table_name = table_name

            def select(self, *args, **kwargs):
                return self
            def insert(self, *args, **kwargs):
                return self
            def update(self, *args, **kwargs):
                return self
            def upsert(self, *args, **kwargs):
                return self
            def eq(self, *args, **kwargs):
                return self
            def order(self, *args, **kwargs):
                return self
            def limit(self, *args, **kwargs):
                return self
            def in_(self, *args, **kwargs):
                return self
            def not_(self, *args, **kwargs):
                return self
            def is_(self, *args, **kwargs):
                return self
            def or_(self, *args, **kwargs):
                return self
            def execute(self):
                # Return empty so in-memory store handles separation deterministically
                res = MockResult()
                res.data = []
                return res

        class MockSupabase:
            def table(self, tbl):
                return MockQuery(tbl)
            def rpc(self, *args, **kwargs):
                return MockQuery("rpc")

        monkeypatch.setattr("main.supabase", MockSupabase())

        # ── Step 1: Agent A sends to Client X ──
        res1 = self.client.post("/api/whatsapp/send_message", json={
            "to_number": test_phone,
            "message": "Agent A -> Client X: unit specs attached",
            "agent_id": agent_a_id,
            "client_id": client_x_id,
            "client_name": "Client X",
        })
        assert res1.status_code == 200, res1.text

        # ── Step 2: Agent B sends to Client Y on same phone number ──
        res2 = self.client.post("/api/whatsapp/send_message", json={
            "to_number": test_phone,
            "message": "Agent B -> Client Y: pricing overview",
            "agent_id": agent_b_id,
            "client_id": client_y_id,
            "client_name": "Client Y",
        })
        assert res2.status_code == 200, res2.text

        # ── Step 3: Inbound webhook reply ──
        wamid = f"wamid.test_{uuid.uuid4()}"
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Test Prospect"}}],
                        "messages": [{
                            "id": wamid,
                            "from": test_phone,
                            "type": "text",
                            "text": {"body": "Thanks, can we schedule a demo?"},
                        }],
                    }
                }]
            }]
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = compute_sig(raw_body, self.app_secret)

        wh1 = self.client.post(
            "/api/whatsapp/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        assert wh1.status_code == 200

        # ── Step 4: Idempotency check — same wamid retried by Meta ──
        wh2 = self.client.post(
            "/api/whatsapp/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        assert wh2.status_code == 200

        # Confirm exactly 1 instance of wamid in message history
        matching_wamids = [m for m in WHATSAPP_MESSAGE_HISTORY if m.get("id") == wamid]
        assert len(matching_wamids) == 1, f"Expected 1 message for wamid, found {len(matching_wamids)}"

        # ── Step 5: Query messages for Agent A / Client X ──
        msgs_a = self.client.get("/api/whatsapp/messages", params={
            "to_number": test_phone,
            "agent_id": agent_a_id,
            "client_id": client_x_id,
        }).json().get("messages", [])

        # ── Step 6: Query messages for Agent B / Client Y ──
        msgs_b = self.client.get("/api/whatsapp/messages", params={
            "to_number": test_phone,
            "agent_id": agent_b_id,
            "client_id": client_y_id,
        }).json().get("messages", [])

        # Assertions
        a_texts = [m["text"] for m in msgs_a]
        b_texts = [m["text"] for m in msgs_b]

        assert any("Client X" in t for t in a_texts), f"Agent A must see Client X messages: {a_texts}"
        assert not any("Client Y" in t for t in a_texts), f"Agent A must NOT see Client Y messages: {a_texts}"

        assert any("Client Y" in t for t in b_texts), f"Agent B must see Client Y messages: {b_texts}"
        assert not any("Client X" in t for t in b_texts), f"Agent B must NOT see Client X messages: {b_texts}"
