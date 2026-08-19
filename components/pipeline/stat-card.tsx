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
        className={`group flex h-full flex-col justify-between gap-4 rounded-[var(--radius)] border p-5 sm:p-6 transition-shadow duration-200 ${
          emphasis
            ? "border-l-[3px] border-l-primary border-border bg-card shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-sm-hover)]"
            : "border-border bg-card shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-sm-hover)]"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <span className={`text-xs sm:text-sm font-semibold uppercase tracking-wider pb-1 ${emphasis ? "text-primary-foreground/80" : "text-muted-foreground"}`}>
            <GlitchLabel text={label} triggerKey={triggerKey} />
          </span>
          {icon ? (
            <span className={`shrink-0 rounded-[calc(var(--radius)-2px)] p-1.5 ${emphasis ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"}`}>
              {icon}
            </span>
          ) : null}
        </div>
        <div>
          <div className="font-display text-3xl sm:text-4xl font-bold leading-none tracking-tight">
            <CountUp value={numericValue} formatNumber={formatNumber} triggerKey={triggerKey} />
          </div>
          {detail ? <div className="mt-2 text-xs sm:text-sm text-muted-foreground">{detail}</div> : null}
        </div>
      </div>
    </AnimatedContent>
  )
}
