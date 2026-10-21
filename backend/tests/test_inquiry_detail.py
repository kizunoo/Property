import sys
import types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copilot_tools as ct
import inquiry_detail as idt
from copilot_tools import Identity

C1, C2 = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
I1, I2, MISSING = ("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                   "cccccccc-cccc-4ccc-8ccc-cccccccccccc")


class Q:
    def __init__(self, rows): self.rows, self.f, self.n, self.o = rows, [], None, None
    def select(self, *a, **k): return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self
    def ilike(self, c, p): self.f.append(lambda r: p.strip("%").lower() in str(r.get(c) or "").lower()); return self
    def order(self, c, desc=False): self.o = (c, desc); return self
    def limit(self, n): self.n = n; return self
    def execute(self):
        rows = [r for r in self.rows if all(f(r) for f in self.f)]
        if self.o: rows.sort(key=lambda r: str(r.get(self.o[0]) or ""), reverse=self.o[1])
        return types.SimpleNamespace(data=rows[: self.n] if self.n else rows)


class DB:
    def __init__(self, t): self.t = t
    def table(self, n): return Q(list(self.t.get(n, [])))


def make():
    return DB({
        "clients": [{"id": C1, "name": "Alpha Sdn Bhd", ct.CLIENT_AGENT_COL: "repA"},
                    {"id": C2, "name": "Beta Bhd", ct.CLIENT_AGENT_COL: "repB"}],
        "client_inquiries": [
            {"id": I1, "client_id": C1, ct.INQUIRY_TEXT_COL: "Is it safe?\x00\x07 Need info",
             "status": "open", "created_at": "2026-10-20T01:00:00+00:00", "triage_priority": "high",
             "triage_category": "complaint_issue", "triage_reasons": ["Problem or safety concern"],
             "triage_summary": "Asks about safety", "triage_status": "ai",
             "roi_scenario": {"secret": "do not leak"}, "agent_reply": "internal"},
            {"id": I2, "client_id": C2, ct.INQUIRY_TEXT_COL: "other rep", "status": "open"},
        ],
        "inquiry_messages": [
            {"inquiry_id": I1, "sender": "client", "body": "Is it safe?\x00\x07 Need info", "created_at": "2026-10-20T01:00:01+00:00"},
            {"inquiry_id": I1, "sender": "rep", "body": "Yes, details attached.", "created_at": "2026-10-20T02:00:00+00:00"},
            {"inquiry_id": I1, "sender": "client", "body": "Thanks!", "created_at": "2026-10-20T03:00:00+00:00"},
            {"inquiry_id": I2, "sender": "client", "body": "x", "created_at": "2026-10-20T01:00:00+00:00"},
        ],
    })


REP_A, ADMIN = Identity("repA", False), Identity("adm", True)


def test_rep_sees_own_inquiry_with_thread_in_order():
    r = idt.get_inquiry_detail(make(), REP_A, I1)
    assert r["inquiry"]["company"] == "Alpha Sdn Bhd" and r["inquiry"]["priority"] == "high"
    assert [m["sender"] for m in r["messages"]] == ["rep", "company"]   # first repeated message dropped
    assert r["original_message"] == "Is it safe? Need info"

def test_control_characters_removed():
    r = idt.get_inquiry_detail(make(), REP_A, I1)
    assert "\x00" not in r["original_message"] and "\x07" not in r["original_message"]

def test_other_reps_inquiry_and_missing_look_identical():
    db = make()
    assert idt.get_inquiry_detail(db, REP_A, I2) is None
    assert idt.get_inquiry_detail(db, REP_A, MISSING) is None

def test_admin_sees_any():
    assert idt.get_inquiry_detail(make(), ADMIN, I2) is not None

def test_invalid_id_rejected():
    assert idt.get_inquiry_detail(make(), ADMIN, "priority") is None
    assert idt.get_inquiry_detail(make(), ADMIN, "' or 1=1 --") is None

def test_internal_columns_never_returned():
    blob = str(idt.get_inquiry_detail(make(), REP_A, I1))
    assert "do not leak" not in blob and "internal" not in blob
