// lib/roi.ts
export type RoiInputs = { shifts: 1 | 2 | 3; headcountPerShift: number; monthlyLaborCost: number };
export type RoiRobot = { purchasePrice?: number | null; leaseMonthly?: number | null };
export type RoiResult = {
  monthlySavings: number;
  netMonthly: number;
  paybackMonths: number | null;
  threeYearRoiPct: number | null;
};

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export function computeRoi(i: RoiInputs, r: RoiRobot, mode: "purchase" | "lease"): RoiResult {
  const shifts = clamp(Math.round(i.shifts), 1, 3);
  const heads = clamp(i.headcountPerShift, 0, 500);
  const labor = clamp(i.monthlyLaborCost, 0, 1_000_000);
  const monthlySavings = shifts * heads * labor;

  if (mode === "lease") {
    const lease = r.leaseMonthly ?? 0;
    const netMonthly = monthlySavings - lease;
    return {
      monthlySavings, netMonthly,
      paybackMonths: netMonthly > 0 ? 0 : null,          // no upfront cost on lease
      threeYearRoiPct: lease > 0 ? (netMonthly * 36) / (lease * 36) * 100 : null,
    };
  }
  const price = r.purchasePrice ?? 0;
  const netMonthly = monthlySavings;
  return {
    monthlySavings, netMonthly,
    paybackMonths: price > 0 && netMonthly > 0 ? price / netMonthly : null,
    threeYearRoiPct: price > 0 ? ((netMonthly * 36 - price) / price) * 100 : null,
  };
}
