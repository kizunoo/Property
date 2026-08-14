"use client";
import { useEffect, useRef, useState } from "react";

interface CountUpProps {
  value: number;
  duration?: number; // ms
  prefix?: string;
  suffix?: string;
  decimals?: number;
  formatNumber?: (n: number) => string; // e.g. RM currency formatter
  triggerKey?: string | number; // change this to re-trigger the count (e.g. on Sync & Re-evaluate)
}

export function CountUp({
  value, duration = 700, prefix = "", suffix = "",
  decimals = 0, formatNumber, triggerKey,
}: CountUpProps) {
  const [display, setDisplay] = useState(0);
  const fromRef = useRef(0);

  useEffect(() => {
    const from = fromRef.current;
    const to = value;
    const start = performance.now();

    let raf: number;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // linear — no ease-in-out softness, stays mechanical/snappy
      const current = from + (to - from) * t;
      setDisplay(current);
      if (t < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = to;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, triggerKey]);

  const text = formatNumber
    ? formatNumber(display)
    : display.toFixed(decimals);

  return <span>{prefix}{text}{suffix}</span>;
}
