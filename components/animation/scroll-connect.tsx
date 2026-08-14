"use client";
import { useEffect, useRef, ElementType, ComponentPropsWithoutRef, ReactNode } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

interface ScrollConnectBaseProps {
  children?: ReactNode;
  distance?: number; // how far the "disconnected" state sits, in px
  className?: string;
}

export type ScrollConnectProps<T extends ElementType = "div"> = ScrollConnectBaseProps & {
  as?: T;
} & Omit<ComponentPropsWithoutRef<T>, keyof ScrollConnectBaseProps | "as">;

export function ScrollConnect<T extends ElementType = "div">({
  children,
  distance = 60,
  className = "",
  as,
  ...props
}: ScrollConnectProps<T>) {
  const Component = as || "div";
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const tween = gsap.fromTo(
      el,
      { x: distance, opacity: 0.15, filter: "grayscale(1)" },
      {
        x: 0,
        opacity: 1,
        filter: "grayscale(0)",
        ease: "none", // linear, direct 1:1 tracking with scroll — no bounce, no smoothing
        scrollTrigger: {
          trigger: el,
          start: "top bottom", // starts animating the moment it enters the viewport from below
          end: "top 75%",      // fully "connected" once it's 75% up the viewport
          scrub: 0.3,           // ties progress directly to scroll position; small value = slight smoothing, not a delay
        },
      }
    );

    return () => {
      tween.scrollTrigger?.kill();
      tween.kill();
    };
  }, [distance]);

  return (
    <Component ref={ref} className={className} {...(props as any)}>
      {children}
    </Component>
  );
}
