"use client";

interface GlitchLabelProps {
  text: string;
  triggerKey?: string | number;
  glitchDuration?: number;
  className?: string;
}

export function GlitchLabel({ text, className }: GlitchLabelProps) {
  return <span className={className}>{text}</span>;
}
