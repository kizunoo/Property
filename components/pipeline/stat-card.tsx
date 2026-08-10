import type { ReactNode } from "react"

interface StatCardProps {
  label: string
  value: string
  detail?: string
  icon?: ReactNode
  emphasis?: boolean
}

export function StatCard({ label, value, detail, icon, emphasis }: StatCardProps) {
  return (
    <div
      className={`flex flex-col justify-between gap-4 border-4 border-black p-5 sm:p-6 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] ${
        emphasis ? "bg-primary text-primary-foreground" : "bg-card text-card-foreground"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-xs sm:text-sm font-black uppercase tracking-wider border-b-2 border-black pb-1">
          {label}
        </span>
        {icon ? (
          <span className={`shrink-0 border-2 border-black p-1.5 ${emphasis ? "bg-black text-primary" : "bg-black text-white"}`}>
            {icon}
          </span>
        ) : null}
      </div>
      <div>
        <div className="font-sans text-3xl sm:text-4xl font-bold leading-none tracking-tight">{value}</div>
        {detail ? <div className="mt-2 text-xs sm:text-sm font-bold text-muted-foreground">{detail}</div> : null}
      </div>
    </div>
  )
}
