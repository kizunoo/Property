"use client";

import { useRef, useEffect, type ReactNode, type ElementType } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

export interface AnimatedContentProps {
  as?: ElementType;
  children?: ReactNode;
  container?: string | HTMLElement | null;
  distance?: number;
  direction?: "vertical" | "horizontal";
  reverse?: boolean;
  duration?: number;
  ease?: string;
  initialOpacity?: number;
  animateOpacity?: boolean;
  scale?: number;
  threshold?: number;
  delay?: number;
  disappearAfter?: number;
  disappearDuration?: number;
  disappearEase?: string;
  onComplete?: () => void;
  onDisappearanceComplete?: () => void;
  className?: string;
  [key: string]: any;
}

export function AnimatedContent({
  as: Component = "div",
  children,
  container,
  distance = 20,
  direction = "vertical",
  reverse = false,
  duration = 0.25,
  ease = "power2.out",
  initialOpacity = 0.15,
  animateOpacity = true,
  scale = 0.96,
  threshold = 0.15,
  delay = 0,
  disappearAfter = 0,
  disappearDuration = 0.5,
  disappearEase = "power3.in",
  onComplete,
  onDisappearanceComplete,
  className = "",
  ...props
}: AnimatedContentProps) {
  const ref = useRef<any>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let scrollerTarget: Element | null = null;
    if (container) {
      if (typeof container === "string") {
        scrollerTarget = document.querySelector(container);
      } else {
        scrollerTarget = container;
      }
    } else {
      scrollerTarget = document.getElementById("snap-main-container");
    }

    const axis = direction === "horizontal" ? "x" : "y";
    const offset = reverse ? -distance : distance;
    const startPct = (1 - threshold) * 100;

    gsap.set(el, {
      [axis]: offset,
      scale,
      opacity: animateOpacity ? initialOpacity : 1,
      visibility: "visible",
    });

    const tl = gsap.timeline({
      paused: true,
      delay,
      onComplete: () => {
        if (onComplete) onComplete();
        if (disappearAfter > 0) {
          gsap.to(el, {
            [axis]: reverse ? distance : -distance,
            scale: 0.8,
            opacity: animateOpacity ? initialOpacity : 0,
            delay: disappearAfter,
            duration: disappearDuration,
            ease: disappearEase,
            onComplete: () => onDisappearanceComplete?.(),
          });
        }
      },
    });

    tl.to(el, {
      [axis]: 0,
      scale: 1,
      opacity: 1,
      duration,
      ease,
    });

    const st = ScrollTrigger.create({
      trigger: el,
      scroller: scrollerTarget || window,
      start: `top ${startPct}%`,
      once: true,
      onEnter: () => tl.play(),
    });

    return () => {
      st.kill();
      tl.kill();
    };
  }, [
    container,
    distance,
    direction,
    reverse,
    duration,
    ease,
    initialOpacity,
    animateOpacity,
    scale,
    threshold,
    delay,
    disappearAfter,
    disappearDuration,
    disappearEase,
    onComplete,
    onDisappearanceComplete,
  ]);

  return (
    <Component ref={ref} className={className} style={{ visibility: "hidden" }} {...props}>
      {children}
    </Component>
  );
}

export default AnimatedContent;
