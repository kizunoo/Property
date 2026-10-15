# backend/tests/test_roi.py
import os
import sys
import json
import subprocess
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from roi import compute_roi

TEST_CASES = [
    # Case 1: Standard purchase
    {
        "inputs": {"shifts": 2, "headcountPerShift": 3, "monthlyLaborCost": 4000},
        "robot": {"purchasePrice": 120000, "leaseMonthly": None},
        "mode": "purchase",
    },
    # Case 2: Standard lease
    {
        "inputs": {"shifts": 2, "headcountPerShift": 3, "monthlyLaborCost": 4000},
        "robot": {"purchasePrice": None, "leaseMonthly": 5000},
        "mode": "lease",
    },
    # Case 3: Extreme bounds / clamping
    {
        "inputs": {"shifts": 5, "headcountPerShift": 600, "monthlyLaborCost": 2000000},
        "robot": {"purchasePrice": 500000, "leaseMonthly": None},
        "mode": "purchase",
    },
    # Case 4: Zero / null robot pricing
    {
        "inputs": {"shifts": 1, "headcountPerShift": 2, "monthlyLaborCost": 3500},
        "robot": {"purchasePrice": 0, "leaseMonthly": 0},
        "mode": "purchase",
    },
    # Case 5: Lease deficit (netMonthly <= 0)
    {
        "inputs": {"shifts": 1, "headcountPerShift": 1, "monthlyLaborCost": 2000},
        "robot": {"purchasePrice": None, "leaseMonthly": 5000},
        "mode": "lease",
    },
]

def run_node_roi(inputs: dict, robot: dict, mode: str) -> dict:
    js_code = (
        f"const {{ computeRoi }} = require('./lib/roi.ts'); "
        f"const res = computeRoi({json.dumps(inputs)}, {json.dumps(robot)}, '{mode}'); "
        f"console.log(JSON.stringify(res));"
    )
    proc = subprocess.run(
        ["node", "-e", js_code],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())

@pytest.mark.parametrize("case", TEST_CASES)
def test_roi_python_matches_typescript(case):
    py_res = compute_roi(case["inputs"], case["robot"], case["mode"])
    ts_res = run_node_roi(case["inputs"], case["robot"], case["mode"])

    assert py_res["monthlySavings"] == pytest.approx(ts_res["monthlySavings"])
    assert py_res["netMonthly"] == pytest.approx(ts_res["netMonthly"])
    if ts_res["paybackMonths"] is None:
        assert py_res["paybackMonths"] is None
    else:
        assert py_res["paybackMonths"] == pytest.approx(ts_res["paybackMonths"])
    if ts_res["threeYearRoiPct"] is None:
        assert py_res["threeYearRoiPct"] is None
    else:
        assert py_res["threeYearRoiPct"] == pytest.approx(ts_res["threeYearRoiPct"])

def test_roi_specific_calculations():
    # Case 1 math: 2 * 3 * 4000 = 24000 monthly savings. price=120000.
    # payback = 120000 / 24000 = 5.0 months.
    # 3-year net = 24000 * 36 = 864000. (864000 - 120000) / 120000 * 100 = 620%.
    res = compute_roi({"shifts": 2, "headcountPerShift": 3, "monthlyLaborCost": 4000}, {"purchasePrice": 120000}, "purchase")
    assert res["monthlySavings"] == 24000
    assert res["netMonthly"] == 24000
    assert res["paybackMonths"] == 5.0
    assert res["threeYearRoiPct"] == 620.0
