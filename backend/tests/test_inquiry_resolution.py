import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copilot_tools as ct
import inquiry_resolution as ir
from copilot_tools import Identity

C1, C2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
I1, I2, I3 = ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              "dddddddd-dddd-4ddd-8ddd-dddddddddddd")
MISSING = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


class Q:
    def __init__(self, t): self.t, self.f, self.n, self.o, self.upd = t, [], None, None, None
    def select(self, *a, **k): return self
    def update(self, v): self.upd = v; return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.f.append(lambda r: r.get(c) in vs); return self
    def is_(self, c, v): self.f.append(lambda r: (r.get(c) is None) if v == "null" else r.get(c) == v); return self
    def ilike(self, c, p): self.f.append(lambda r: p.strip("%").lower() in str(r.get(c) or "").lower()); return self
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
    def __init__(self, t): self.t = t
    def table(self, n): return Q(self.t.setdefault(n, []))


def make():
    return DB({
        "clients": [{"id": C1, "name": "Alpha Sdn Bhd", ct.CLIENT_AGENT_COL: "repA"},
                    {"id": C2, "name": "Beta Bhd", ct.CLIENT_AGENT_COL: "repB"}],
        "client_inquiries": [
            {"id": I1, "client_id": C1, "created_at": "2026-10-20T01:00:00+00:00", "triage_priority": "high",
             "triage_category": "pricing_quote", "triage_summary": "asks price", "resolved_at": None},
            {"id": I3, "client_id": C1, "created_at": "2026-10-19T01:00:00+00:00", "triage_priority": "normal",
             "triage_category": "technical_question", "triage_summary": "asks weight",
             "resolved_at": "2026-10-19T05:00:00+00:00", "resolved_by": "repA", "resolution_note": "Sent datasheet"},
            {"id": I2, "client_id": C2, "created_at": "2026-10-20T01:00:00+00:00", "resolved_at": None},
        ],
        "inquiry_messages": [
            {"inquiry_id": I1, "sender": "rep", "body": "hi"}, {"inquiry_id": I1, "sender": "client", "body": "x"},
            {"inquiry_id": I3, "sender": "rep", "body": "a"}, {"inquiry_id": I3, "sender": "rep", "body": "b"},
        ],
        "agent_accounts": [{"id": "repA", "name": "S. Yusof"}],
    })


REP_A, ADMIN = Identity("repA", False), Identity("adm", True)


def test_resolve_marks_resolved_with_note_and_actor():
    db = make()
    assert ir.resolve_inquiry(db, REP_A, I1, "  Answered by phone \x00 ") == "ok"
    r = next(x for x in db.t["client_inquiries"] if x["id"] == I1)
    assert r["resolved_at"] and r["resolved_by"] == "repA" and r["resolution_note"] == "Answered by phone"

def test_double_resolve_is_refused():
    db = make()
    assert ir.resolve_inquiry(db, REP_A, I1) == "ok"
    assert ir.resolve_inquiry(db, REP_A, I1) == "already_resolved"

def test_cannot_resolve_other_reps_or_missing_or_invalid():
    db = make()
    assert ir.resolve_inquiry(db, REP_A, I2) == "not_found"
    assert ir.resolve_inquiry(db, REP_A, MISSING) == "not_found"
    assert ir.resolve_inquiry(db, REP_A, "x' or 1=1") == "not_found"
    assert next(x for x in db.t["client_inquiries"] if x["id"] == I2)["resolved_at"] is None

def test_note_is_capped():
    db = make()
    ir.resolve_inquiry(db, REP_A, I1, "n" * 900)
    assert len(next(x for x in db.t["client_inquiries"] if x["id"] == I1)["resolution_note"]) == 500

def test_reopen_only_when_resolved():
    db = make()
    assert ir.reopen_inquiry(db, REP_A, I1) == "not_resolved"
    assert ir.reopen_inquiry(db, REP_A, I3) == "ok"
    r = next(x for x in db.t["client_inquiries"] if x["id"] == I3)
    assert r["resolved_at"] is None and r["resolution_note"] is None
    assert ir.reopen_inquiry(db, REP_A, I2) == "not_found"

def test_history_lists_open_and_resolved_newest_first_with_reply_counts():
    h = ir.list_company_history(make(), REP_A, C1)
    assert h["company"] == "Alpha Sdn Bhd"
    assert [i["inquiry_id"] for i in h["inquiries"]] == [I1, I3]
    open_row, done_row = h["inquiries"]
    assert open_row["state"] == "open" and open_row["replies"] == 1
    assert done_row["state"] == "resolved" and done_row["replies"] == 2
    assert done_row["resolved_by"] == "S. Yusof" and done_row["resolution_note"] == "Sent datasheet"

def test_history_scoped_to_own_clients():
    db = make()
    assert ir.list_company_history(db, REP_A, C2) is None
    assert ir.list_company_history(db, REP_A, MISSING) is None
    assert ir.list_company_history(db, REP_A, "not-a-uuid") is None
    assert ir.list_company_history(db, ADMIN, C2) is not None

def test_history_never_returns_internal_columns():
    db = make()
    db.t["client_inquiries"][0]["roi_scenario"] = {"secret": "leak"}
    db.t["client_inquiries"][0]["agent_reply"] = "internal"
    assert "leak" not in str(ir.list_company_history(db, REP_A, C1)) and "internal" not in str(ir.list_company_history(db, REP_A, C1))
