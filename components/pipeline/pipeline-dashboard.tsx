"use client"

import { useMemo, useState } from "react"
import { Building2, Flame, Home, Snowflake, Star, Target, Wallet } from "lucide-react"
import { CLIENTS, currency, type Tier } from "@/lib/pipeline-data"
import { StatCard } from "./stat-card"
import { SegmentPills, type SegmentFilter } from "./segment-pills"
import { ClientTable } from "./client-table"
import { TierValueChart } from "./tier-value-chart"
import { TabNav, type DashboardTab } from "./tab-nav"
import { AgentMenu } from "./agent-menu"
import { PropertyCards } from "./property-cards"

export function PipelineDashboard() {
  const [tab, setTab] = useState<DashboardTab>("DASHBOARD")
  const [filter, setFilter] = useState<SegmentFilter>("ALL")
  const [lastInvite, setLastInvite] = useState<string | null>(null)

  const totals = useMemo(() => {
    const totalPipelineValue = CLIENTS.reduce((sum, c) => sum + c.expectedValue, 0)
    const totalPropertyValue = CLIENTS.reduce((sum, c) => sum + c.propertyValue, 0)
    const byTier = CLIENTS.reduce(
      (acc, c) => {
        acc[c.tier] += 1
        return acc
      },
      { TIER_1: 0, TIER_2: 0, TIER_3: 0 } as Record<Tier, number>,
    )
    const avgProbability = CLIENTS.reduce((sum, c) => sum + c.probability, 0) / CLIENTS.length
    return { totalPipelineValue, totalPropertyValue, byTier, avgProbability }
  }, [])

  const counts: Record<SegmentFilter, number> = {
    ALL: CLIENTS.length,
    TIER_1: totals.byTier.TIER_1,
    TIER_2: totals.byTier.TIER_2,
    TIER_3: totals.byTier.TIER_3,
  }

  const filteredClients = useMemo(() => {
    if (filter === "ALL") return CLIENTS
    return CLIENTS.filter((c) => c.tier === filter)
  }, [filter])

  return (
    <main className="min-h-screen bg-background px-4 py-6 sm:px-6 sm:py-10 lg:px-10">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 sm:gap-8">
        {/* Header */}
        <header className="flex flex-col gap-4 border-b-4 border-black pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center border-4 border-black bg-black">
              <Building2 className="h-5 w-5 text-primary" strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-sans text-xl font-bold leading-none tracking-tight sm:text-2xl">
                PIPELINE<span className="text-muted-foreground">.EV</span>
              </div>
              <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
                Client Priority Console
              </div>
            </div>
          </div>

          <AgentMenu />
        </header>

        {/* Tab navigation */}
        <TabNav active={tab} onChange={setTab} />

        {/* Dashboard tab */}
        {tab === "DASHBOARD" ? (
          <>
            <section className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">
              <div className="relative flex flex-col justify-between overflow-hidden border-4 border-black bg-white p-5 sm:col-span-2 sm:p-7 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
                <div className="stripes-diagonal absolute inset-0" />
                <div className="relative z-10">
                  <div className="flex items-start justify-between gap-3">
                    <span className="inline-block border-2 border-black bg-white px-3 py-1 text-xs font-black uppercase tracking-wider sm:text-sm">
                      Total Pipeline Value
                    </span>
                    <span className="shrink-0 border-2 border-black bg-black p-1.5 text-primary">
                      <Wallet className="h-4 w-4" strokeWidth={2.5} />
                    </span>
                  </div>
                  <div className="mt-4 font-sans text-5xl font-bold leading-[0.9] tracking-tight sm:text-6xl lg:text-7xl">
                    {currency(totals.totalPipelineValue)}
                  </div>
                  <div className="mt-4 inline-block border-4 border-black bg-primary px-4 py-2 text-xs font-black uppercase tracking-wider shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] sm:text-sm">
                    Sum of E(x) across {CLIENTS.length} active clients
                  </div>
                </div>
              </div>

              <StatCard
                label="Total VIPs"
                value={String(totals.byTier.TIER_1)}
                detail="Tier 1 clients ready for invite"
                icon={<Star className="h-4 w-4" strokeWidth={2.5} />}
                emphasis
              />

              <StatCard
                label="Avg. Buy Probability"
                value={`${Math.round(totals.avgProbability * 100)}%`}
                detail="Across full active pipeline"
                icon={<Target className="h-4 w-4" strokeWidth={2.5} />}
              />
            </section>

            <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatCard
                label="Tier 2 · Warm"
                value={String(totals.byTier.TIER_2)}
                detail="Needs nurture sequence"
                icon={<Flame className="h-4 w-4" strokeWidth={2.5} />}
              />
              <StatCard
                label="Tier 3 · Cold"
                value={String(totals.byTier.TIER_3)}
                detail="Low near-term conversion"
                icon={<Snowflake className="h-4 w-4" strokeWidth={2.5} />}
              />
              <StatCard
                label="Total Property Value"
                value={currency(totals.totalPropertyValue)}
                detail="Combined target listings"
                icon={<Home className="h-4 w-4" strokeWidth={2.5} />}
              />
            </section>
          </>
        ) : null}

        {/* Analytics tab */}
        {tab === "ANALYTICS" ? (
          <section>
            <TierValueChart tall />
          </section>
        ) : null}

        {/* Properties tab */}
        {tab === "PROPERTIES" ? (
          <section>
            <PropertyCards />
          </section>
        ) : null}

        {/* Clients tab */}
        {tab === "CLIENTS" ? (
          <>
            <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <SegmentPills active={filter} onChange={setFilter} counts={counts} />
              {lastInvite ? (
                <div className="border-2 border-black bg-primary px-4 py-2 text-xs font-black uppercase tracking-wider shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] sm:text-sm">
                  Invite generated for {lastInvite}
                </div>
              ) : null}
            </section>

            <section>
              <ClientTable clients={filteredClients} onGenerateInvite={(client) => setLastInvite(client.name)} />
            </section>
          </>
        ) : null}

        <footer className="border-t-4 border-black pt-5 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          E(x) = P(Buy) × Property Value — Segmentation: Tier 1 ≥ 65% · Tier 2 35–64% · Tier 3 &lt; 35%
        </footer>
      </div>
    </main>
  )
}
