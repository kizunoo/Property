"use client"

import { Treemap, ResponsiveContainer, Tooltip } from "recharts"
import { LayoutDashboard } from "lucide-react"
import { currency, getDashboardSummary, type Client, type Tier } from "@/lib/pipeline-data"

import { ScrollConnect } from "@/components/animation/scroll-connect"
import { useChartInsight, ChartInsightPanel } from "./chart-insight-panel"


const TIER_ORDER: Tier[] = ["TIER_1", "TIER_2", "TIER_3"]

const TIER_META: Record<Tier, { label: string; shortLabel: string; fill: string; textColor: string }> = {
  TIER_1: { label: "TIER 1 · VIP",  shortLabel: "VIP",  fill: "var(--primary)", textColor: "#000000" },
  TIER_2: { label: "TIER 2 · WARM", shortLabel: "WARM", fill: "#1a1a1a",        textColor: "#ffffff" },
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
    <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3 shadow-[0px_4px_16px_rgba(0,0,0,0.12)]">
      <div className="text-xs font-semibold uppercase tracking-wider">{item.label}</div>
      <div className="mt-1 font-mono text-lg font-bold">{currency(item.value)}</div>
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
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

  // Gap between segments: inset each cell by 2px on each side
  const gap = 3
  const rx = x + gap
  const ry = y + gap
  const rw = width - gap * 2
  const rh = height - gap * 2

  return (
    <g style={{ cursor: onTierClick ? "pointer" : "default" }} onClick={() => onTierClick?.(tier)}>
      {/* Soft gap achieved by insetting rect; thin 1px stroke instead of heavy 3px */}
      <rect x={rx} y={ry} width={rw} height={rh} fill={meta.fill} stroke="rgba(255,255,255,0.25)" strokeWidth={1} rx={4} ry={4} />
      {!isTiny && (
        <text
          x={x + width / 2} y={y + (isSmall ? height / 2 - 4 : height / 2 - 14)}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={isSmall ? 10 : 13} fontWeight={700}
          fontFamily="var(--font-sans)"
          style={{ userSelect: "none", textTransform: "uppercase", letterSpacing: "0.08em" }}
        >
          {meta.shortLabel}
        </text>
      )}
      {!isSmall && value !== undefined && (
        <text
          x={x + width / 2} y={y + height / 2 + 4}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={11} fontWeight={600}
          fontFamily="var(--font-sans)" opacity={0.85}
          style={{ userSelect: "none" }}
        >
          {currency(value)}
        </text>
      )}
      {!isSmall && count !== undefined && (
        <text
          x={x + width / 2} y={y + height / 2 + 22}
          textAnchor="middle" dominantBaseline="middle"
          fill={meta.textColor} fontSize={10} fontWeight={600}
          fontFamily="var(--font-sans)" opacity={0.7}
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
      <div className="overflow-hidden rounded-[10px] border border-neutral-200 bg-card shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
        <div
          className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-neutral-900 px-5 py-3.5 sm:px-6"
          style={{ borderRadius: "10px 10px 0 0" }}
        >
          <div className="flex items-center gap-2 text-white">
            <LayoutDashboard className="h-4 w-4" strokeWidth={2} />
            <span className="text-xs font-semibold uppercase tracking-wider sm:text-sm">
              Expected Value by Tier
            </span>
          </div>
          <span className="rounded-md bg-primary px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-black sm:text-xs">
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
