"use client"

import { useEffect, useMemo, useState } from "react"
import { Building2, Flame, Home, Loader2, RefreshCw, Snowflake, Star, Target, Wallet } from "lucide-react"
import { currency, percent, getDashboardSummary, type Client, type DeduplicatedClient, type Property, type Tier } from "@/lib/pipeline-data"
import { fetchDeduplicatedClients, fetchPipelineClients, fetchProperties } from "@/lib/fetch-pipeline-data"
import { StatCard } from "./stat-card"
import { CountUp } from "@/components/animation/count-up"
import { GlitchLabel } from "@/components/animation/glitch-label"
import { SegmentPills, type SegmentFilter } from "./segment-pills"
import { ClientTable } from "./client-table"
import { ClientDetailModal } from "./client-detail-drawer"
import { PropertyDetailModal } from "./property-detail-drawer"
import { TierValueChart } from "./tier-value-chart"
import { PriorityMatrixChart } from "./priority-matrix-chart"
import { PipelineFunnel } from "./pipeline-funnel"
import { NeighborhoodTierHeatmap } from "./neighborhood-tier-heatmap"
import { AnalyticsInsightPanel } from "./analytics-insight-panel"
import { AnalyticsFilters, type AnalyticsTierFilter, type NeighborhoodFilter } from "./analytics-filters"
import { TabNav, type DashboardTab } from "./tab-nav"
import { AgentMenu } from "./agent-menu"
import { PropertyCards } from "./property-cards"
import { ShortlistModal } from "./shortlist-modal"
import { InviteModal } from "./invite-modal"
import { ViewingsBoard } from "./viewings-board"
import { RecentSignalsPanel } from "./recent-signals-panel"
import { AnimatedContent } from "@/components/animation/animated-content"


function HeroStatCard({ totalPipelineValue, dedupCount, syncTimestamp }: { totalPipelineValue: number; dedupCount: number; syncTimestamp: number }) {
  return (
    <AnimatedContent delay={0} className="sm:col-span-2">
      <div className="relative flex flex-col justify-between overflow-hidden border-4 border-black bg-white p-5 sm:p-7 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
        <div className="stripes-diagonal absolute inset-0" />
        <div className="relative z-10">
          <div className="flex items-start justify-between gap-3">
            <span className="inline-block border-2 border-black bg-white px-3 py-1 text-xs font-black uppercase tracking-wider sm:text-sm">
              <GlitchLabel text="Total Pipeline Value" triggerKey={syncTimestamp} />
            </span>
            <span className="shrink-0 border-2 border-black bg-black p-1.5 text-primary">
              <Wallet className="h-4 w-4" strokeWidth={2.5} />
            </span>
          </div>
          <div className="mt-4 font-sans text-5xl font-bold leading-[0.9] tracking-tight sm:text-6xl lg:text-7xl">
            <CountUp value={totalPipelineValue} formatNumber={currency} triggerKey={syncTimestamp} />
          </div>
          <div className="mt-4 inline-block border-4 border-black bg-primary px-4 py-2 text-xs font-black uppercase tracking-wider shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] sm:text-sm">
            Sum of E(x) across {dedupCount} unique clients
          </div>
        </div>
      </div>
    </AnimatedContent>
  )
}

export function PipelineDashboard({ onLogout }: PipelineDashboardProps) {
  const [tab, setTab]             = useState<DashboardTab>("DASHBOARD")
  const [filter, setFilter]       = useState<SegmentFilter>("ALL")
  const [lastInvite, setLastInvite] = useState<string | null>(null)
  const [syncTimestamp, setSyncTimestamp] = useState<number>(() => Date.now())

  // Raw Client[] for analytics charts (full rows, may include duplicates)
  const [rawClients, setRawClients]       = useState<Client[]>([])
  // Deduplicated for the Clients tab (1 row per unique client)
  const [dedupClients, setDedupClients]   = useState<DeduplicatedClient[]>([])
  const [properties, setProperties]       = useState<Property[]>([])
  const [loading, setLoading]             = useState(true)
  const [error, setError]                 = useState<string | null>(null)

  // ── Analytics-tab local filters ──
  const [analyticsTier, setAnalyticsTier]               = useState<AnalyticsTierFilter>("ALL")
  const [analyticsNeighborhood, setAnalyticsNeighborhood] = useState<NeighborhoodFilter>("ALL")

  // ── Modal selection state ──
  const [selectedClient,    setSelectedClient]    = useState<DeduplicatedClient | null>(null)
  const [selectedProperty,  setSelectedProperty]  = useState<Property | null>(null)
  const [shortlistProperty, setShortlistProperty] = useState<Property | null>(null)
  const [inviteTarget,      setInviteTarget]      = useState<{
    clientId: string
    propertyId: string
    clientName: string
    propertyName: string
  } | null>(null)

  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [dedup, raw, propertyRows] = await Promise.all([
        fetchDeduplicatedClients(),
        fetchPipelineClients(),
        fetchProperties(),
      ])
      setDedupClients(dedup)
      setRawClients(raw)
      setProperties(propertyRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline data")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  async function handleSync() {
    setSyncing(true)
    setSyncMsg(null)
    try {
      await fetch("/api/re-evaluate", { method: "POST" })
      await loadData()
      setSyncTimestamp(Date.now())
      setSyncMsg("Evaluations & DB synced successfully")
      setTimeout(() => setSyncMsg(null), 4000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed")
    } finally {
      setSyncing(false)
    }
  }

  // ── Dashboard stat totals — deduplicated via getDashboardSummary ──
  // Each client counted once (best-match row); each property counted once.
  const totals = useMemo(() => getDashboardSummary(rawClients), [rawClients])

  // ── Segment pill counts (off dedup for accurate unique-client count) ──
  const counts: Record<SegmentFilter, number> = {
    ALL:    dedupClients.length,
    TIER_1: dedupClients.filter((c) => c.tier === "TIER_1").length,
    TIER_2: dedupClients.filter((c) => c.tier === "TIER_2").length,
    TIER_3: dedupClients.filter((c) => c.tier === "TIER_3").length,
  }

  // ── Segment-filtered deduplicated clients for the table ──
  const filteredDedupClients = useMemo(() => {
    if (filter === "ALL") return dedupClients
    return dedupClients.filter((c) => c.tier === filter)
  }, [dedupClients, filter])

  // ── Deduplicated raw clients (one row per unique client: best match row) ──
  const deduplicatedRawClients = useMemo(() => {
    const seen = new Set<string>()
    return rawClients.filter((c) => {
      if (seen.has(c.clientDbId)) return false
      seen.add(c.clientDbId)
      return true
    })
  }, [rawClients])

  // ── Analytics clients (deduplicated per-client best match, filtered by tier + neighbourhood) ──
  const analyticsClients = useMemo(() => {
    return deduplicatedRawClients.filter((c) => {
      const tierOk = analyticsTier === "ALL" || c.tier === analyticsTier
      const nbhd = c.preferredNeighborhood ?? c.agent
      const nbhdOk = analyticsNeighborhood === "ALL" || nbhd === analyticsNeighborhood
      return tierOk && nbhdOk
    })
  }, [deduplicatedRawClients, analyticsTier, analyticsNeighborhood])

  return (
    <main className="min-h-screen bg-transparent px-4 py-6 sm:px-6 sm:py-10 lg:px-10">
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

          <div className="flex items-center gap-3">
            {syncMsg && (
              <span className="border-2 border-black bg-primary px-3 py-1.5 text-xs font-black uppercase tracking-wider shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                {syncMsg}
              </span>
            )}
            <button
              type="button"
              disabled={syncing || loading}
              onClick={handleSync}
              className="flex items-center gap-2 border-2 border-black bg-white px-3 py-2 text-xs font-black uppercase tracking-wider shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 sm:px-4"
              title="Re-run evaluation engine against Supabase and refresh data"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin text-black" : "text-black"}`} strokeWidth={2.5} />
              {syncing ? "Syncing..." : "Sync & Re-evaluate"}
            </button>
            <AgentMenu onLogout={onLogout} />
          </div>
        </header>

        {/* Tab navigation */}
        <TabNav active={tab} onChange={setTab} />

        {loading ? (
          <div className="flex flex-col items-center justify-center gap-4 border-4 border-black bg-white py-24 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <Loader2 className="h-8 w-8 animate-spin text-black" strokeWidth={2.5} />
            <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
              Loading pipeline data…
            </p>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="border-4 border-black bg-white p-6 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
            <p className="text-xs font-black uppercase tracking-wider text-black">Data Error</p>
            <p className="mt-2 text-sm font-bold text-muted-foreground">{error}</p>
          </div>
        ) : null}

        {!loading && !error ? (
          <>
            {/* Dashboard tab */}
            {tab === "DASHBOARD" ? (
              <>
                <RecentSignalsPanel onOpenClient={(clientId) => {
                  const found = dedupClients.find((c) => c.clientId === clientId)
                  if (found) {
                    setSelectedClient(found)
                  }
                }} />
                <section className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">

                  <HeroStatCard
                    totalPipelineValue={totals.totalPipelineValue}
                    dedupCount={dedupClients.length}
                    syncTimestamp={syncTimestamp}
                  />

                  <StatCard
                    label="Total VIPs"
                    numericValue={totals.byTier.TIER_1}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Tier 1 clients ready for invite"
                    icon={<Star className="h-4 w-4" strokeWidth={2.5} />}
                    emphasis
                    index={1}
                    triggerKey={syncTimestamp}
                  />

                  <StatCard
                    label="Avg. Buy Probability"
                    numericValue={totals.avgProbability}
                    formatNumber={percent}
                    detail="Across full active pipeline"
                    icon={<Target className="h-4 w-4" strokeWidth={2.5} />}
                    index={2}
                    triggerKey={syncTimestamp}
                  />
                </section>

                <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <StatCard
                    label="Tier 2 · Warm"
                    numericValue={totals.byTier.TIER_2}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Needs nurture sequence"
                    icon={<Flame className="h-4 w-4" strokeWidth={2.5} />}
                    index={3}
                    triggerKey={syncTimestamp}
                  />
                  <StatCard
                    label="Tier 3 · Cold"
                    numericValue={totals.byTier.TIER_3}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Low near-term conversion"
                    icon={<Snowflake className="h-4 w-4" strokeWidth={2.5} />}
                    index={4}
                    triggerKey={syncTimestamp}
                  />
                  <StatCard
                    label="Total Property Value"
                    numericValue={totals.totalPropertyValue}
                    formatNumber={currency}
                    detail="Combined target listings"
                    icon={<Home className="h-4 w-4" strokeWidth={2.5} />}
                    index={5}
                    triggerKey={syncTimestamp}
                  />
                </section>
              </>
            ) : null}

            {/* Analytics tab */}
            {tab === "ANALYTICS" ? (
              <section className="flex flex-col gap-6">
                {/* AI Insight panel — auto-refreshes on filter change */}
                <AnalyticsInsightPanel
                  clients={analyticsClients}
                  activeFilters={{ tier: analyticsTier, neighborhood: analyticsNeighborhood }}
                />

                <AnalyticsFilters
                  allClients={deduplicatedRawClients}
                  tierFilter={analyticsTier}
                  onTierChange={setAnalyticsTier}
                  neighborhoodFilter={analyticsNeighborhood}
                  onNeighborhoodChange={setAnalyticsNeighborhood}
                  filteredCount={analyticsClients.length}
                />

                {/* Treemap — click tier to jump to Clients tab filtered by that tier */}
                <TierValueChart
                  clients={analyticsClients}
                  onTierClick={(tier) => {
                    setFilter(tier)
                    setTab("CLIENTS")
                  }}
                />

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <PriorityMatrixChart clients={analyticsClients} />
                  <PipelineFunnel clients={analyticsClients} />
                </div>

                {/* Heatmap — click cell to jump to Clients tab filtered by tier (neighborhood filter stays in analytics) */}
                <NeighborhoodTierHeatmap
                  clients={analyticsClients}
                  onCellClick={(neighborhood, tier) => {
                    setAnalyticsNeighborhood(neighborhood)
                    setFilter(tier)
                    setTab("CLIENTS")
                  }}
                />
              </section>
            ) : null}

            {/* Properties tab */}
            {tab === "PROPERTIES" ? (
              <section>
                <PropertyCards
                  properties={properties}
                  onSelect={setSelectedProperty}
                  onFindBuyers={(p) => { setShortlistProperty(p) }}
                />
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
                  <ClientTable
                    clients={filteredDedupClients}
                    onGenerateInvite={(client) => {
                      setLastInvite(client.name)
                      setInviteTarget({
                        clientId: client.clientId,
                        propertyId: client.bestMatch.propertyId,
                        clientName: client.name,
                        propertyName: client.bestMatch.property,
                      })
                    }}
                    onSelect={setSelectedClient}
                  />
                </section>
              </>
            ) : null}

            {/* Viewings tab */}
            {tab === "VIEWINGS" ? (
              <section>
                <ViewingsBoard
                  dedupClients={dedupClients}
                  onNavigateToClients={() => setTab("CLIENTS")}
                />
              </section>
            ) : null}
          </>
        ) : null}

        <footer className="border-t-4 border-black pt-5 text-xs font-bold uppercase tracking-wider text-muted-foreground">
          E(x) = P(Buy) × Property Value — Segmentation: Tier 1 E(x) &gt; RM50K &amp; prob ≥ 65% · Tier 2 prob ≥
          35% · Tier 3 &lt; 35%
        </footer>
      </div>

      {/* ── Global modals ── */}
      <ClientDetailModal
        client={selectedClient}
        open={selectedClient !== null}
        onClose={() => setSelectedClient(null)}
        onGenerateInvite={(client) => {
          setLastInvite(client.name)
          setInviteTarget({
            clientId: client.clientId,
            propertyId: client.bestMatch.propertyId,
            clientName: client.name,
            propertyName: client.bestMatch.property,
          })
        }}
      />
      <PropertyDetailModal
        property={selectedProperty}
        open={selectedProperty !== null}
        onClose={() => setSelectedProperty(null)}
        onFindBuyers={() => {
          setShortlistProperty(selectedProperty)
          setSelectedProperty(null)
        }}
      />
      <ShortlistModal
        property={shortlistProperty}
        open={shortlistProperty !== null}
        onClose={() => setShortlistProperty(null)}
        onGenerateInvite={(entry) => {
          if (!shortlistProperty) return
          setLastInvite(entry.name)
          setInviteTarget({
            clientId: entry.clientId,
            propertyId: shortlistProperty.id,
            clientName: entry.name,
            propertyName: shortlistProperty.address,
          })
        }}
      />
      <InviteModal
        clientId={inviteTarget?.clientId ?? null}
        propertyId={inviteTarget?.propertyId ?? null}
        clientName={inviteTarget?.clientName ?? null}
        propertyName={inviteTarget?.propertyName ?? null}
        open={inviteTarget !== null}
        onClose={() => setInviteTarget(null)}
      />
    </main>
  )
}
