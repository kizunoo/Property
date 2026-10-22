import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copilot_tools as ct
import reply_context as rc
from copilot_tools import Identity
from test_inquiry_resolution import DB, I1, C1, C2, REP_A, ADMIN

P1, P2, P3 = "p1", "p2", "p3"


def make():
    db = DB({
        "clients": [{"id": C1, "name": "Alpha Sdn Bhd", ct.CLIENT_AGENT_COL: "repA",
                     "facility_profile": {"facility_type": "warehouse"}, "stated_budget": 310000,
                     "agent_notes": "INTERNAL NOTE"},
                    {"id": C2, "name": "Beta", ct.CLIENT_AGENT_COL: "repB"}],
        "client_inquiries": [{"id": I1, "client_id": C1, ct.INQUIRY_TEXT_COL: "What is the weight of the AMR-4000?",
                              "status": "open", "created_at": "2026-10-20T01:00:00+00:00"}],
        "inquiry_messages": [],
        ct.ROBOT_TABLE: [
            {"id": P1, ct.ROBOT_NAME_COL: "AMR-4000 Heavy-Lift Pallet Jack", "manufacturer": "Acme",
             ct.ROBOT_PRICE_COL: 237207, "data_source": "seed",
             "specs": {"payload_kg": 1500, "weight_kg": 480},
             "owner_client_id": "SECRET-OWNER", "assigned_agent_id": "SECRET-AGENT"},
            {"id": P2, ct.ROBOT_NAME_COL: "ScrubBot S5", "manufacturer": "CleanCo", ct.ROBOT_PRICE_COL: 85000,
             "data_source": "real", "specs": {"battery_hours": 4}},
            {"id": P3, ct.ROBOT_NAME_COL: "Lifter L9", "data_source": "real"},
        ],
        ct.EVAL_TABLE: [{ct.EVAL_CLIENT_COL: C1, rc.EVAL_PROPERTY_COL: P2, ct.EV_COL: 5}],
    })
    return db


def test_named_product_first_then_best_fit():
    ctx = rc.build_context(make(), REP_A, I1)
    names = [p["name"] for p in ctx["candidate_products"]]
    assert names == ["AMR-4000 Heavy-Lift Pallet Jack", "ScrubBot S5"]
    assert ctx["candidate_products"][0]["why_relevant"].startswith("named")

def test_weight_and_payload_are_separate_labelled_facts():
    sheet = rc.build_context(make(), REP_A, I1)["candidate_products"][0]
    facts = {f["label"]: f["value"] for f in sheet["facts"]}
    assert facts["Robot weight (kg)"] == "480" and facts["Payload capacity (kg)"] == "1500"
    assert facts["Unit cost (RM)"] == "237207"

def test_demo_source_is_flagged():
    sheets = rc.build_context(make(), REP_A, I1)["candidate_products"]
    assert sheets[0]["source"].startswith("demo") and sheets[1]["source"] == "catalog"

def test_context_never_contains_internal_data():
    blob = str(rc.build_context(make(), REP_A, I1))
    for secret in ("SECRET-OWNER", "SECRET-AGENT", "INTERNAL NOTE", "310000", "expected_value"):
        assert secret not in blob

def test_context_scoped_to_own_clients():
    db = make()
    db.t["client_inquiries"][0]["client_id"] = C2
    assert rc.build_context(db, REP_A, I1) is None
    assert rc.build_context(db, ADMIN, I1) is not None

def test_find_products_sanitises_wildcards_and_searches():
    db = make()
    assert rc.find_products(db, "%") == [] and rc.find_products(db, "_") == []
    assert [s["name"] for s in rc.find_products(db, "scrub")] == ["ScrubBot S5"]

def test_missing_weight_is_visible_by_absence():
    sheets = rc.build_context(make(), REP_A, I1)["candidate_products"]
    assert "Robot weight (kg)" not in [f["label"] for f in sheets[1]["facts"]]

def test_parse_suggestion():
    raw = 'ok ```json\n{"draft":"The AMR-4000 weighs 480 kg.","product":"AMR-4000 Heavy-Lift Pallet Jack","facts_used":[{"label":"Robot weight (kg)","value":"480"}],"missing":["Robot height"]}\n```'
    p = rc.parse_suggestion(raw)
    assert p["draft"].startswith("The AMR") and p["missing"] == ["Robot height"]
    for bad in (None, "", "no json", '{"draft": ""}', '{"x": 1}', '[1]'):
        assert rc.parse_suggestion(bad) is None

def _final(draft, facts_used, product="AMR-4000 Heavy-Lift Pallet Jack", missing=()):
    ctx = rc.build_context(make(), REP_A, I1)
    parsed = {"draft": draft, "product": product, "facts_used": facts_used, "missing": list(missing)}
    return rc.finalize_suggestion(parsed, ctx["candidate_products"], ctx["conversation"], ctx["company"])

def test_grounded_draft_has_no_warnings():
    out = _final("The AMR-4000 weighs 480 kg.", [{"label": "Robot weight (kg)", "value": "480"}])
    assert out["warnings"] == [] and len(out["facts_used"]) == 1 and out["uses_demo_data"] is True

def test_invented_number_is_flagged():
    out = _final("The AMR-4000 weighs 520 kg.", [{"label": "Robot weight (kg)", "value": "520"}])
    assert any("520" in w for w in out["warnings"])
    assert out["facts_used"] == []            # unverifiable fact removed

def test_promised_timeframe_is_flagged_because_it_is_not_in_the_data():
    out = _final("We can deliver within 14 days.", [])
    assert any("14" in w for w in out["warnings"])

def test_real_product_not_marked_demo():
    out = _final("The ScrubBot runs 4 hours.", [{"label": "Battery life (hours)", "value": "4"}], product="ScrubBot S5")
    assert out["uses_demo_data"] is False and out["warnings"] == []

def test_missing_details_pass_through():
    out = _final("I will confirm the height and revert.", [], missing=["Robot height"])
    assert out["missing"] == ["Robot height"]
