"use client";

import { useEffect, useState, useRef } from "react";

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
  speed = 50,
  maxIterations = 10,
  sequential = false,
  revealDirection = "start",
  useOriginalCharsOnly = false,
  characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+",
  className = "",
  encryptedClassName = "",
  parentClassName = "",
  animateOn = "view",
}: DecryptedTextProps) {
  const [displayText, setDisplayText] = useState(text);
  const [isHovered, setIsHovered] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);

  const availableChars = useOriginalCharsOnly
    ? Array.from(new Set(text.replace(/\s/g, ""))).join("") || characters
    : characters;

  useEffect(() => {
    let interval: NodeJS.Timeout;
    let currentIteration = 0;

    const getNextChar = () => {
      const charsToUse = useOriginalCharsOnly ? availableChars : characters;
      return charsToUse[Math.floor(Math.random() * charsToUse.length)];
    };

    const startDecrypting = () => {
      const length = text.length;

      interval = setInterval(() => {
        currentIteration++;

        const revealedIndices = new Set<number>();
        if (sequential) {
          const numRevealed = Math.floor((currentIteration / maxIterations) * length);
          if (revealDirection === "start") {
            for (let i = 0; i < numRevealed; i++) revealedIndices.add(i);
          } else if (revealDirection === "end") {
            for (let i = length - 1; i >= length - numRevealed; i--) revealedIndices.add(i);
          } else {
            const mid = Math.floor(length / 2);
            const half = Math.floor(numRevealed / 2);
            for (let i = mid - half; i <= mid + half; i++) {
              if (i >= 0 && i < length) revealedIndices.add(i);
            }
          }
        }

        const nextText = text
          .split("")
          .map((char, index) => {
            if (char === " ") return " ";
            if (sequential && revealedIndices.has(index)) return char;
            if (!sequential && currentIteration >= maxIterations) return char;
            return getNextChar();
          })
          .join("");

        setDisplayText(nextText);

        if (currentIteration >= maxIterations) {
          setDisplayText(text);
          clearInterval(interval);
        }
      }, speed);
    };

    if (animateOn === "view" || (animateOn === "hover" && isHovered)) {
      startDecrypting();
    } else {
      setDisplayText(text);
    }

    return () => clearInterval(interval);
  }, [text, speed, maxIterations, sequential, revealDirection, useOriginalCharsOnly, availableChars, characters, animateOn, isHovered]);

  return (
    <span
      ref={containerRef}
      className={`inline-block ${parentClassName}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">
        {displayText.split("").map((char, index) => {
          const isRevealed = char === text[index];
          return (
            <span
              key={index}
              className={isRevealed ? className : encryptedClassName}
            >
              {char}
            </span>
          );
        })}
      </span>
    </span>
  );
}

export default DecryptedText;
