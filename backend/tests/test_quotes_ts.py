"""backend/tests/test_quotes_ts.py

Unit tests for lib/quotes.ts TypeScript logic.
Loads lib/quotes.ts via npx tsx in the same way as test_market_sim.py.
Each test case is its own test function.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


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


def test_quotes_selftest_passes():
    code = """
import { selftest } from './lib/quotes';
selftest();
console.log('OK');
"""
    out = _run_node_ts(code)
    assert out.endswith("OK")


def test_valid_quote_and_days_left():
    code = """
import { isValidQuote, daysLeft, SupplierQuote } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const MS_DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString();

const qValid: SupplierQuote = {
  id: 'q1', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};
const qExpired: SupplierQuote = {
  id: 'q2', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 15 * MS_DAY), expiresAt: iso(now - 1 * MS_DAY), supersededBy: null
};
const qSuperseded: SupplierQuote = {
  id: 'q3', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: 'q4'
};
const qZeroPrice: SupplierQuote = {
  id: 'q4', clientId: 'c1', propertyId: 'p1', priceMyr: 0, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};

console.log(JSON.stringify({
  valid: isValidQuote(qValid, now),
  expired: isValidQuote(qExpired, now),
  superseded: isValidQuote(qSuperseded, now),
  zero: isValidQuote(qZeroPrice, now),
  leftValid: daysLeft(qValid, now),
  leftExpired: daysLeft(qExpired, now),
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["valid"] is True
    assert res["expired"] is False
    assert res["superseded"] is False
    assert res["zero"] is False
    assert res["leftValid"] == 13
    assert res["leftExpired"] == 0


def test_price_order_pair_price():
    code = """
import { pairPrice, SupplierQuote } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const MS_DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString();

const validQuote: SupplierQuote = {
  id: 'q1', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};
const expQuote: SupplierQuote = {
  id: 'q2', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 15 * MS_DAY), expiresAt: iso(now - 1 * MS_DAY), supersededBy: null
};

console.log(JSON.stringify({
  realWins: pairPrice(5000, validQuote, 90000, now),
  quoteBeatsMarket: pairPrice(null, validQuote, 90000, now),
  expiredFallsToMarket: pairPrice(null, expQuote, 90000, now),
  noneWhenEmpty: pairPrice(null, null, null, now),
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["realWins"]["kind"] == "real" and res["realWins"]["value"] == 5000
    assert res["quoteBeatsMarket"]["kind"] == "quote" and res["quoteBeatsMarket"]["value"] == 100000
    assert res["expiredFallsToMarket"]["kind"] == "market" and res["expiredFallsToMarket"]["value"] == 90000
    assert res["noneWhenEmpty"]["kind"] == "none" and res["noneWhenEmpty"]["value"] is None


def test_compare_to_market():
    code = """
import { compareToMarket } from './lib/quotes';
console.log(JSON.stringify({
  cmp1: compareToMarket(100000, 96000),
  cmpInvalid: compareToMarket(100000, null),
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["cmp1"] is not None
    assert abs(res["cmp1"]["pct"] - 0.04) < 1e-9
    assert res["cmp1"]["diff"] == 4000
    assert res["cmpInvalid"] is None


def test_latest_valid_quote():
    code = """
import { latestValidQuote, SupplierQuote } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const MS_DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString();

const older: SupplierQuote = {
  id: 'old', clientId: 'c1', propertyId: 'p1', priceMyr: 110000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 5 * MS_DAY), expiresAt: iso(now + 9 * MS_DAY), supersededBy: null
};
const newer: SupplierQuote = {
  id: 'new', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};

console.log(JSON.stringify({
  bestId: latestValidQuote([older, newer], 'c1', 'p1', now)?.id,
  otherPair: latestValidQuote([older, newer], 'c1', 'unknown', now),
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["bestId"] == "new"
    assert res["otherPair"] is None


def test_agent_actions_requote_and_expiry():
    code = """
import { agentActions, SupplierQuote, Names } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const MS_DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString();

const names: Names = { client: () => 'Alpha', robot: () => 'RobotX' };
const q: SupplierQuote = {
  id: 'q1', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};

const under4 = agentActions({
  quotes: [q], requests: [], activity: [], marketByRobot: { p1: 96000 }, nowMs: now, names
});
const under2 = agentActions({
  quotes: [q], requests: [], activity: [], marketByRobot: { p1: 98000 }, nowMs: now, names
});

console.log(JSON.stringify({
  under4Length: under4.length,
  under4Kind: under4[0]?.kind,
  under4Price: under4[0]?.marketPriceMyr,
  under2Length: under2.length,
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["under4Length"] == 1
    assert res["under4Kind"] == "requote"
    assert res["under4Price"] == 96000
    assert res["under2Length"] == 0


def test_briefing_lines():
    code = """
import { briefing } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const empty = briefing([], [], [], now);
console.log(JSON.stringify({ empty: empty[0] }));
"""
    res = json.loads(_run_node_ts(code))
    assert res["empty"] == "No agent activity yet."


def test_no_function_mutates_inputs():
    code = """
import { agentActions, briefing, SupplierQuote, Names } from './lib/quotes';
const now = Date.UTC(2026, 10, 3, 9, 0, 0);
const MS_DAY = 86400000;
const iso = (ms: number) => new Date(ms).toISOString();
const names: Names = { client: () => 'A', robot: () => 'R' };
const q: SupplierQuote = {
  id: 'q1', clientId: 'c1', propertyId: 'p1', priceMyr: 100000, leadTimeWeeks: 8, terms: null,
  issuedAt: iso(now - 1 * MS_DAY), expiresAt: iso(now + 13 * MS_DAY), supersededBy: null
};

const input = {
  quotes: [q], requests: [], activity: [], marketByRobot: { p1: 90000 }, nowMs: now, names
};
const before = JSON.stringify(input);
agentActions(input);
briefing(input.quotes, input.requests, [], now);
const after = JSON.stringify(input);

console.log(JSON.stringify({ unchanged: before === after }));
"""
    res = json.loads(_run_node_ts(code))
    assert res["unchanged"] is True


def test_map_quotes_payload_drops_invalid_rows():
    code = """
import { mapQuotesPayload } from './lib/quotes';
const resNull = mapQuotesPayload(null);
const resGarbage = mapQuotesPayload("random string");
const resMixed = mapQuotesPayload({
  requests: [
    { id: "r1", client_id: "c1", property_id: "p1", kind: "quote", status: "draft" },
    { id: 123 },
    null
  ],
  quotes: [
    { id: "q1", client_id: "c1", property_id: "p1", price_myr: 100000, issued_at: "2026-11-01T00:00:00Z", expires_at: "2026-11-15T00:00:00Z" },
    { id: "q2", price_myr: -1 },
    "bad"
  ],
  activity: [
    { id: "a1", kind: "test", summary: "ok" },
    { bad: true }
  ]
});

console.log(JSON.stringify({
  nullOk: resNull.requests.length === 0 && resNull.quotes.length === 0 && resNull.activity.length === 0,
  garbageOk: resGarbage.requests.length === 0,
  reqLen: resMixed.requests.length,
  quoteLen: resMixed.quotes.length,
  actLen: resMixed.activity.length,
  firstReqId: resMixed.requests[0]?.id,
  firstQuoteId: resMixed.quotes[0]?.id,
}));
"""
    res = json.loads(_run_node_ts(code))
    assert res["nullOk"] is True
    assert res["garbageOk"] is True
    assert res["reqLen"] == 1 and res["firstReqId"] == "r1"
    assert res["quoteLen"] == 1 and res["firstQuoteId"] == "q1"
    assert res["actLen"] == 1

