"use client"

import { useState } from "react"
import { Bot } from "lucide-react"

interface PixelatedImageCanvasProps {
  src?: string
  alt: string
  className?: string
  containerHeightClass?: string
  showCreditBadge?: boolean
  borderBottomOnly?: boolean
  disablePixelation?: boolean
}

export function PixelatedImageCanvas({
  src,
  alt,
  className = "",
  containerHeightClass = "h-48 sm:h-52",
  showCreditBadge = false,
  borderBottomOnly = true,
}: PixelatedImageCanvasProps) {
  const [error, setError] = useState(false)

  if (error || !src) {
    return (
      <div
        className={`relative flex flex-col items-center justify-center gap-2 bg-neutral-100 rounded-lg ${containerHeightClass} ${
          borderBottomOnly ? "border-b border-neutral-200" : "border border-neutral-200 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]"
        }`}
      >
        <Bot className="h-10 w-10 text-muted-foreground opacity-30" />
        <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground opacity-40">
          Image coming soon
        </span>
      </div>
    )
  }

  return (
    <div
      className={`relative w-full overflow-hidden bg-neutral-100 rounded-lg ${containerHeightClass} ${
        borderBottomOnly ? "border-b border-neutral-200" : "border border-neutral-200 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]"
      } ${className}`}
    >
      <img
        src={src}
        alt={alt}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setError(true)}
        className="block h-full w-full object-contain p-2 rounded-lg"
      />
      {showCreditBadge && (
        <span className="absolute bottom-2.5 right-2.5 rounded border border-neutral-300 bg-black/80 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white shadow-sm">
          Manufacturer image
        </span>
      )}
    </div>
  )
}
