import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import triage_service as ts
from copilot_tools import Identity
from triage_rules import AiTriage


class Q:
    def __init__(self, table):
        self.t, self.f, self.n, self.o, self.upd = table, [], None, None, None
    def select(self, *a, **k): return self
    def update(self, vals): self.upd = vals; return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.f.append(lambda r: r.get(c) in vs); return self
    def order(self, c, desc=False): self.o = (c, desc); return self
    def limit(self, n): self.n = n; return self
    def execute(self):
        rows = [r for r in self.t if all(f(r) for f in self.f)]
        if self.upd is not None:
            for r in rows: r.update(self.upd)
            return types.SimpleNamespace(data=[dict(r) for r in rows])
        if self.o: rows.sort(key=lambda r: str(r.get(self.o[0]) or ""), reverse=self.o[1])
        rows = rows[: self.n] if self.n else rows
        return types.SimpleNamespace(data=[dict(r) for r in rows])


class DB:
    def __init__(self, tables): self.t = tables
    def table(self, n): return Q(self.t.setdefault(n, []))


def iso(**kw): return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def make():
    db = DB({
        "clients": [{"id": "c1", "name": "Alpha Sdn Bhd", "assigned_agent_id": "repA"},
                    {"id": "c2", "name": "Beta", "assigned_agent_id": "repB"}],
        "client_inquiries": [
            {"id": "i1", "client_id": "c1", "status": "open", "created_at": iso(minutes=1),
             "triage_alerted": False, "triage_status": "rules"},
        ],
        "portal_quotes": [], "scheduled_viewings": [],
    })
    ts.set_db(db)
    ts.set_ai_runner(None)
    alerts = []
    ts.set_signal_hook(lambda cid, title, body, prio: alerts.append((cid, title, body, prio)))
    return db, alerts


def row(db, iid="i1"): return next(r for r in db.t["client_inquiries"] if r["id"] == iid)


def test_rules_label_is_immediate_and_alerts_rep_once():
    db, alerts = make()
    ts.set_ai_runner(lambda cid, text: None)
    ts.triage_new_inquiry(db, "c1", "i1", "How much is the AMR? Need a quote ASAP", background=False)
    r = row(db)
    assert r["triage_priority"] == "urgent" and r["triage_category"] == "pricing_quote"
    assert len(alerts) == 1 and alerts[0][3] == "urgent" and "Alpha" in alerts[0][2]
    assert r["triage_status"] == "failed"      # AI returned nothing: rules label stands

def test_ai_failure_never_breaks_and_keeps_rules_label():
    db, alerts = make()
    def boom(cid, text): raise RuntimeError("model down")
    ts.set_ai_runner(boom)
    ts.triage_new_inquiry(db, "c1", "i1", "Can we book a demo?", background=False)
    r = row(db)
    assert r["triage_priority"] == "high" and r["triage_status"] == "failed"

def test_ai_can_escalate_but_not_lower():
    db, alerts = make()
    ts.set_ai_runner(lambda cid, text: AiTriage("complaint_issue", True, "Robot stopped, go-live Friday"))
    ts.triage_new_inquiry(db, "c1", "i1", "hello we have a situation", background=False)
    assert row(db)["triage_priority"] == "urgent" and row(db)["triage_status"] == "ai"
    db2, _ = make()
    ts.set_ai_runner(lambda cid, text: AiTriage("unclear", False, "Spam"))
    ts.triage_new_inquiry(db2, "c1", "i1", "Need a quote ASAP please", background=False)
    assert row(db2)["triage_priority"] == "urgent"     # injected "low/spam" cannot downgrade

def test_no_duplicate_alert_when_ai_confirms_same_priority():
    db, alerts = make()
    ts.set_ai_runner(lambda cid, text: AiTriage("pricing_quote", False, "Asks price"))
    ts.triage_new_inquiry(db, "c1", "i1", "What is the price?", background=False)
    assert len(alerts) == 1

def test_alert_failure_resets_claim():
    db, _ = make()
    def bad_hook(*a): raise RuntimeError("signals down")
    ts.set_signal_hook(bad_hook)
    ts.set_ai_runner(lambda cid, text: None)
    ts.triage_new_inquiry(db, "c1", "i1", "Need a demo", background=False)
    assert row(db)["triage_alerted"] is False

def test_facts_raise_priority():
    db, _ = make()
    db.t["portal_quotes"].append({"client_id": "c1", "status": "sent"})
    db.t["client_inquiries"].append({"id": "old", "client_id": "c1", "status": "open",
                                     "created_at": iso(days=3)})
    ts.set_ai_runner(lambda cid, text: None)
    ts.triage_new_inquiry(db, "c1", "i1", "What is the price?", background=False)
    r = row(db)
    assert r["triage_priority"] == "urgent"
    assert "Has an open quote" in r["triage_reasons"]

def test_ai_budget_caps_runs_per_client():
    db, _ = make()
    for k in range(ts.MAX_AI_PER_CLIENT_PER_HOUR):
        db.t["client_inquiries"].append({"id": f"x{k}", "client_id": "c1", "status": "open",
                                         "triage_status": "ai", "triaged_at": iso(minutes=5)})
    called = []
    ts.set_ai_runner(lambda cid, text: called.append(1))
    ts.triage_new_inquiry(db, "c1", "i1", "What is the price?", background=False)
    assert called == [] and row(db)["triage_status"] == "rules"

def test_list_is_scoped_sorted_and_hides_message_text():
    db, _ = make()
    db.t["client_inquiries"] = [
        {"id": "a", "client_id": "c1", "status": "open", "created_at": iso(hours=2),
         "triage_priority": "normal", "triage_summary": "s", "triage_reasons": []},
        {"id": "b", "client_id": "c1", "status": "open", "created_at": iso(hours=1),
         "triage_priority": "urgent", "triage_summary": "s", "triage_reasons": ["x"]},
        {"id": "c", "client_id": "c2", "status": "open", "created_at": iso(hours=1),
         "triage_priority": "urgent", "triage_summary": "other rep", "triage_reasons": []},
        {"id": "d", "client_id": "c1", "status": "closed", "created_at": iso(hours=1),
         "triage_priority": "urgent", "triage_summary": "closed", "triage_reasons": []},
        {"id": "e", "client_id": "c1", "status": "open", "created_at": iso(hours=1),
         "triage_priority": None, "message": "SECRET FULL TEXT"},
    ]
    rep = ts.list_priority_inquiries(db, Identity("repA", False))
    assert [r["inquiry_id"] for r in rep] == ["b", "a"]
    assert all("message" not in r for r in rep)
    admin = ts.list_priority_inquiries(db, Identity("adm", True))
    assert {r["inquiry_id"] for r in admin} == {"a", "b", "c"}
    assert ts.list_priority_inquiries(db, Identity("nobody", False)) == []
