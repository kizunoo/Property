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

    def test_fluct_1_same_seed_same_path(self):
        code = """
import { pricePath, VOLATILITY, mulberry32 } from './lib/market-sim';
const a = pricePath(100000, 12, VOLATILITY.medium, mulberry32(7));
const b = pricePath(100000, 12, VOLATILITY.medium, mulberry32(7));
console.log(JSON.stringify({ match: JSON.stringify(a) === JSON.stringify(b) }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["match"])

    def test_fluct_2_different_seed_different_path(self):
        code = """
import { pricePath, VOLATILITY, mulberry32 } from './lib/market-sim';
const a = pricePath(100000, 12, VOLATILITY.medium, mulberry32(7));
const c = pricePath(100000, 12, VOLATILITY.medium, mulberry32(8));
console.log(JSON.stringify({ diff: JSON.stringify(a) !== JSON.stringify(c) }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["diff"])

    def test_fluct_3_path_length_and_start(self):
        code = """
import { pricePath, VOLATILITY, mulberry32 } from './lib/market-sim';
const a = pricePath(100000, 12, VOLATILITY.medium, mulberry32(7));
console.log(JSON.stringify({ length: a.length, start: a[0] }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["length"], 13)
        self.assertEqual(out["start"], 100000)

    def test_fluct_4_bounds_respected_high_vol(self):
        code = """
import { pricePath, MIN_MULT, MAX_MULT, mulberry32 } from './lib/market-sim';
const h = pricePath(100000, 24, { sigma: 0.5, drift: 0.2 }, mulberry32(1));
const inBounds = h.every(p => p >= 100000 * MIN_MULT - 1e-6 && p <= 100000 * MAX_MULT + 1e-6);
console.log(JSON.stringify({ inBounds }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["inBounds"])

    def test_fluct_5_zero_vol_flat(self):
        code = """
import { pricePath, mulberry32 } from './lib/market-sim';
const flat = pricePath(50000, 6, { sigma: 0, drift: 0 }, mulberry32(3));
const isFlat = flat.every(p => Math.abs(p - 50000) < 1e-6);
console.log(JSON.stringify({ isFlat }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["isFlat"])

    def test_fluct_6_percentiles_order_and_exclusions(self):
        code = """
import { runFluctuation } from './lib/market-sim';
const valueFn = (prices: Record<string, number>) =>
  Object.values(prices).reduce((s, p) => s + p * 0.5, 0);
const r = runFluctuation({
  startPrices: { A: 100000, B: 200000, C: null, D: undefined, E: 0, F: -5, G: NaN },
  months: 12,
  trials: 100,
  vol: "medium",
  seed: 42,
  valueFn,
});
const ordered = r.months.every(m => m.p10 <= m.p50 && m.p50 <= m.p90);
console.log(JSON.stringify({
  robotsSimulated: r.robotsSimulated,
  robotsExcluded: r.robotsExcluded,
  monthsCount: r.months.length,
  ordered,
  month0P50: r.months[0].p50,
  cExcluded: !("C" in r.medianPrices)
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["robotsSimulated"], 2)
        self.assertEqual(out["robotsExcluded"], 5)
        self.assertEqual(out["monthsCount"], 13)
        self.assertTrue(out["ordered"])
        self.assertAlmostEqual(out["month0P50"], 150000, delta=1e-4)
        self.assertTrue(out["cExcluded"])

    def test_fluct_7_nothing_priced_no_crash(self):
        code = """
import { runFluctuation } from './lib/market-sim';
const valueFn = (prices: Record<string, number>) =>
  Object.values(prices).reduce((s, p) => s + p * 0.5, 0);
const none = runFluctuation({
  startPrices: { A: null },
  months: 3,
  trials: 10,
  vol: "low",
  seed: 1,
  valueFn,
});
console.log(JSON.stringify({
  robotsSimulated: none.robotsSimulated,
  month3P50: none.months[3].p50
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["robotsSimulated"], 0)
        self.assertEqual(out["month3P50"], 0)

    def test_fluct_8_clamps(self):
        code = """
import { runFluctuation, MAX_MONTHS, MAX_TRIALS } from './lib/market-sim';
const valueFn = (prices: Record<string, number>) =>
  Object.values(prices).reduce((s, p) => s + p * 0.5, 0);
const big = runFluctuation({
  startPrices: { A: 1000 },
  months: 9999,
  trials: 999999,
  vol: "low",
  seed: 1,
  valueFn,
});
console.log(JSON.stringify({
  monthsLen: big.months.length,
  maxMonthsPlus1: MAX_MONTHS + 1,
  trials: big.trials,
  maxTrials: MAX_TRIALS
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["monthsLen"], out["maxMonthsPlus1"])
        self.assertEqual(out["trials"], out["maxTrials"])

    def test_fluct_deterministic_twice(self):
        code = """
import { runFluctuation } from './lib/market-sim';
const valueFn = (prices: Record<string, number>) =>
  Object.values(prices).reduce((s, p) => s + p * 0.7, 0);
const input = {
  startPrices: { A: 50000, B: 80000 },
  months: 6,
  trials: 50,
  vol: "medium" as const,
  seed: 12345,
  valueFn,
};
const run1 = runFluctuation(input);
const run2 = runFluctuation(input);
console.log(JSON.stringify({ match: JSON.stringify(run1) === JSON.stringify(run2) }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["match"])

    def test_fluct_does_not_mutate_start_prices(self):
        code = """
import { runFluctuation } from './lib/market-sim';
const valueFn = (prices: Record<string, number>) => 100;
const startPrices: Record<string, any> = { A: 50000, B: null, C: 120000 };
const original = JSON.stringify(startPrices);
runFluctuation({
  startPrices,
  months: 6,
  trials: 10,
  vol: "low",
  seed: 99,
  valueFn,
});
console.log(JSON.stringify({ mutated: JSON.stringify(startPrices) !== original }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertFalse(out["mutated"])

    def test_display_price_real_beats_indicative(self):
        code = """
import { displayPrice } from './lib/display-price';
const res = displayPrice(80000, 70000);
console.log(JSON.stringify(res));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["value"], 80000)
        self.assertEqual(out["kind"], "real")

    def test_display_price_indicative_fallbacks(self):
        code = """
import { displayPrice } from './lib/display-price';
const badReals = [null, 0, -500, NaN, undefined];
const results = badReals.map(r => displayPrice(r, 70000));
console.log(JSON.stringify(results));
"""
        out = json.loads(_run_node_ts(code))
        for item in out:
            self.assertEqual(item["value"], 70000)
            self.assertEqual(item["kind"], "indicative")

    def test_display_price_none_when_both_invalid(self):
        code = """
import { displayPrice } from './lib/display-price';
const cases = [
  displayPrice(null, null),
  displayPrice(0, -100),
  displayPrice(undefined, NaN),
  displayPrice("bad", null)
];
console.log(JSON.stringify(cases));
"""
        out = json.loads(_run_node_ts(code))
        for item in out:
            self.assertIsNone(item["value"])
            self.assertEqual(item["kind"], "none")

    def test_format_rm(self):
        code = """
import { formatRM } from './lib/display-price';
const res = {
  standard: formatRM(133000),
  rounded: formatRM(133000.4),
  nullVal: formatRM(null),
  undefinedVal: formatRM(undefined),
  nanVal: formatRM(NaN)
};
console.log(JSON.stringify(res));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["standard"], "RM 133,000")
        self.assertEqual(out["rounded"], "RM 133,000")
        self.assertEqual(out["nullVal"], "RM 0")
        self.assertEqual(out["undefinedVal"], "RM 0")
        self.assertEqual(out["nanVal"], "RM 0")

    def test_display_price_does_not_modify_inputs(self):
        code = """
import { displayPrice } from './lib/display-price';
const r = 50000;
const i = 40000;
const out = displayPrice(r, i);
console.log(JSON.stringify({ rSame: r === 50000, iSame: i === 40000 }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["rSame"])
        self.assertTrue(out["iSame"])

    def test_potential_pipeline_excludes_none_and_matches_simulate(self):
        code = """
import { potentialPipeline } from './lib/display-price';
import { simulate, SimPair } from './lib/market-sim';
const pairs: SimPair[] = [
  { companyId: "c1", companyName: "Co A", robotId: "r1", probability: 0.6 },
  { companyId: "c2", companyName: "Co B", robotId: "r2", probability: 0.8 },
  { companyId: "c3", companyName: "Co C", robotId: "r3", probability: 0.5 }
];
const displayPrices = { r1: 100000, r2: 50000, r3: null };
const pRes = potentialPipeline(pairs, displayPrices);
const sRes = simulate(pairs, displayPrices, 1);
console.log(JSON.stringify({
  pTotal: pRes.total,
  sTotal: sRes.totalValue,
  robotsUsed: pRes.robotsUsed,
  robotsExcluded: pRes.robotsExcluded
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["pTotal"], out["sTotal"])
        self.assertEqual(out["robotsUsed"], 2)
        self.assertEqual(out["robotsExcluded"], 1)

    def test_tick_gap_and_tick_time(self):
        code = """
import { tickGapMs, tickTimeMs, SIM_EPOCH_MS } from './lib/market-sim';
let gapsOk = true;
let timeStrictlyIncreasing = true;
let prevTime = SIM_EPOCH_MS;
for (let k = 1; k <= 2000; k++) {
  const g = tickGapMs(k);
  const minMinutes = 30 * 60 * 1000;
  const maxMinutes = 120 * 60 * 1000;
  if (g < minMinutes || g > maxMinutes || g % 60000 !== 0) {
    gapsOk = false;
    break;
  }
  const t = tickTimeMs(k);
  if (t <= prevTime) {
    timeStrictlyIncreasing = false;
    break;
  }
  prevTime = t;
}
console.log(JSON.stringify({ gapsOk, timeStrictlyIncreasing }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertTrue(out["gapsOk"])
        self.assertTrue(out["timeStrictlyIncreasing"])

    def test_current_tick_and_next_tick(self):
        code = """
import { currentTick, nextTickMs, tickTimeMs, SIM_EPOCH_MS } from './lib/market-sim';
const atEpoch = currentTick(SIM_EPOCH_MS);
const beforeEpoch = currentTick(SIM_EPOCH_MS - 1000);
const invalidTick = currentTick(NaN);

let ticksOk = true;
let nextOk = true;
for (let k = 1; k <= 100; k++) {
  const tK = tickTimeMs(k);
  const tNext = tickTimeMs(k + 1);
  if (currentTick(tK) !== k) { ticksOk = false; break; }
  if (currentTick(tNext - 1) !== k) { ticksOk = false; break; }
  const nxt = nextTickMs(tK);
  if (nxt <= tK || nxt - tK > 120 * 60 * 1000) { nextOk = false; break; }
}
console.log(JSON.stringify({ atEpoch, beforeEpoch, invalidTick, ticksOk, nextOk }));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["atEpoch"], 0)
        self.assertEqual(out["beforeEpoch"], 0)
        self.assertEqual(out["invalidTick"], 0)
        self.assertTrue(out["ticksOk"])
        self.assertTrue(out["nextOk"])

    def test_price_at_tick_bounds_and_determinism(self):
        code = """
import { priceAtTick, MIN_MULT, MAX_MULT } from './lib/market-sim';
const start = 100000;
const p0 = priceAtTick(start, "r1", 0);
const p50_a = priceAtTick(start, "r1", 50);
const p50_b = priceAtTick(start, "r1", 50);
const p50_other = priceAtTick(start, "r2", 50);
const pInvalid = priceAtTick(null, "r1", 10);
const pNegative = priceAtTick(-100, "r1", 10);

let inBounds = true;
for (let t = 0; t <= 100; t++) {
  const pt = priceAtTick(start, "r1", t);
  if (pt === null || pt < start * MIN_MULT * 0.99 || pt > start * MAX_MULT * 1.01) {
    inBounds = false;
    break;
  }
}
console.log(JSON.stringify({
  p0,
  deterministic: p50_a === p50_b,
  differsByRobot: p50_a !== p50_other,
  pInvalid,
  pNegative,
  inBounds
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["p0"], 100000)
        self.assertTrue(out["deterministic"])
        self.assertTrue(out["differsByRobot"])
        self.assertIsNone(out["pInvalid"])
        self.assertIsNone(out["pNegative"])
        self.assertTrue(out["inBounds"])

    def test_price_history(self):
        code = """
import { priceHistory, priceAtTick } from './lib/market-sim';
const start = 80000;
const history10 = priceHistory(start, "r1", 10, 48);
const history50 = priceHistory(start, "r1", 50, 48);
const lastPrice50 = priceAtTick(start, "r1", 50);
const invalidHistory = priceHistory(0, "r1", 10, 48);
console.log(JSON.stringify({
  len10: history10.length,
  len50: history50.length,
  lastMatches: history50[history50.length - 1].price === lastPrice50,
  invalidLen: invalidHistory.length
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["len10"], 11)  # min(48, 10 + 1)
        self.assertEqual(out["len50"], 48)  # min(48, 50 + 1)
        self.assertTrue(out["lastMatches"])
        self.assertEqual(out["invalidLen"], 0)

    def test_display_price_order_real_beats_sim_beats_ind(self):
        code = """
import { displayPrice, simulatedPriceMap } from './lib/display-price';
const realBeatsSim = displayPrice(100000, 50000, 75000);
const simBeatsInd = displayPrice(null, 50000, 75000);
const indBeatsNone = displayPrice(null, 50000, null);
const noneInvalid = displayPrice(null, null, null);

const robots = [{ id: "r1", indicativePriceMyr: 60000 }, { id: "r2", indicative_price_myr: 90000 }];
const simMap = simulatedPriceMap(robots, 5);
console.log(JSON.stringify({
  realBeatsSim,
  simBeatsInd,
  indBeatsNone,
  noneInvalid,
  simMapR1: simMap["r1"] != null && simMap["r1"] > 0,
  simMapR2: simMap["r2"] != null && simMap["r2"] > 0
}));
"""
        out = json.loads(_run_node_ts(code))
        self.assertEqual(out["realBeatsSim"]["kind"], "real")
        self.assertEqual(out["realBeatsSim"]["value"], 100000)
        self.assertEqual(out["simBeatsInd"]["kind"], "simulated")
        self.assertEqual(out["simBeatsInd"]["value"], 75000)
        self.assertEqual(out["indBeatsNone"]["kind"], "indicative")
        self.assertEqual(out["indBeatsNone"]["value"], 50000)
        self.assertEqual(out["noneInvalid"]["kind"], "none")
        self.assertIsNone(out["noneInvalid"]["value"])
        self.assertTrue(out["simMapR1"])
        self.assertTrue(out["simMapR2"])


if __name__ == "__main__":
    unittest.main()

