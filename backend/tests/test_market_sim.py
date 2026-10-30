"""
backend/tests/test_market_sim.py
──────────────────────────────────
Unit tests for lib/market-sim.ts market simulator pure logic.
Ports all selftest cases from market_sim_reference.ts.
Runs TypeScript via npx tsx using the same method as test_null_property_value.py.
"""

import json
import os
import subprocess
import tempfile
import unittest


def _run_node_ts(ts_code: str) -> str:
    """Execute a TypeScript snippet via npx tsx and return stdout."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, dir=repo_root) as f:
        f.write(ts_code)
        temp_path = f.name
    try:
        res = subprocess.run(
            ["npx", "tsx", temp_path],
            capture_output=True,
            text=True,
            cwd=repo_root,
            shell=True,
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"npx tsx failed (code {res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            )
        return res.stdout.strip()
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


class TestMarketSimulatorTs(unittest.TestCase):
    """Port of market_sim_reference.ts selftest suite."""

    def test_no_prices_gives_no_rows(self):
        code = """
import { simulate, SimPair } from './lib/market-sim';
const pairs: SimPair[] = [
  { companyId: "c1", companyName: "A", robotId: "r1", probability: 0.667 },
  { companyId: "c1", companyName: "A", robotId: "r2", probability: 0.667 },
  { companyId: "c2", companyName: "B", robotId: "r1", probability: 0.3 },
  { companyId: "c2", companyName: "B", robotId: "r3", probability: 0.9 },
];
const r = simulate(pairs, {}, 1);
console.log(JSON.stringify({
  rowCount: r.rows.length,
  totalValue: r.totalValue,
  excludedCount: r.excludedRobotIds.length,
  companiesWithoutPrice: r.companiesWithoutPrice
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["rowCount"], 0)
        self.assertEqual(out["totalValue"], 0)
        self.assertEqual(out["excludedCount"], 3)
        self.assertEqual(out["companiesWithoutPrice"], 2)

    def test_best_robot_per_company_tiers_and_total(self):
        code = """
import { simulate, SimPair } from './lib/market-sim';
const pairs: SimPair[] = [
  { companyId: "c1", companyName: "A", robotId: "r1", probability: 0.667 },
  { companyId: "c1", companyName: "A", robotId: "r2", probability: 0.667 },
  { companyId: "c2", companyName: "B", robotId: "r1", probability: 0.3 },
  { companyId: "c2", companyName: "B", robotId: "r3", probability: 0.9 },
];
const r = simulate(pairs, { r1: 80000, r2: 60000, r3: null }, 1);
console.log(JSON.stringify({
  rowCount: r.rows.length,
  topCompany: r.rows[0].companyId,
  topRobot: r.rows[0].robotId,
  topEv: r.rows[0].ev,
  topTier: r.rows[0].tier,
  secondCompany: r.rows[1].companyId,
  secondTier: r.rows[1].tier,
  excluded: r.excludedRobotIds,
  totalValue: r.totalValue
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["rowCount"], 2)
        self.assertEqual(out["topCompany"], "c1")
        self.assertEqual(out["topRobot"], "r1")
        self.assertAlmostEqual(out["topEv"], 0.667 * 80000, delta=1e-4)
        self.assertEqual(out["topTier"], 1)
        self.assertEqual(out["secondCompany"], "c2")
        self.assertEqual(out["secondTier"], 3)
        self.assertEqual(out["excluded"], ["r3"])
        self.assertAlmostEqual(out["totalValue"], 0.667 * 80000 + 0.3 * 80000, delta=1e-4)

    def test_scenarios_and_clamping(self):
        code = """
import { simulate, SimPair } from './lib/market-sim';
const pairs: SimPair[] = [
  { companyId: "c1", companyName: "A", robotId: "r1", probability: 0.667 },
  { companyId: "c2", companyName: "B", robotId: "r3", probability: 0.9 },
];
const low = simulate(pairs, { r1: 80000 }, 0.7);
const high = simulate(pairs, { r3: 10000 }, 1.3);
console.log(JSON.stringify({
  lowProb: low.rows[0].probability,
  lowTier: low.rows[0].tier,
  highCount: high.rows.length,
  highProb: high.rows[0].probability
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertAlmostEqual(out["lowProb"], 0.667 * 0.7, delta=1e-5)
        self.assertEqual(out["lowTier"], 2)
        self.assertEqual(out["highCount"], 1)
        self.assertEqual(out["highProb"], 1.0)

    def test_bad_prices_count_as_missing(self):
        code = """
import { simulate, SimPair } from './lib/market-sim';
const pairs: SimPair[] = [
  { companyId: "c1", companyName: "A", robotId: "r1", probability: 0.667 }
];
const bads = [0, -1, NaN, Infinity, null, undefined];
const results = bads.map(bad => simulate(pairs, { r1: bad as any }, 1).rows.length);
console.log(JSON.stringify(results));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out, [0, 0, 0, 0, 0, 0])

    def test_starting_price_resolution(self):
        code = """
import { startingPrice } from './lib/market-sim';
const res = {
  realWins: startingPrice(50000, 70000),
  indicativeNext: startingPrice(null, 70000),
  neitherNull: startingPrice(null, null),
  zeroUnset: startingPrice(0, undefined)
};
console.log(JSON.stringify(res));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["realWins"], 50000)
        self.assertEqual(out["indicativeNext"], 70000)
        self.assertIsNone(out["neitherNull"])
        self.assertIsNone(out["zeroUnset"])

    def test_stable_tie_break(self):
        code = """
import { simulate } from './lib/market-sim';
const tie = simulate(
  [
    { companyId: "c", companyName: "C", robotId: "a", probability: 0.5 },
    { companyId: "c", companyName: "C", robotId: "b", probability: 0.5 },
  ],
  { a: 1000, b: 1000 },
  1,
);
console.log(JSON.stringify({ winner: tie.rows[0].robotId }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["winner"], "a")

    def test_to_sim_pairs(self):
        code = """
import { toSimPairs } from './lib/market-sim';
const clients = [
  { clientDbId: "cid1", name: "Company One", propertyDbId: "rid1", probability: 0.8 },
  { clientDbId: "cid2", name: "Company Two", propertyDbId: "rid2", probability: 75 }
];
const mapped = toSimPairs(clients);
console.log(JSON.stringify(mapped));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {
            "companyId": "cid1",
            "companyName": "Company One",
            "robotId": "rid1",
            "probability": 0.8,
        })
        self.assertEqual(out[1], {
            "companyId": "cid2",
            "companyName": "Company Two",
            "robotId": "rid2",
            "probability": 0.75,
        })


if __name__ == "__main__":
    unittest.main()

