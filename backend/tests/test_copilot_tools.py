import sys, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copilot_tools as ct
from copilot_tools import Identity


class Q:
    def __init__(self, rows):
        self.rows, self.f, self.n, self.o = rows, [], None, None
    def select(self, *a, **k): return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.f.append(lambda r: r.get(c) in vs); return self
    def order(self, c, desc=False): self.o = (c, desc); return self
    def limit(self, n): self.n = n; return self
    def execute(self):
        rows = [r for r in self.rows if all(f(r) for f in self.f)]
        if self.o: rows.sort(key=lambda r: r.get(self.o[0]) or 0, reverse=self.o[1])
        return types.SimpleNamespace(data=rows[: self.n] if self.n else rows)


class DB:
    def __init__(self, t): self.t = t
    def table(self, n): return Q(list(self.t.get(n, [])))


def make_db():
    return DB({
        "clients": [
            {"id": "c1", "name": "Alpha", "assigned_agent_id": "repA", "facility_profile": {"facility_type": "warehouse"}},
            {"id": "c2", "name": "Beta", "assigned_agent_id": "repB"},
        ],
        "pipeline_evaluations": [
            {"client_id": "c1", "expected_value": 5, "segment_tier": "A"},
            {"client_id": "c2", "expected_value": 9, "segment_tier": "A"},
        ],
        "client_inquiries": [{"client_id": "c1", "status": "open", "message": "x" * 900}],
        "properties": [{"name": "R1", "manufacturer": "M", "specs": {}, "price": None, "data_source": "real"},
                       {"name": "Dummy", "data_source": "seed"}],
    })

REP_A, ADMIN = Identity("repA", False), Identity("adm", True)


def test_rep_only_sees_own_clients():
    r = ct.list_priority_clients(make_db(), REP_A)
    assert [c["client_id"] for c in r["clients"]] == ["c1"]

def test_admin_sees_all_sorted():
    r = ct.list_priority_clients(make_db(), ADMIN)
    assert [c["client_id"] for c in r["clients"]] == ["c2", "c1"]

def test_rep_cannot_read_other_reps_client():
    assert "error" in ct.get_client_brief(make_db(), REP_A, "c2")
    assert "error" in ct.suggest_robot_matches(make_db(), REP_A, "c2")

def test_untrusted_text_is_clipped_and_labelled():
    r = ct.get_client_brief(make_db(), REP_A, "c1")
    assert len(r["recent_inquiries"][0]["untrusted_text"]) == ct.MAX_TEXT
    assert "untrusted" in r["note"].lower()

def test_only_real_robots_listed():
    r = ct.suggest_robot_matches(make_db(), REP_A, "c1")
    assert [x["name"] for x in r["catalog"]] == ["R1"]

def test_no_tool_accepts_an_identity_argument():
    import inspect
    for fn in (ct.list_priority_clients, ct.get_client_brief, ct.suggest_robot_matches):
        assert list(inspect.signature(fn).parameters)[:2] == ["db", "identity"]
