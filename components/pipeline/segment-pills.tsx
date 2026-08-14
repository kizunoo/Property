"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import type { Tier } from "@/lib/pipeline-data";
import "./tab-nav.css";

export type SegmentFilter = "ALL" | Tier;

interface SegmentPillsProps {
  active: SegmentFilter;
  onChange: (value: SegmentFilter) => void;
  counts: Record<SegmentFilter, number>;
}

const OPTIONS: { value: SegmentFilter; label: string }[] = [
  { value: "ALL", label: "All Clients" },
  { value: "TIER_1", label: "Tier 1 · VIP" },
  { value: "TIER_2", label: "Tier 2 · Warm" },
  { value: "TIER_3", label: "Tier 3 · Cold" },
];

export function SegmentPills({ active, onChange, counts }: SegmentPillsProps) {
  const circleRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const tlRefs = useRef<any[]>([]);
  const activeTweenRefs = useRef<any[]>([]);

  useEffect(() => {
    const layout = () => {
      circleRefs.current.forEach((rect, i) => {
        if (!rect?.parentElement) return;
        const pill = rect.parentElement;
        const h = pill.getBoundingClientRect().height;

        gsap.set(rect, { scaleY: 0, transformOrigin: "bottom center" });

        const label = pill.querySelector(".tab-label") as HTMLElement;
        const hoverLabel = pill.querySelector(".tab-label-hover") as HTMLElement;
        if (label) gsap.set(label, { y: 0 });
        if (hoverLabel) gsap.set(hoverLabel, { y: h, opacity: 0 });

        tlRefs.current[i]?.kill();
        const tl = gsap.timeline({ paused: true });
        tl.to(rect, { scaleY: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        if (label) tl.to(label, { y: -h, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        if (hoverLabel) tl.to(hoverLabel, { y: 0, opacity: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        tlRefs.current[i] = tl;
      });
    };
    layout();
    window.addEventListener("resize", layout);
    return () => window.removeEventListener("resize", layout);
  }, [counts]);

  const handleEnter = (i: number) => {
    const tl = tlRefs.current[i];
    if (!tl) return;
    activeTweenRefs.current[i]?.kill();
    activeTweenRefs.current[i] = tl.tweenTo(tl.duration(), { duration: 0.15, ease: "power2.out", overwrite: "auto" });
  };

  const handleLeave = (i: number) => {
    const tl = tlRefs.current[i];
    if (!tl) return;
    activeTweenRefs.current[i]?.kill();
    activeTweenRefs.current[i] = tl.tweenTo(0, { duration: 0.12, ease: "power2.out", overwrite: "auto" });
  };

  return (
    <nav className="rect-tab-nav" aria-label="Filter by segment">
      <ul className="rect-tab-list" role="tablist">
        {OPTIONS.map((option, i) => {
          const isActive = active === option.value;
          const count = counts[option.value] ?? 0;
          const displayLabel = `${option.label} (${count})`;

          return (
            <li key={option.value} role="none">
              <button
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`rect-tab${isActive ? " is-active" : ""}`}
                style={{ height: "36px", padding: "0 14px", fontSize: "12px" }}
                onMouseEnter={() => handleEnter(i)}
                onMouseLeave={() => handleLeave(i)}
                onClick={() => onChange(option.value)}
              >
                <span
                  className="hover-block"
                  aria-hidden="true"
                  ref={(el) => {
                    circleRefs.current[i] = el;
                  }}
                />
                <span className="label-stack">
                  <span className="tab-label">{displayLabel}</span>
                  <span className="tab-label-hover" aria-hidden="true">
                    {displayLabel}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default SegmentPills;
