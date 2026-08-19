"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import "./tab-nav.css";

export type DashboardTab = "DASHBOARD" | "ANALYTICS" | "PROPERTIES" | "CLIENTS" | "VIEWINGS";

export interface TabItem {
  key: string;
  label: string;
}

export interface TabNavProps {
  items?: TabItem[];
  activeKey?: string;
  onSelect?: (key: string) => void;
  active?: DashboardTab;
  onChange?: (value: DashboardTab) => void;
}

const DEFAULT_ITEMS: TabItem[] = [
  { key: "DASHBOARD", label: "Dashboard" },
  { key: "ANALYTICS", label: "Analytics" },
  { key: "PROPERTIES", label: "Properties" },
  { key: "CLIENTS", label: "Clients" },
  { key: "VIEWINGS", label: "Viewings" },
];

export function TabNav({
  items = DEFAULT_ITEMS,
  activeKey,
  onSelect,
  active,
  onChange,
}: TabNavProps) {
  const currentActiveKey = activeKey ?? active ?? "DASHBOARD";
  const handleSelect = (key: string) => {
    if (onSelect) onSelect(key);
    if (onChange) onChange(key as DashboardTab);
  };

  const circleRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const tlRefs = useRef<any[]>([]);
  const activeTweenRefs = useRef<any[]>([]);

  useEffect(() => {
    const layout = () => {
      circleRefs.current.forEach((rect, i) => {
        if (!rect?.parentElement) return;
        const pill = rect.parentElement;
        const h = pill.getBoundingClientRect().height;

        // Rectangular wipe — no circle-radius geometry needed, just a hard block scaling up from the bottom
        gsap.set(rect, { scaleY: 0, transformOrigin: "bottom center" });

        const label = pill.querySelector(".tab-label") as HTMLElement;
        const hoverLabel = pill.querySelector(".tab-label-hover") as HTMLElement;
        if (label) gsap.set(label, { y: 0 });
        if (hoverLabel) gsap.set(hoverLabel, { y: h, opacity: 0 });

        tlRefs.current[i]?.kill();
        const tl = gsap.timeline({ paused: true });
        // fast, linear-leaning ease — snap, not glide
        tl.to(rect, { scaleY: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        if (label) tl.to(label, { y: -h, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        if (hoverLabel) tl.to(hoverLabel, { y: 0, opacity: 1, duration: 0.18, ease: "power2.out", overwrite: "auto" }, 0);
        tlRefs.current[i] = tl;
      });
    };
    layout();
    window.addEventListener("resize", layout);
    return () => window.removeEventListener("resize", layout);
  }, [items]);

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
    <nav className="rect-tab-nav" aria-label="Primary">
      <ul className="rect-tab-list" role="tablist">
        {items.map((item, i) => (
          <li key={item.key} role="none">
            <button
              type="button"
              role="tab"
              aria-selected={currentActiveKey === item.key}
              className={`rect-tab${currentActiveKey === item.key ? " is-active" : ""}`}
              onMouseEnter={() => handleEnter(i)}
              onMouseLeave={() => handleLeave(i)}
              onClick={() => handleSelect(item.key)}
            >
              <span
                className="hover-block"
                aria-hidden="true"
                ref={(el) => { circleRefs.current[i] = el; }}
              />
              <span className="label-stack">
                <span className="tab-label">{item.label}</span>
                <span className="tab-label-hover" aria-hidden="true">{item.label}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default TabNav;
