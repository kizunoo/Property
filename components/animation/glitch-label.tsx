"use client";
import { useEffect, useState } from "react";

const GLITCH_CHARS = "█▓▒░/\\|—•";

interface GlitchLabelProps {
  text: string;
  triggerKey?: string | number; // change this to re-trigger the glitch (e.g. on Sync & Re-evaluate)
  glitchDuration?: number; // ms
  className?: string;
}

export function GlitchLabel({
  text, triggerKey, glitchDuration = 220, className,
}: GlitchLabelProps) {
  const [display, setDisplay] = useState(text);

  useEffect(() => {
    let frame = 0;
    const totalFrames = 5; // small number of steps = snappy, not smooth
    const interval = glitchDuration / totalFrames;

    const id = setInterval(() => {
      frame++;
      if (frame >= totalFrames) {
        setDisplay(text);
        clearInterval(id);
        return;
      }
      const revealCount = Math.floor((frame / totalFrames) * text.length);
      const scrambled = text
        .split("")
        .map((ch, i) =>
          i < revealCount || ch === " "
            ? ch
            : GLITCH_CHARS[Math.floor(Math.random() * GLITCH_CHARS.length)]
        )
        .join("");
      setDisplay(scrambled);
    }, interval);

    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerKey]);

  return <span className={className} style={{ fontFamily: "var(--font-mono)" }}>{display}</span>;
}
