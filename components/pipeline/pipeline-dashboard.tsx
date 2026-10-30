"use client"

import { useEffect, useMemo, useState } from "react"
import { Building2, Check, Flame, Home, Loader2, RefreshCw, Snowflake, Star, Target, Trophy, Wallet, X } from "lucide-react"
import { currency, percent, getDashboardSummary, type Agent, type Client, type DeduplicatedClient, type Property, type Tier } from "@/lib/pipeline-data"
import { fetchDeduplicatedClients, fetchPipelineClients, fetchProperties } from "@/lib/fetch-pipeline-data"
import { StatCard } from "./stat-card"
import { CountUp } from "@/components/animation/count-up"
import { SegmentPills, type SegmentFilter } from "./segment-pills"
import { ClientTable } from "./client-table"
import { ClientDetailModal } from "./client-detail-drawer"
import { PropertyDetailModal } from "./property-detail-drawer"
import { TierValueChart } from "./tier-value-chart"
import { PriorityMatrixChart } from "./priority-matrix-chart"
import { NeighborhoodTierHeatmap } from "./neighborhood-tier-heatmap"
import { AnalyticsInsightPanel } from "./analytics-insight-panel"
import { AnalyticsFilters, type AnalyticsTierFilter, type NeighborhoodFilter } from "./analytics-filters"
import { TabNav, type DashboardTab } from "./tab-nav"
import { AgentMenu, AgentSelector } from "./agent-menu"
import { PropertyCards } from "./property-cards"
import { ShortlistModal } from "./shortlist-modal"
import { InviteModal } from "./invite-modal"
import { ViewingsBoard } from "./viewings-board"
import { RecentSignalsPanel } from "./recent-signals-panel"
import { DailyWorklistPanel } from "./daily-worklist-panel"
import { AIBriefingHero } from "./ai-briefing-hero"
import { AnimatedContent } from "@/components/animation/animated-content"
import { MarketMovementsPanel } from "./market-movements-panel"
import { MarketSimulatorPanel } from "./market-simulator-panel"
import { displayPrice, potentialPipeline, simulatedPriceMap } from "@/lib/display-price"
import { toSimPairs, currentTick } from "@/lib/market-sim"
import { ModelTrainingPanel } from "./model-training-panel"
import { PipelineProjectionCard } from "./pipeline-projection-card"
import { WhatsAppFloatingPanel } from "./whatsapp-floating-panel"
import { PriorityInquiries } from "./priority-inquiries"

interface PipelineDashboardProps {
  onLogout?: () => void
}


function HeroStatCard({
  totalPipelineValue,
  dedupCount,
  syncTimestamp,
  unpricedCount,
  hasDisplayPrice,
}: {
  totalPipelineValue: number | null
  dedupCount: number
  syncTimestamp: number
  unpricedCount?: number
  hasDisplayPrice?: boolean
}) {
  return (
    <AnimatedContent delay={0} className="sm:col-span-2">
      <div className="relative flex h-full flex-col justify-between rounded-[var(--radius)] border border-l-[3px] border-l-neutral-300 border-border bg-card p-5 sm:p-7 shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-sm-hover)] transition-shadow duration-200">
        <div>
          <div className="flex items-start justify-between gap-3">
            <span className="text-xs sm:text-sm font-semibold uppercase tracking-wider text-muted-foreground pb-1">
              Total Pipeline Value
            </span>
            <span className="shrink-0 rounded-[8px] bg-black p-1.5 text-primary">
              <Wallet className="h-4 w-4" strokeWidth={2.5} />
            </span>
          </div>
          <div className="mt-4 font-display text-4xl font-bold leading-none tracking-tight sm:text-5xl lg:text-6xl">
            {totalPipelineValue !== null ? (
              <CountUp value={totalPipelineValue} formatNumber={currency} triggerKey={syncTimestamp} />
            ) : hasDisplayPrice ? (
              currency(0)
            ) : (
              "Awaiting quotes"
            )}
          </div>
          {!hasDisplayPrice && unpricedCount && unpricedCount > 0 ? (
            <div className="mt-1 font-mono text-xs font-bold text-amber-600">
              {unpricedCount} robot{unpricedCount === 1 ? "" : "s"} awaiting quotes
            </div>
          ) : null}
        </div>
        <div className="mt-4 inline-flex w-fit items-center rounded-[var(--radius-sm)] border border-border bg-secondary/80 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Sum of E(x) across {dedupCount} unique clients
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
  const [currentTickState, setCurrentTickState] = useState<number | null>(null)

  useEffect(() => {
    const updateTick = () => {
      const now = Date.now()
      const t = currentTick(now)
      setCurrentTickState((prev) => (prev !== t ? t : prev))
    }
    updateTick()
    const timer = setInterval(updateTick, 60000)
    return () => clearInterval(timer)
  }, [])

  // ── Agent selector state ──
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [selectedAgent,   setSelectedAgent]   = useState<Agent | null>(null)

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
  const [openClientSchedule, setOpenClientSchedule] = useState(false)
  const [selectedProperty,  setSelectedProperty]  = useState<Property | null>(null)
  const [shortlistProperty, setShortlistProperty] = useState<Property | null>(null)
  const [inviteTarget,      setInviteTarget]      = useState<{
    clientId: string
    propertyId: string
    clientName: string
    propertyName: string
    whatsappNumber?: string | null
  } | null>(null)

  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  // ── Prediction accuracy (outcome tracking) ──
  const [accuracy, setAccuracy] = useState<{
    total_recorded: number
    won_count?: number
    lost_count?: number
    avg_predicted_probability_when_won?: number
    avg_predicted_probability_when_lost?: number
    message?: string
  } | null>(null)

  const refreshAccuracy = () => {
    fetch("/api/prediction_accuracy")
      .then((r) => r.json())
      .then(setAccuracy)
      .catch(() => {})
  }

  useEffect(() => { refreshAccuracy() }, [])

  // Also refetch on tab focus (e.g. user switches away and back)
  useEffect(() => {
    window.addEventListener("focus", refreshAccuracy)
    return () => window.removeEventListener("focus", refreshAccuracy)
  }, [])

  async function loadData(agentId?: string | null) {
    setLoading(true)
    setError(null)
    try {
      const id = agentId !== undefined ? agentId : selectedAgentId
      const [dedup, raw, propertyRows] = await Promise.all([
        fetchDeduplicatedClients(id),
        fetchPipelineClients(id),
        fetchProperties(id),
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
    loadData(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Refetch whenever the agent selection changes
  useEffect(() => {
    loadData(selectedAgentId)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgentId])

  async function handleSync() {
    setSyncing(true)
    setSyncMsg(null)
    try {
      await fetch("/api/re-evaluate", { method: "POST" })
      await loadData(selectedAgentId)
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

  const simPairs = useMemo(() => toSimPairs(rawClients), [rawClients])

  const simPrices = useMemo(() => {
    return currentTickState !== null ? simulatedPriceMap(properties, currentTickState) : {}
  }, [properties, currentTickState])

  const { displayPriceMap, hasAnyDisplayPrice } = useMemo(() => {
    const map: Record<string, number | null> = {}
    let hasPrice = false
    for (const p of properties) {
      const sim = simPrices[p.id] ?? null
      const disp = displayPrice(p.value, p.indicativePriceMyr, sim)
      map[p.id] = disp.value
      if (disp.kind !== "none") hasPrice = true
    }
    return { displayPriceMap: map, hasAnyDisplayPrice: hasPrice }
  }, [properties, simPrices])

  const potentialPipe = useMemo(() => {
    return potentialPipeline(simPairs, displayPriceMap)
  }, [simPairs, displayPriceMap])

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

  // ── Select property by ID (from Analytics charts or Market Movements) ──
  const handleSelectPropertyById = (
    propertyId: string,
    fallbackInfo?: { address?: string; neighborhood?: string; value?: number }
  ) => {
    let prop = properties.find((p) => p.id === propertyId)
    if (!prop) {
      const match = rawClients.find((c) => c.propertyDbId === propertyId)
      if (match) {
        prop = {
          id: propertyId,
          name: match.property,
          address: match.property,
          neighborhood: match.agent,
          value: match.propertyValue,
          status: "LISTED",
        }
      } else if (fallbackInfo) {
        prop = {
          id: propertyId,
          name: fallbackInfo.address || "Property",
          address: fallbackInfo.address || "Property",
          neighborhood: fallbackInfo.neighborhood || "",
          value: fallbackInfo.value || 0,
          status: "LISTED",
        }
      }
    }
    if (prop) {
      setSelectedProperty(prop)
    }
  }

  return (
    <main className="min-h-screen bg-transparent px-4 py-6 sm:px-6 sm:py-10 lg:px-10">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 sm:gap-8">
        <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[8px] bg-black">
              <Building2 className="h-5 w-5 text-primary" strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-sans text-xl font-bold leading-none tracking-tight sm:text-2xl">
                PIPELINE<span className="text-muted-foreground">.EV</span>
              </div>
              <div className="text-[11px] font-black uppercase tracking-wider text-muted-foreground">
                Adoption Priority Console
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {syncMsg && (
              <span className="rounded-[var(--radius-sm)] border border-primary bg-primary px-3 py-1.5 text-xs font-semibold uppercase tracking-wider shadow-[var(--shadow-xs)]">
                {syncMsg}
              </span>
            )}
            <button
              type="button"
              disabled={syncing || loading}
              onClick={handleSync}
              className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-border bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wider shadow-[var(--shadow-xs)] transition-shadow duration-150 hover:shadow-[var(--shadow-sm)] disabled:opacity-50 sm:px-4"
              title="Re-run evaluation engine against Supabase and refresh data"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin text-black" : "text-black"}`} strokeWidth={2.5} />
              {syncing ? "Syncing..." : "Sync & Re-evaluate"}
            </button>
            <AgentSelector
              selectedAgentId={selectedAgentId}
              onChange={(id) => {
                setSelectedAgentId(id)
                // selectedAgent will be resolved by AgentSelector internally;
                // mirror it here for the profile drawer via a quick agents lookup.
                if (id === null) {
                  setSelectedAgent(null)
                }
              }}
            />
            <AgentMenu onLogout={onLogout} selectedAgent={selectedAgent} />
          </div>
        </header>

        {/* Tab navigation */}
        <TabNav active={tab} onChange={setTab} />

        {loading ? (
          <div className="flex flex-col items-center justify-center gap-4 rounded-[var(--radius)] border border-border bg-white py-24 shadow-[var(--shadow-sm)]">
            <Loader2 className="h-8 w-8 animate-spin text-foreground" strokeWidth={2} />
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Loading pipeline data…
            </p>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="rounded-[var(--radius)] border border-border bg-card p-6 shadow-[var(--shadow-sm)]">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-foreground">
                  Database Connection Error
                </p>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  {error}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Unable to reach Supabase database. If you are connected to a campus or public Wi-Fi hotspot, please log in to the Wi-Fi portal first, then retry.
                </p>
              </div>
              <button
                type="button"
                onClick={() => loadData(selectedAgentId)}
                className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[8px] border border-border bg-black px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-[var(--shadow-xs)] transition-all hover:bg-neutral-800 hover:shadow-[var(--shadow-sm)]"
              >
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={2.5} />
                Retry Connection
              </button>
            </div>
          </div>
        ) : null}

        {!loading && !error ? (
          <>
            {/* Dashboard tab */}
            {tab === "DASHBOARD" ? (
              <>
                <PipelineProjectionCard
                  agentId={selectedAgentId}
                  agentName={selectedAgent?.name}
                  syncTimestamp={syncTimestamp}
                  potentialPipeline={potentialPipe}
                />
                <PriorityInquiries
                  onOpenClient={(clientId) => {
                    const found = dedupClients.find((c) => c.clientId === clientId)
                    if (found) {
                      setSelectedClient(found)
                    }
                  }}
                />
                <DailyWorklistPanel
                  agentId={selectedAgentId}
                  onGenerateInvite={(clientId, propertyId) => {
                    const client = dedupClients.find((c) => c.clientId === clientId)
                    const prop = properties.find((p) => p.id === propertyId)
                    const clientName = client?.name || "Client"
                    const propName = prop?.address || prop?.name || "Property"
                    setLastInvite(clientName)
                    setInviteTarget({
                      clientId,
                      propertyId,
                      clientName,
                      propertyName: propName,
                      whatsappNumber: client?.whatsappNumber ?? null,
                    })
                  }}
                  onScheduleViewing={(clientId, propertyId) => {
                    const client = dedupClients.find((c) => c.clientId === clientId)
                    if (client) {
                      setOpenClientSchedule(true)
                      setSelectedClient(client)
                    }
                  }}
                />
                <RecentSignalsPanel
                  onOpenClient={(clientId) => {
                    const found = dedupClients.find((c) => c.clientId === clientId)
                    if (found) {
                      setSelectedClient(found)
                    }
                  }}
                  onOpenProperty={(propertyId) => {
                    const found = properties.find((p) => p.id === propertyId)
                    if (found) {
                      setSelectedProperty(found)
                    }
                  }}
                />
                <section className="grid grid-cols-1 gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-4">

                  <HeroStatCard
                    totalPipelineValue={totals.totalPipelineValue}
                    unpricedCount={totals.unpricedPipelineCount}
                    dedupCount={dedupClients.length}
                    syncTimestamp={syncTimestamp}
                    hasDisplayPrice={hasAnyDisplayPrice}
                  />

                  <StatCard
                    label="High-Fit Prospects"
                    numericValue={totals.byTier.TIER_1}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Ready for outreach."
                    icon={<Star className="h-4 w-4" strokeWidth={2.5} />}
                    accent="yellow"
                    index={1}
                    triggerKey={syncTimestamp}
                  />

                  <StatCard
                    label="Avg. Adoption Probability"
                    numericValue={totals.avgProbability}
                    formatNumber={percent}
                    detail="Across full active pipeline"
                    icon={<Target className="h-4 w-4" strokeWidth={2.5} />}
                    accent="gray"
                    index={2}
                    triggerKey={syncTimestamp}
                  />
                </section>

                <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <StatCard
                    label="Tier 2 · Possible-Fit"
                    numericValue={totals.byTier.TIER_2}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Needs demo sequence"
                    icon={<Flame className="h-4 w-4" strokeWidth={2.5} />}
                    accent="gray"
                    index={3}
                    triggerKey={syncTimestamp}
                  />
                  <StatCard
                    label="Tier 3 · Low-Fit"
                    numericValue={totals.byTier.TIER_3}
                    formatNumber={(n) => String(Math.round(n))}
                    detail="Low near-term adoption"
                    icon={<Snowflake className="h-4 w-4" strokeWidth={2.5} />}
                    accent="gray"
                    index={4}
                    triggerKey={syncTimestamp}
                  />
                  <StatCard
                    label="Total Fleet Value"
                    numericValue={totals.totalPropertyValue}
                    formatNumber={currency}
                    detail="Combined robot units"
                    icon={<Home className="h-4 w-4" strokeWidth={2.5} />}
                    accent="gray"
                    index={5}
                    triggerKey={syncTimestamp}
                    hasDisplayPrice={hasAnyDisplayPrice}
                  />
                </section>

                {/* Prediction Accuracy card */}
                <section className="grid grid-cols-1 gap-4 sm:gap-6">
                  <AnimatedContent delay={0}>
                    <div className="relative flex flex-col gap-3 rounded-[var(--radius)] border border-border bg-white p-5 shadow-[var(--shadow-sm)] sm:p-6">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className="rounded-[8px] bg-foreground p-1.5 text-primary">
                            <Trophy className="h-4 w-4" strokeWidth={2} />
                          </span>
                          <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground sm:text-xs">
                            Prediction Accuracy
                          </span>
                        </div>
                        {accuracy && accuracy.total_recorded > 0 && (
                          <span className="rounded-[var(--radius-sm)] bg-primary px-2 py-0.5 font-mono text-xs font-semibold">
                            {accuracy.total_recorded} recorded
                          </span>
                        )}
                      </div>

                      {!accuracy || accuracy.total_recorded === 0 ? (
                        <div className="text-sm font-bold text-muted-foreground">
                          No outcomes recorded yet — mark a client <span className="font-black text-black">Won</span> or <span className="font-black text-black">Lost</span> in their detail panel to start tracking.
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                           <div className="rounded-[var(--radius-sm)] border border-l-[3px] border-l-primary border-border bg-card p-3.5 shadow-[var(--shadow-xs)]">
                             <div className="flex items-center justify-between gap-2">
                               <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Deals Won</span>
                               <span className="flex h-5 w-5 items-center justify-center rounded-[6px] bg-primary text-black">
                                 <Check className="h-3.5 w-3.5" strokeWidth={3} />
                               </span>
                             </div>
                             <div className="mt-1.5 font-display text-2xl font-bold">{accuracy.won_count ?? 0}</div>
                             {accuracy.avg_predicted_probability_when_won !== undefined && (
                               <div className="mt-1 text-[11px] text-muted-foreground">
                                 Avg predicted{" "}
                                 <span className="font-semibold text-foreground">{accuracy.avg_predicted_probability_when_won}%</span>
                               </div>
                             )}
                           </div>
                           <div className="rounded-[var(--radius-sm)] border border-l-[3px] border-l-neutral-300 border-border bg-card p-3.5 shadow-[var(--shadow-xs)]">
                             <div className="flex items-center justify-between gap-2">
                               <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Deals Lost</span>
                               <span className="flex h-5 w-5 items-center justify-center rounded-[6px] border border-neutral-300 bg-transparent text-muted-foreground">
                                 <X className="h-3.5 w-3.5" strokeWidth={2.5} />
                               </span>
                             </div>
                             <div className="mt-1.5 font-display text-2xl font-bold">{accuracy.lost_count ?? 0}</div>
                             {accuracy.avg_predicted_probability_when_lost !== undefined && (
                               <div className="mt-1 text-[11px] text-muted-foreground">
                                 Avg predicted{" "}
                                 <span className="font-semibold text-foreground">{accuracy.avg_predicted_probability_when_lost}%</span>
                               </div>
                             )}
                           </div>
                           <div className="rounded-[var(--radius-sm)] border border-l-[3px] border-l-primary border-border bg-card p-3.5 shadow-[var(--shadow-xs)]">
                             <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Model Signal</div>
                             <div className="mt-1.5 font-mono text-sm font-semibold leading-tight text-foreground">
                               {accuracy.avg_predicted_probability_when_won !== undefined && accuracy.avg_predicted_probability_when_lost !== undefined ? (
                                 <>Won @ {accuracy.avg_predicted_probability_when_won}% &middot; Lost @ {accuracy.avg_predicted_probability_when_lost}%</>
                               ) : "—"}
                             </div>
                             <div className="mt-1 text-[10px] text-muted-foreground">
                               {accuracy.avg_predicted_probability_when_won !== undefined && accuracy.avg_predicted_probability_when_lost !== undefined && accuracy.avg_predicted_probability_when_won > accuracy.avg_predicted_probability_when_lost
                                 ? "Model is discriminating correctly ✓"
                                 : accuracy.total_recorded < 3 ? "Need more outcomes to assess" : "Review model calibration"}
                             </div>
                           </div>
                        </div>
                      )}
                    </div>
                  </AnimatedContent>

                  <AnimatedContent delay={0}>
                    <ModelTrainingPanel />
                  </AnimatedContent>
                </section>
              </>
            ) : null}

            {/* Analytics tab */}
            {tab === "ANALYTICS" ? (
              <section className="flex flex-col gap-8">
                {/* AI Insight panel — auto-refreshes on filter change (Anchor: signature black header) */}
                <AnalyticsInsightPanel
                  clients={analyticsClients}
                  activeFilters={{ tier: analyticsTier, neighborhood: analyticsNeighborhood }}
                />

                {/* Filter controls — Lighter panel */}
                <AnalyticsFilters
                  allClients={deduplicatedRawClients}
                  tierFilter={analyticsTier}
                  onTierChange={setAnalyticsTier}
                  neighborhoodFilter={analyticsNeighborhood}
                  onNeighborhoodChange={setAnalyticsNeighborhood}
                  filteredCount={analyticsClients.length}
                />

                {/* Treemap with inline AI analysis — Lighter panel */}
                <TierValueChart clients={analyticsClients} />

                {/* Priority Matrix with inline AI analysis — Lighter panel */}
                <PriorityMatrixChart
                  clients={analyticsClients}
                  properties={properties}
                  onSelectProperty={handleSelectPropertyById}
                />

                {/* Heatmap with inline AI analysis — Lighter panel */}
                <NeighborhoodTierHeatmap clients={analyticsClients} />

                {/* Market Movements — price volatility across all listings */}
                <MarketMovementsPanel
                  onSimulateComplete={loadData}
                  onSelectProperty={handleSelectPropertyById}
                />

                <MarketSimulatorPanel pairs={rawClients} robots={properties} displayPrices={displayPriceMap} />
              </section>
            ) : null}

            {/* Properties tab */}
            {tab === "PROPERTIES" ? (
              <section>
                <PropertyCards
                  properties={properties}
                  displayPriceMap={displayPriceMap}
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
                    <div className="rounded-[var(--radius-sm)] border border-primary bg-primary px-4 py-2 text-xs font-semibold uppercase tracking-wider shadow-[var(--shadow-xs)] sm:text-sm">
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
                        whatsappNumber: client.whatsappNumber ?? null,
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

        <footer className="border-t border-border pt-5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          E(x) = P(Adopt) × Unit Cost — Segmentation: Tier 1 E(x) &gt; RM50K &amp; prob ≥ 65% · Tier 2 prob ≥
          35% · Tier 3 &lt; 35%
        </footer>
      </div>

      {/* ── Global modals ── */}
      <ClientDetailModal
        client={selectedClient}
        open={selectedClient !== null}
        onClose={() => {
          setSelectedClient(null)
          setOpenClientSchedule(false)
        }}
        initialScheduleViewing={openClientSchedule}
        onGenerateInvite={(client) => {
          setLastInvite(client.name)
          setInviteTarget({
            clientId: client.clientId,
            propertyId: client.bestMatch.propertyId,
            clientName: client.name,
            propertyName: client.bestMatch.property,
            whatsappNumber: client.whatsappNumber ?? null,
          })
        }}
        onOutcomeRecorded={() => {
          refreshAccuracy()
          loadData(selectedAgentId)
        }}
        onStageChanged={() => {
          loadData(selectedAgentId)
        }}
      />
      <PropertyDetailModal
        property={selectedProperty}
        currentTick={currentTickState}
        displayPriceMap={displayPriceMap}
        open={selectedProperty !== null}
        onClose={() => setSelectedProperty(null)}
        onFindBuyers={() => {
          setShortlistProperty(selectedProperty)
          setSelectedProperty(null)
        }}
        onPriceChanged={(propertyId, newVal) => {
          setProperties((prev) =>
            prev.map((p) =>
              p.id === propertyId
                ? {
                    ...p,
                    value: newVal,
                    lastPriceChangeAt: new Date().toISOString(),
                    lastPriceChangePct: p.value ? (newVal - p.value) / p.value : undefined,
                  }
                : p
            )
          )
          if (selectedProperty && selectedProperty.id === propertyId) {
            setSelectedProperty((prev) =>
              prev
                ? {
                    ...prev,
                    value: newVal,
                    lastPriceChangeAt: new Date().toISOString(),
                    lastPriceChangePct: prev.value ? (newVal - prev.value) / prev.value : undefined,
                  }
                : null
            )
          }
          // Refresh client probabilities and pipeline data in the background
          loadData()
        }}
      />

      <ShortlistModal
        property={shortlistProperty}
        displayPriceMap={displayPriceMap}
        open={shortlistProperty !== null}
        onClose={() => setShortlistProperty(null)}
        agentId={selectedAgentId}
        onGenerateInvite={(entry) => {
          if (!shortlistProperty) return
          const client = dedupClients.find((c) => c.clientId === entry.clientId)
          setLastInvite(entry.name)
          setInviteTarget({
            clientId: entry.clientId,
            propertyId: shortlistProperty.id,
            clientName: entry.name,
            propertyName: shortlistProperty.address,
            whatsappNumber: client?.whatsappNumber ?? null,
          })
        }}
      />
      <InviteModal
        clientId={inviteTarget?.clientId ?? null}
        propertyId={inviteTarget?.propertyId ?? null}
        clientName={inviteTarget?.clientName ?? null}
        propertyName={inviteTarget?.propertyName ?? null}
        whatsappNumber={inviteTarget?.whatsappNumber ?? null}
        agentId={selectedAgentId}
        open={inviteTarget !== null}
        onClose={() => setInviteTarget(null)}
        onMarkSent={() => loadData(selectedAgentId)}
      />

      {/* Floating draggable WhatsApp outreach & live messaging panel */}
      <WhatsAppFloatingPanel clients={dedupClients} agentId={selectedAgentId} />
    </main>
  )
}
