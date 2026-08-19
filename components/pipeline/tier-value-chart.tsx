"use client"

import { Treemap, ResponsiveContainer, Tooltip } from "recharts"
import { LayoutDashboard } from "lucide-react"
import { currency, getDashboardSummary, type Client, type Tier } from "@/lib/pipeline-data"

import { ScrollConnect } from "@/components/animation/scroll-connect"
import { useChartInsight, ChartInsightPanel } from "./chart-insight-panel"


const TIER_ORDER: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

const TIER_META: Record<Tier, { label: string; shortLabel: string; fill: string; textColor: string }> = {
  TIER_1: { label: "TIER 1 · VIP",  shortLabel: "VIP",  fill: "var(--primary)", textColor: "#000000" },
  TIER_2: { label: "TIER 2 · WARM", shortLabel: "WARM", fill: "#000000",        textColor: "#ffffff" },
  TIER_3: { label: "TIER 3 · COLD", shortLabel: "COLD", fill: "#c4c4c4",        textColor: "#000000" },
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────
interface TooltipPayload {
  active?: boolean
  payload?: { payload: { label: string; value: number; count: number } }[]
}

function TreeTooltip({ active, payload }: TooltipPayload) {
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

// ─── Custom treemap cell renderer ─────────────────────────────────────────────
interface TreeCellProps {
  x?: number
  y?: number
  width?: number
  height?: number
  tier?: Tier
  value?: number
  count?: number
  onTierClick?: (tier: Tier) => void
}

function TreeCell({ x = 0, y = 0, width = 0, height = 0, tier, value, count, onTierClick }: TreeCellProps) {
  if (!tier || width < 2 || height < 2) return null
  const meta = TIER_META[tier]
  const isSmall = width < 90 || height < 60
  const isTiny  = width < 55 || height < 40

  return (
    <g style={{ cursor: onTierClick ? "pointer" : "default" }} onClick={() => onTierClick?.(tier)}>
      <rect x={x + 2} y={y + 2} width={width - 4} height={height - 4} fill={meta.fill} stroke="#000000" strokeWidth={3} />
      {tier === "TIER_1" && !isTiny && (
        <rect x={x + 6} y={y + 6} width={width - 12} height={4} fill="rgba(0,0,0,0.15)" />
      )}
      {!isTiny && (
        <text
          x={x + width / 2} y={y + (isSmall ? height / 2 - 4 : height / 2 - 14)}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={isSmall ? 10 : 13} fontWeight={900}
          fontFamily="var(--font-space-mono, monospace)"
          style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: "0.08em" }}
        >
          {meta.shortLabel}
        </text>
      )}
      {!isSmall && value !== undefined && (
        <text
          x={x + width / 2} y={y + height / 2 + 4}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={11} fontWeight={700}
          fontFamily="var(--font-space-mono, monospace)" opacity={0.85}
          style={{ userSelect: "none" }}
        >
          {currency(value)}
        </text>
      )}
      {!isSmall && count !== undefined && (
        <text
          x={x + width / 2} y={y + height / 2 + 22}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={10} fontWeight={700}
          fontFamily="var(--font-space-mono, monospace)" opacity={0.7}
          style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: "0.06em" }}
        >
          {count} {count === 1 ? "client" : "clients"}
        </text>
      )}
    </g>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────
interface TierValueChartProps {
  clients: Client[]
  onTierClick?: (tier: Tier) => void
}

export function TierValueChart({ clients, onTierClick }: TierValueChartProps) {
  const { insight, loading, fetchInsight } = useChartInsight()
  // Single shared aggregation — same deduplication logic as Dashboard stat cards
  const { byTier, byTierEx } = getDashboardSummary(clients)

  const rawData = TIER_ORDER.map((tier) => ({
    tier,
    label: TIER_META[tier].label,
    value: byTierEx[tier],
    count: byTier[tier],
  })).filter((d) => d.value > 0)

  const treeChildren = rawData.map((d) => ({ ...d, name: d.label, size: d.value }))

  const handleCellClick = (tier: Tier) => {
    fetchInsight("tier", { tier })
    if (onTierClick) onTierClick(tier)
  }

  return (
    <ScrollConnect>
      <div className="border-4 border-black bg-card shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div className="flex items-center justify-between gap-3 border-b-4 border-black bg-black px-5 py-3.5 sm:px-6">
          <div className="flex items-center gap-2 text-white">
            <LayoutDashboard className="h-4 w-4" strokeWidth={2.5} />
            <span className="text-xs font-black uppercase tracking-wider sm:text-sm">
              Expected Value by Tier
            </span>
          </div>
          <span className="border-2 border-black bg-primary px-2.5 py-1 text-[10px] font-black uppercase tracking-wider text-black sm:text-xs">
            Click segment for AI analysis
          </span>
        </div>

        <div className="p-4 sm:p-5">
          <div className="h-[280px] sm:h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={treeChildren}
                dataKey="size"
                aspectRatio={4 / 3}
                isAnimationActive={true}
                animationDuration={600}
                animationEasing="ease-out"
                content={<TreeCell onTierClick={handleCellClick} />}
              >
                <Tooltip content={<TreeTooltip />} />
              </Treemap>
            </ResponsiveContainer>
          </div>
          <ChartInsightPanel insight={insight} loading={loading} />
        </div>
      </div>
    </ScrollConnect>
  )
}
