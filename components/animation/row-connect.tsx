"use client";
import { useEffect, useRef, ReactNode } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

interface RowConnectProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function RowConnect({ children, className = "", onClick }: RowConnectProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const tween = gsap.fromTo(
      el,
      {
        x: 56,
        marginTop: 20,
        marginBottom: 20,
        scale: 0.97,
        borderWidth: 3,
        boxShadow: "6px 6px 0px 0px rgba(0,0,0,1)",
        filter: "grayscale(1)",
      },
      {
        x: 0,
        marginTop: 0,
        marginBottom: 0,
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
        },
      }
    );

    return () => {
      tween.scrollTrigger?.kill();
      tween.kill();
    };
  }, []);

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
      }}
    >
      {children}
    </div>
  );
}
