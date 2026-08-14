"use client";
import { useEffect, useRef, ReactNode } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

interface RowConnectProps {
  /** Stable identifier used to report height/progress back to a growing container. */
  id: string;
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  /** Called whenever the row's rendered height changes (mount + resize). */
  onHeightChange?: (id: string, height: number) => void;
  /** Called on every scrub tick with the row's connect progress, 0 (floating) → 1 (connected). */
  onProgress?: (id: string, progress: number) => void;
  /** Called on unmount so the parent can drop this row from its bookkeeping. */
  onUnregister?: (id: string) => void;
}

export function RowConnect({
  id,
  children,
  className = "",
  onClick,
  onHeightChange,
  onProgress,
  onUnregister,
}: RowConnectProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reportHeight = () => onHeightChange?.(id, el.offsetHeight);
    reportHeight();

    const resizeObserver = new ResizeObserver(reportHeight);
    resizeObserver.observe(el);

    const tween = gsap.fromTo(
      el,
      {
        x: 56,
        scale: 0.97,
        borderWidth: 3,
        boxShadow: "6px 6px 0px 0px rgba(0,0,0,1)",
        filter: "grayscale(1)",
      },
      {
        x: 0,
        scale: 1,
        borderWidth: 0,
        boxShadow: "0px 0px 0px 0px rgba(0,0,0,0)",
        filter: "grayscale(0)",
        ease: "none",
        scrollTrigger: {
          trigger: el,
          start: "top bottom",
          end: "top 70%",
          scrub: 0.3,
          onUpdate: (self) => onProgress?.(id, self.progress),
        },
      }
    );

    return () => {
      resizeObserver.disconnect();
      tween.scrollTrigger?.kill();
      tween.kill();
      onUnregister?.(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <div
      ref={ref}
      role="row"
      onClick={onClick}
      className={className}
      style={{
        borderStyle: "solid",
        borderColor: "#000",
        background: "inherit",
        boxSizing: "border-box",
        position: "relative",
        zIndex: 1,
      }}
    >
      {children}
    </div>
  );
}
