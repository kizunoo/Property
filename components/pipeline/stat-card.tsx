import type { ReactNode } from "react"
import { CountUp } from "@/components/animation/count-up"
import { AnimatedContent } from "@/components/animation/animated-content"

interface StatCardProps {
  label: string
  numericValue: number | null
  formatNumber?: (n: number) => string
  detail?: string
  icon?: ReactNode
  accent?: "yellow" | "gray" | "none"
  emphasis?: boolean
  index?: number
  triggerKey?: string | number
  hasDisplayPrice?: boolean
}

export function StatCard({
  label,
  numericValue,
  formatNumber,
  detail,
  icon,
  accent,
  emphasis,
  index = 0,
  triggerKey,
  hasDisplayPrice,
}: StatCardProps) {
  const resolvedAccent = accent ?? (emphasis ? "yellow" : "gray")

  const accentBorderClass =
    resolvedAccent === "yellow"
      ? "border-l-[3px] border-l-primary"
      : resolvedAccent === "gray"
      ? "border-l-[3px] border-l-neutral-300 dark:border-l-neutral-600"
      : ""

  return (
    <AnimatedContent delay={index * 0.04} className="h-full">
      <div
        className={`group flex h-full flex-col justify-between gap-4 rounded-[var(--radius)] border border-border bg-card p-5 sm:p-6 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-sm-hover)] transition-shadow duration-200 ${accentBorderClass}`}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="text-xs sm:text-sm font-semibold uppercase tracking-wider text-muted-foreground pb-1">
            {label}
          </span>
          {icon ? (
            <span
              className={`shrink-0 rounded-[8px] p-1.5 ${
                resolvedAccent === "yellow"
                  ? "bg-primary text-primary-foreground"
                  : "bg-black text-white"
              }`}
            >
              {icon}
            </span>
          ) : null}
        </div>
        <div>
          <div className="font-display text-3xl sm:text-4xl font-bold leading-none tracking-tight">
            {numericValue !== null ? (
              <CountUp value={numericValue} formatNumber={formatNumber} triggerKey={triggerKey} />
            ) : hasDisplayPrice ? (
              formatNumber ? formatNumber(0) : "RM 0"
            ) : (
              <span className="text-2xl sm:text-3xl text-muted-foreground">Awaiting quotes</span>
            )}
          </div>
          {detail ? <div className="mt-2 text-xs sm:text-sm text-muted-foreground">{detail}</div> : null}
        </div>
      </div>
    </AnimatedContent>
  )
}
