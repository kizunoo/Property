"use client"

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { BarChart3 } from "lucide-react"
import { CLIENTS, currency, type Tier } from "@/lib/pipeline-data"

const TIER_ORDER: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

const TIER_META: Record<Tier, { label: string; fill: string }> = {
  TIER_1: { label: "TIER 1 · VIP", fill: "var(--primary)" },
  TIER_2: { label: "TIER 2 · WARM", fill: "#000000" },
  TIER_3: { label: "TIER 3 · COLD", fill: "#d4d4d4" },
}

interface TooltipPayload {
  active?: boolean
  payload?: { payload: { label: string; value: number; count: number } }[]
}

function ChartTooltip({ active, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return (
    <div className="border-4 border-black bg-white px-4 py-3 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
      <div className="text-xs font-black uppercase tracking-wider">{item.label}</div>
      <div className="mt-1 font-mono text-lg font-black">{currency(item.value)}</div>
      <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        {item.count} {item.count === 1 ? "client" : "clients"}
      </div>
    </div>
  )
}

interface TierValueChartProps {
  tall?: boolean
}

export function TierValueChart({ tall = false }: TierValueChartProps) {
  const data = TIER_ORDER.map((tier) => {
    const items = CLIENTS.filter((c) => c.tier === tier)
    return {
      tier,
      label: TIER_META[tier].label,
      value: items.reduce((sum, c) => sum + c.expectedValue, 0),
      count: items.length,
    }
  })

  return (
    <div className="border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
      <div className="flex items-center justify-between gap-3 border-b-4 border-black bg-black px-5 py-3.5 sm:px-6">
        <div className="flex items-center gap-2 text-white">
          <BarChart3 className="h-4 w-4" strokeWidth={2.5} />
          <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
            Total Expected Value by Tier
          </span>
        </div>
        <span className="border-2 border-black bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
          Live
        </span>
      </div>

      <div className={tall ? "h-[60vh] min-h-[420px] p-4 sm:p-8" : "h-[280px] p-4 sm:h-[320px] sm:p-6"}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }} barCategoryGap="28%">
            <CartesianGrid stroke="rgba(0,0,0,0.15)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#000000", fontWeight: 900, fontSize: 11 }}
              axisLine={{ stroke: "#000000", strokeWidth: 3 }}
              tickLine={{ stroke: "#000000", strokeWidth: 2 }}
            />
            <YAxis
              tickFormatter={(value: number) => currency(value).replace("$", "").replace(/,\d{3}$/, "K")}
              tick={{ fill: "#000000", fontWeight: 700, fontSize: 11 }}
              axisLine={{ stroke: "#000000", strokeWidth: 3 }}
              tickLine={{ stroke: "#000000", strokeWidth: 2 }}
              width={56}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,0,0,0.06)" }} />
            <Bar dataKey="value" stroke="#000000" strokeWidth={3} maxBarSize={110} isAnimationActive={false}>
              {data.map((entry) => (
                <Cell key={entry.tier} fill={TIER_META[entry.tier].fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
