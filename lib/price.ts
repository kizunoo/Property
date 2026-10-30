// lib/price.ts  (reference for PHASE 9A; place unchanged)
// Use ONLY where a ROBOT price or an expected value is shown. Do NOT change the shared currency()
// helper: budgets, totals and other money fields must keep their own wording (e.g. "Not stated").

export const PRICE_ON_REQUEST = "Price on request";
export const EV_AWAITING_PRICE = "Awaiting price";

/** Positive finite number, else null. Never returns 0 for "missing". */
export function toPrice(v: unknown): number | null {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Robot price label. `fmt` is the existing currency formatter so formatting of real prices is unchanged. */
export function priceLabel(v: unknown, fmt: (n: number) => string): string {
  const p = toPrice(v);
  return p === null ? PRICE_ON_REQUEST : fmt(p);
}

/** Indicative price label. Returns null if real price is set, or if indicative is missing. */
export function indicativePriceLabel(
  indicative: number | null | undefined,
  realPrice: number | null | undefined,
  fmt: (n: number) => string,
): string | null {
  if (toPrice(realPrice) != null) return null; // a real price always wins
  const n = toPrice(indicative);
  return n == null ? null : `~${fmt(n)} (indicative)`;
}

/** Expected value label. null EV means no price yet, so say that instead of "RM 0". */
export function evLabel(v: unknown, fmt: (n: number) => string): string {
  const p = toPrice(v);
  return p === null ? EV_AWAITING_PRICE : fmt(p);
}

/** Total over priced values only. total is null when nothing is priced, so the card can say
 *  "Awaiting quotes" instead of "RM 0". */
export function sumPriced(values: Array<number | null | undefined>): {
  total: number | null;
  pricedCount: number;
  unpricedCount: number;
} {
  let total = 0;
  let pricedCount = 0;
  for (const v of values) {
    const p = toPrice(v);
    if (p !== null) {
      total += p;
      pricedCount += 1;
    }
  }
  return {
    total: pricedCount > 0 ? total : null,
    pricedCount,
    unpricedCount: values.length - pricedCount,
  };
}

/** Rows sorted best-first: priced rows by EV, then unpriced rows by probability (0-1). */
export function compareByEvThenProbability(
  a: { expectedValue: number | null; probability: number | null },
  b: { expectedValue: number | null; probability: number | null },
): number {
  const ae = toPrice(a.expectedValue);
  const be = toPrice(b.expectedValue);
  if (ae !== null && be !== null) return be - ae;
  if (ae !== null) return -1;
  if (be !== null) return 1;
  return (b.probability ?? 0) - (a.probability ?? 0);
}
