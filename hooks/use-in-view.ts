"use client";
import { useEffect, useRef, useState } from "react";

export interface UseInViewOptions extends IntersectionObserverInit {
  once?: boolean;
}

export function useInView(options?: UseInViewOptions) {
  const ref = useRef<any>(null);
  const [isInView, setIsInView] = useState(false);
  const { once = false, threshold = 0.15, ...observerOptions } = options ?? {};

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          if (once) observer.disconnect();
        } else if (!once) {
          setIsInView(false);
        }
      },
      { threshold, ...observerOptions }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [once, threshold]);

  return { ref, isInView };
}
