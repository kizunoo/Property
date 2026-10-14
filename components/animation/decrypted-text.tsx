"use client";

interface DecryptedTextProps {
  text: string;
  speed?: number;
  maxIterations?: number;
  sequential?: boolean;
  revealDirection?: "start" | "end" | "center";
  useOriginalCharsOnly?: boolean;
  characters?: string;
  className?: string;
  encryptedClassName?: string;
  parentClassName?: string;
  animateOn?: "view" | "hover";
}

export function DecryptedText({
  text,
  className = "",
  parentClassName = "",
}: DecryptedTextProps) {
  return (
    <span className={`inline-block ${parentClassName}`}>
      <span className={className}>{text}</span>
    </span>
  );
}

export default DecryptedText;
