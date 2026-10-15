# backend/tests/test_facility_profile.py
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


class TestFacilityProfile:
    def setup_method(self):
        os.environ["PORTAL_CODE_PEPPER"] = "test-pepper-1234567890123456789012"
        self.client_id = str(uuid.uuid4())
        self.other_client_id = str(uuid.uuid4())

        self.mock_session = PortalSession(
            session_id="test-session-id",
            client_id=self.client_id,
            contact_id="test-contact-id",
            contact_name="Deployment Lead",
            portal_role="evaluator",
            client_name="OmniCorp Logistics",
            is_legacy=False,
        )

        app.dependency_overrides[get_current_portal_session] = lambda: self.mock_session

    def teardown_method(self):
        app.dependency_overrides.clear()

    @patch("main.supabase")
    def test_get_preferences_returns_facility_profile(self, mock_supabase):
        mock_client_table = MagicMock()
        mock_client_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": self.client_id,
            "name": "OmniCorp Logistics",
            "stated_budget": 500000,
            "facility_profile": {
                "facility_type": "warehouse",
                "floor_area_sqm": 25000,
                "primary_use_case": "pallet_transport",
                "timeline": "3_6_months",
                "budget_band": "250k_500k",
            },
        }
        mock_supabase.table.return_value = mock_client_table

        response = client.get(f"/api/portal/{self.client_id}/preferences")
        assert response.status_code == 200
        data = response.json()
        assert "facility_profile" in data
        assert data["facility_profile"]["facility_type"] == "warehouse"
        assert data["facility_profile"]["floor_area_sqm"] == 25000

    @patch("main.check_portal_write_rate_limit")
    @patch("main.supabase")
    def test_patch_facility_profile_merges_audits_and_emits_signal(self, mock_supabase, mock_rate_limit):
        initial_client = {
            "id": self.client_id,
            "name": "OmniCorp Logistics",
            "facility_profile": {
                "facility_type": "warehouse",
                "floor_area_sqm": 20000,
            },
        }

        mock_client_table = MagicMock()
        mock_client_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = initial_client
        mock_client_table.update.return_value.eq.return_value.execute.return_value.data = [{}]

        audit_inserts = []
        mock_audit_table = MagicMock()
        mock_audit_table.insert.side_effect = lambda payload: (audit_inserts.append(payload), MagicMock(execute=lambda: MagicMock(data=[payload])))[1]

        signal_inserts = []
        mock_signal_table = MagicMock()
        mock_signal_table.insert.side_effect = lambda payload: (signal_inserts.append(payload), MagicMock(execute=lambda: MagicMock(data=[payload])))[1]

        def table_router(table_name):
            if table_name == "clients":
                return mock_client_table
            if table_name == "portal_profile_audit":
                return mock_audit_table
            if table_name == "signals":
                return mock_signal_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        patch_body = {
            "facility_profile": {
                "floor_area_sqm": 35000,
                "primary_use_case": "palletizing",
                "timeline": "0-3m",
            }
        }

        response = client.patch(f"/api/portal/{self.client_id}/preferences", json=patch_body)
        assert response.status_code == 200

        # Check client update was called with merged facility_profile
        update_calls = mock_client_table.update.call_args_list
        assert len(update_calls) > 0
        updated_data = update_calls[0][0][0]
        assert "facility_profile" in updated_data
        assert updated_data["facility_profile"]["facility_type"] == "warehouse"  # Preserved from initial
        assert updated_data["facility_profile"]["floor_area_sqm"] == 35000       # Updated
        assert updated_data["facility_profile"]["primary_use_case"] == "palletizing"  # Added
        assert updated_data["facility_profile"]["timeline"] == "0-3m"       # Added

        # Check audit rows
        audit_fields = [row["field"] for row in audit_inserts]
        assert "facility_profile.floor_area_sqm" in audit_fields
        assert "facility_profile.primary_use_case" in audit_fields
        assert "facility_profile.timeline" in audit_fields

        # Check rep signal
        assert len(signal_inserts) == 1
        assert signal_inserts[0]["type"] == "portal_profile_updated"
        assert signal_inserts[0]["client_id"] == self.client_id
        assert "OmniCorp Logistics updated deployment specs" in signal_inserts[0]["message"]

    @patch("main.check_portal_write_rate_limit")
    @patch("main.supabase")
    def test_patch_facility_profile_invalid_enum_rejected(self, mock_supabase, mock_rate_limit):
        mock_client_table = MagicMock()
        mock_client_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": self.client_id,
            "name": "OmniCorp Logistics",
        }
        mock_supabase.table.return_value = mock_client_table

        patch_body = {
            "facility_profile": {
                "facility_type": "space_station",  # Invalid enum
            }
        }

        response = client.patch(f"/api/portal/{self.client_id}/preferences", json=patch_body)
        assert response.status_code == 422

    @patch("main.check_portal_write_rate_limit")
    @patch("main.supabase")
    def test_patch_facility_profile_unknown_field_rejected(self, mock_supabase, mock_rate_limit):
        mock_client_table = MagicMock()
        mock_client_table.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "id": self.client_id,
            "name": "OmniCorp Logistics",
        }
        mock_supabase.table.return_value = mock_client_table

        patch_body = {
            "facility_profile": {
                "unauthorized_secret_key": "val",
            }
        }

        response = client.patch(f"/api/portal/{self.client_id}/preferences", json=patch_body)
        assert response.status_code == 422

    def test_patch_other_client_forbidden(self):
        response = client.patch(f"/api/portal/{self.other_client_id}/preferences", json={})
        assert response.status_code == 403
