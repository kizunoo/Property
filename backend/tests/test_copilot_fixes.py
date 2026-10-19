"""Regression tests for the copilot fixes. Own fake DB (supports ilike), no network."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copilot_tools as ct
from copilot_tools import Identity


class Q:
    def __init__(self, rows):
        self.rows, self.f, self.n = rows, [], None
    def select(self, *a, **k): return self
    def eq(self, c, v): self.f.append(lambda r: r.get(c) == v); return self
    def in_(self, c, vs): self.f.append(lambda r: r.get(c) in vs); return self
    def ilike(self, c, pat):
        needle = pat.strip("%").lower()
        self.f.append(lambda r: needle in str(r.get(c) or "").lower()); return self
    def order(self, *a, **k): return self
    def limit(self, n): self.n = n; return self
    def execute(self):
        rows = [r for r in self.rows if all(f(r) for f in self.f)]
        return types.SimpleNamespace(data=rows[: self.n] if self.n else rows)


class DB:
    def __init__(self, tables): self.t = tables
    def table(self, n): return Q(list(self.t.get(n, [])))


REP = Identity("repA", False)


def client(cid, name, agent="repA"):
    return {"id": cid, ct.CLIENT_NAME_COL: name, ct.CLIENT_AGENT_COL: agent, "facility_profile": {}}


def test_seed_only_robots_are_never_listed_as_catalog():
    db = DB({ct.CLIENT_TABLE: [client("c1", "Alpha")],
             ct.ROBOT_TABLE: [{ct.ROBOT_NAME_COL: "Dummy AMR", "data_source": "seed"}]})
    out = ct.suggest_robot_matches(db, REP, None)
    assert out["catalog"] == []

def test_real_robots_are_listed():
    db = DB({ct.CLIENT_TABLE: [client("c1", "Alpha")],
             ct.ROBOT_TABLE: [{ct.ROBOT_NAME_COL: "Real AMR", "manufacturer": "M", "data_source": "real"},
                              {ct.ROBOT_NAME_COL: "Dummy", "data_source": "seed"}]})
    out = ct.suggest_robot_matches(db, REP, None)
    assert [r["name"] for r in out["catalog"]] == ["Real AMR"]

def test_ambiguous_company_name_is_refused():
    db = DB({ct.CLIENT_TABLE: [client("c1", "Alpha Logistics A"), client("c2", "Alpha Logistics B")]})
    assert "error" in ct.get_client_brief(db, REP, "Alpha Logistics")
    assert "error" in ct.suggest_robot_matches(db, REP, "Alpha Logistics")

def test_full_company_name_resolves_to_exactly_one():
    db = DB({ct.CLIENT_TABLE: [client("c1", "Alpha Logistics A"), client("c2", "Alpha Logistics B")]})
    out = ct.get_client_brief(db, REP, "Alpha Logistics A")
    assert "error" not in out and out["company"] == "Alpha Logistics A"

def test_name_lookup_never_crosses_reps():
    db = DB({ct.CLIENT_TABLE: [client("c2", "Beta Corp", agent="repB")]})
    assert "error" in ct.get_client_brief(db, REP, "Beta Corp")
    assert "error" not in ct.get_client_brief(db, Identity("adm", True), "Beta Corp")
