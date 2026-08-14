import type { ReactNode } from "react"
import { CountUp } from "@/components/animation/count-up"
import { GlitchLabel } from "@/components/animation/glitch-label"
import { AnimatedContent } from "@/components/animation/animated-content"

interface StatCardProps {
  label: string
  numericValue: number
  formatNumber?: (n: number) => string
  detail?: string
  icon?: ReactNode
  emphasis?: boolean
  index?: number
  triggerKey?: string | number
}

export function StatCard({
  label,
  numericValue,
  formatNumber,
  detail,
  icon,
  emphasis,
  index = 0,
  triggerKey,
}: StatCardProps) {
  return (
    <AnimatedContent delay={index * 0.04} className="h-full">
      <div
        className={`flex h-full flex-col justify-between gap-4 border-4 border-black p-5 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] ${
          emphasis ? "bg-primary text-primary-foreground" : "bg-card text-card-foreground"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="text-xs sm:text-sm font-black uppercase tracking-wider border-b-2 border-black pb-1">
            <GlitchLabel text={label} triggerKey={triggerKey} />
          </span>
          {icon ? (
            <span className={`shrink-0 border-2 border-black p-1.5 ${emphasis ? "bg-black text-primary" : "bg-black text-white"}`}>
              {icon}
            </span>
          ) : null}
        </div>
        <div>
          <div className="font-sans text-3xl sm:text-4xl font-bold leading-none tracking-tight">
            <CountUp value={numericValue} formatNumber={formatNumber} triggerKey={triggerKey} />
          </div>
          {detail ? <div className="mt-2 text-xs sm:text-sm font-bold text-muted-foreground">{detail}</div> : null}
        </div>
      </div>
    </AnimatedContent>
  )
}
