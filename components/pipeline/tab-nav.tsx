"use client"

import type { ComponentType } from "react"
import { BarChart3, LayoutGrid, Home, Users } from "lucide-react"

export type DashboardTab = "DASHBOARD" | "ANALYTICS" | "PROPERTIES" | "CLIENTS"

interface TabNavProps {
  active: DashboardTab
  onChange: (value: DashboardTab) => void
}

const TABS: { value: DashboardTab; label: string; icon: ComponentType<{ className?: string; strokeWidth?: number }> }[] = [
  { value: "DASHBOARD", label: "Dashboard", icon: LayoutGrid },
  { value: "ANALYTICS", label: "Analytics", icon: BarChart3 },
  { value: "PROPERTIES", label: "Properties", icon: Home },
  { value: "CLIENTS", label: "Clients", icon: Users },
]

export function TabNav({ active, onChange }: TabNavProps) {
  return (
    <nav
      role="tablist"
      aria-label="Dashboard sections"
      className="flex flex-wrap gap-3 border-4 border-black bg-card p-2 shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] sm:gap-4"
    >
      {TABS.map((tab) => {
        const isActive = active === tab.value
        const Icon = tab.icon
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.value)}
            className={`flex items-center gap-2 border-2 border-black px-4 py-2.5 text-xs font-black uppercase tracking-wider transition-transform sm:text-sm ${
              isActive
                ? "-translate-x-0.5 -translate-y-0.5 bg-black text-white shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
                : "bg-white text-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]"
            }`}
          >
            <Icon className={`h-4 w-4 ${isActive ? "text-primary" : "text-black"}`} strokeWidth={2.5} />
            {tab.label}
          </button>
        )
      })}
    </nav>
  )
}
