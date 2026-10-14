"use client"

import { useState } from "react"
import { Building2 } from "lucide-react"

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
        className={`stripes-diagonal relative flex ${containerHeightClass} w-full items-center justify-center bg-white rounded-lg ${
          borderBottomOnly ? "border-b border-neutral-200" : "border border-neutral-200 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]"
        }`}
      >
        <div className="relative z-10 flex h-16 w-16 items-center justify-center border border-neutral-200 bg-primary shadow-[0px_2px_8px_rgba(0,0,0,0.08)] rounded-lg">
          <Building2 className="h-8 w-8 text-black" strokeWidth={2.5} />
        </div>
      </div>
    )
  }

  return (
    <div
      className={`relative w-full overflow-hidden bg-neutral-900 rounded-lg ${containerHeightClass} ${
        borderBottomOnly ? "border-b border-neutral-200" : "border border-neutral-200 shadow-[0px_4px_16px_rgba(0,0,0,0.10)]"
      } ${className}`}
    >
      <img
        src={src}
        alt={alt}
        onError={() => setError(true)}
        className="block h-full w-full object-cover rounded-lg"
      />
      {showCreditBadge && (
        <span className="absolute bottom-2.5 right-2.5 rounded-lg border border-neutral-200 bg-black px-2.5 py-1 text-[9px] font-black uppercase tracking-wider text-primary shadow-[0px_1px_4px_rgba(0,0,0,0.07)]">
          Photos via Pexels
        </span>
      )}
    </div>
  )
}
