# backend/tests/test_roi_endpoint.py
import os
import sys
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ["PORTAL_CODE_PEPPER"] = "test-pepper-1234567890123456789012"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from portal_auth import PortalSession, get_current_portal_session

client = TestClient(app)

class TestRoiInquiryEndpoint:
    def setup_method(self):
        os.environ["PORTAL_CODE_PEPPER"] = "test-pepper-1234567890123456789012"
        self.client_id = str(uuid.uuid4())
        self.other_client_id = str(uuid.uuid4())
        self.property_id = str(uuid.uuid4())
        
        self.mock_session = PortalSession(
            session_id="test-session-id",
            client_id=self.client_id,
            contact_id="test-contact-id",
            contact_name="Test Evaluator",
            portal_role="evaluator",
            client_name="Acme Robotics Co",
            is_legacy=False,
        )

        app.dependency_overrides[get_current_portal_session] = lambda: self.mock_session

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.check_portal_write_rate_limit")
    @patch("main.supabase")
    def test_save_roi_scenario_recomputes_server_side(self, mock_supabase, mock_rate_limit):
        # Mock client lookup
        mock_client_table = MagicMock()
        mock_client_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": self.client_id,
            "name": "Acme Robotics Co",
            "assigned_agent_id": "agent-1",
        }

        # Mock property lookup
        mock_prop_table = MagicMock()
        mock_prop_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": self.property_id,
            "property_value": 100000,
            "specs": {"lease_monthly": 3500},
            "address": "Unit Alpha 500",
        }

        # Mock insert into client_inquiries
        mock_inq_table = MagicMock()
        mock_inq_table.insert.return_value.execute.return_value.data = [{
            "id": "inq-123",
            "created_at": "2026-10-16T12:00:00Z",
        }]

        # Mock messages insert
        mock_msg_table = MagicMock()
        mock_msg_table.insert.return_value.execute.return_value.data = [{}]

        # Mock signals insert
        mock_sig_table = MagicMock()
        mock_sig_table.insert.return_value.execute.return_value.data = [{}]

        def table_router(name):
            if name == "clients":
                return mock_client_table
            elif name == "properties":
                return mock_prop_table
            elif name == "client_inquiries":
                return mock_inq_table
            elif name == "inquiry_messages":
                return mock_msg_table
            elif name == "signals":
                return mock_sig_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        # Client sends tampered/fake outputs
        payload = {
            "property_id": self.property_id,
            "roi_scenario": {
                "shifts": 2,
                "headcountPerShift": 3,
                "monthlyLaborCost": 5000,
                "mode": "purchase",
                # Client attempts to spoof high savings
                "fakeMonthlySavings": 999999999,
            },
        }

        res = client.post(
            f"/api/portal/{self.client_id}/inquiry",
            json=payload,
        )

        assert res.status_code == 200, res.text
        data = res.json()
        assert "roi_scenario" in data
        roi = data["roi_scenario"]
        # Expected math: 2 * 3 * 5000 = 30000 monthly savings
        assert roi["outputs"]["monthlySavings"] == 30000
        assert roi["outputs"]["netMonthly"] == 30000
        # Payback = 100000 / 30000 = 3.333...
        assert roi["outputs"]["paybackMonths"] == pytest.approx(100000 / 30000, rel=1e-2)

        # Confirm stored call in client_inquiries includes roi_scenario
        inq_call_args = mock_inq_table.insert.call_args[0][0]
        assert "roi_scenario" in inq_call_args
        assert inq_call_args["roi_scenario"]["outputs"]["monthlySavings"] == 30000

        # Assert zero EV/ML leak
        assert "expected_value" not in data
        assert "ml_probability" not in data
        assert "ai_probability" not in data

        # Confirm signal created
        sig_call_args = mock_sig_table.insert.call_args[0][0]
        assert sig_call_args["type"] == "portal_inquiry"
        assert "RM 30,000/mo savings" in sig_call_args["message"]

    @patch("main.check_portal_write_rate_limit")
    @patch("main.supabase")
    def test_save_roi_scenario_invalid_bounds(self, mock_supabase, mock_rate_limit):
        # Shifts > 3 violates bounds
        payload = {
            "property_id": self.property_id,
            "roi_scenario": {
                "shifts": 5,
                "headcountPerShift": 2,
                "monthlyLaborCost": 4000,
                "mode": "purchase",
            },
        }
        res = client.post(
            f"/api/portal/{self.client_id}/inquiry",
            json=payload,
        )
        assert res.status_code == 422
        assert "Invalid ROI scenario inputs" in res.text

    @patch("main.supabase")
    def test_cross_company_isolation(self, mock_supabase):
        # Session for client_id attempting to write to other_client_id
        payload = {
            "property_id": self.property_id,
            "message": "Hello",
        }
        res = client.post(
            f"/api/portal/{self.other_client_id}/inquiry",
            json=payload,
        )
        assert res.status_code == 403
