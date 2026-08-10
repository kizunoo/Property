"use client"

import type { ComponentType } from "react"
import { Crown, Flame, Snowflake, Users } from "lucide-react"
import type { Tier } from "@/lib/pipeline-data"

export type SegmentFilter = "ALL" | Tier

interface SegmentPillsProps {
  active: SegmentFilter
  onChange: (value: SegmentFilter) => void
  counts: Record<SegmentFilter, number>
}

const OPTIONS: { value: SegmentFilter; label: string; icon: ComponentType<{ className?: string; strokeWidth?: number }> }[] = [
  { value: "ALL", label: "All Clients", icon: Users },
  { value: "TIER_1", label: "Tier 1 · VIP", icon: Crown },
  { value: "TIER_2", label: "Tier 2 · Warm", icon: Flame },
  { value: "TIER_3", label: "Tier 3 · Cold", icon: Snowflake },
]

export function SegmentPills({ active, onChange, counts }: SegmentPillsProps) {
  return (
    <div className="flex flex-wrap gap-3" role="tablist" aria-label="Filter by segment">
      {OPTIONS.map((option) => {
        const isActive = active === option.value
        const Icon = option.icon
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(option.value)}
            className={`flex items-center gap-2 border-2 border-black px-4 py-2.5 text-xs sm:text-sm font-black uppercase tracking-wider transition-transform ${
              isActive
                ? "bg-black text-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] -translate-x-0.5 -translate-y-0.5"
                : "bg-white text-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
            }`}
          >
            <Icon className={`h-4 w-4 ${isActive ? "text-primary" : "text-black"}`} strokeWidth={2.5} />
            {option.label}
            <span
              className={`border-2 border-black px-1.5 text-[10px] sm:text-xs ${
                isActive ? "bg-primary text-black" : "bg-black text-white"
              }`}
            >
              {counts[option.value]}
            </span>
          </button>
        )
      })}
    </div>
  )
}
