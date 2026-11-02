export const DEMO_ANCHORS: readonly number[] = [0.67, 0.33, 0.5, 0.67, 0.33, 0.8, 0.5, 0.25];

export function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function demoAnchor(companyKey: string): number {
  return DEMO_ANCHORS[hashString(String(companyKey)) % DEMO_ANCHORS.length];
}

export function demoProbability(companyKey: string, robotKey: string, original: number): number {
  const a = demoAnchor(companyKey);
  const jitter = ((hashString(String(companyKey) + "|" + String(robotKey)) % 1000) / 1000 - 0.5) * 0.02;
  const lean = (Number.isFinite(original) ? original - 0.5 : 0) * 0.01;
  return Math.min(0.95, Math.max(0.05, a + jitter + lean));
}

export function applyDemoProbability<T extends Record<string, any>>(
  pairs: readonly T[],
  companyField: string,
  robotField: string,
  probField: string
): T[] {
  return pairs.map((p) => ({
    ...p,
    [probField]: demoProbability(p[companyField], p[robotField], Number(p[probField])),
  }));
}

