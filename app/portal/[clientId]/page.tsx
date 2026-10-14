"use client"

import { useEffect, useState, useCallback, Suspense } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { Bot, XCircle } from "lucide-react"

import { PortalShell } from "@/components/portal/portal-shell"
import type { PortalTab, DashboardData } from "@/lib/portal-types"
import { fetchDashboard, PortalApiError } from "@/lib/portal-api"

// ─── Lazy tab imports ─────────────────────────────────────────────────────────
// Each tab is a separate component so only the active one renders.
// All tab components live in components/portal/.

import { OverviewTab }  from "@/components/portal/tabs/overview-tab"
import { MatchesTab }   from "@/components/portal/tabs/matches-tab"
import { CatalogTab }   from "@/components/portal/tabs/catalog-tab"
import { ViewingsTab }  from "@/components/portal/tabs/viewings-tab"
import { ActivityTab }  from "@/components/portal/tabs/activity-tab"
import { MessagesTab }  from "@/components/portal/tabs/messages-tab"
import { ProfileTab }   from "@/components/portal/tabs/profile-tab"

// ─── Auth guard ───────────────────────────────────────────────────────────────

function usePortalAuth(clientId: string) {
  const router = useRouter()
  const [authChecked, setAuthChecked] = useState(false)
  const [sessionInfo, setSessionInfo] = useState<import("@/lib/portal-api").PortalMeData | null>(null)

  useEffect(() => {
    let active = true
    import("@/lib/portal-api").then(({ fetchAuthMe }) => {
      fetchAuthMe()
        .then((me) => {
          if (!active) return
          if (!me.authenticated || me.client_id !== clientId) {
            router.replace("/portal")
            return
          }
          setSessionInfo(me)
          setAuthChecked(true)
        })
        .catch(() => {
          if (active) router.replace("/portal")
        })
    })
    return () => {
      active = false
    }
  }, [clientId, router])

  return { authChecked, sessionInfo }
}

// ─── Tab routing ──────────────────────────────────────────────────────────────

const VALID_TABS: PortalTab[] = ["overview", "matches", "catalog", "viewings", "activity", "messages", "profile"]

function resolveTab(raw: string | null): PortalTab {
  if (raw && VALID_TABS.includes(raw as PortalTab)) return raw as PortalTab
  return "overview"
}

// ─── Loading skeleton ─────────────────────────────────────────────────────────

function PageSkeleton() {
  return (
    <main className="stripes-diagonal flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-12 w-12 items-center justify-center border border-border bg-card shadow-[var(--shadow-sm)] animate-pulse">
          <Bot className="h-6 w-6 text-muted-foreground" />
        </div>
        <p className="text-xs font-black uppercase tracking-wider text-muted-foreground">
          Loading your portal…
        </p>
      </div>
    </main>
  )
}

// ─── Error state ──────────────────────────────────────────────────────────────

function PageError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm border border-border bg-card p-8 shadow-[var(--shadow-md)] text-center">
        <XCircle className="mx-auto h-8 w-8 text-destructive mb-3" />
        <p className="text-sm font-semibold text-destructive mb-4">{message}</p>
        <button
          onClick={onRetry}
          className="border border-border bg-black px-5 py-2.5 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
        >
          Try again
        </button>
      </div>
    </main>
  )
}

// ─── Inner page (reads searchParams — must be wrapped in Suspense) ────────────

function PortalPageInner() {
  const params       = useParams()
  const router       = useRouter()
  const searchParams = useSearchParams()
  const clientId     = params.clientId as string

  const { authChecked, sessionInfo } = usePortalAuth(clientId)

  const [data,    setData]    = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  const activeTab = resolveTab(searchParams.get("tab"))

  const clientName =
    sessionInfo?.client_name ??
    data?.client_name ??
    "Client"

  // Load dashboard data once (drives Overview + Matches)
  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await fetchDashboard(clientId)
      setData(d)
    } catch (err) {
      if (err instanceof PortalApiError && (err.status === 401 || err.status === 403)) {
        router.replace("/portal")
        return
      }
      setError(err instanceof Error ? err.message : "Failed to load your portal.")
    } finally {
      setLoading(false)
    }
  }, [clientId, router])

  useEffect(() => {
    if (authChecked) loadDashboard()
  }, [authChecked, loadDashboard])

  function handleTabChange(tab: PortalTab) {
    const url = new URL(window.location.href)
    url.searchParams.set("tab", tab)
    router.replace(url.pathname + url.search, { scroll: false })
  }

  // Auth not yet confirmed — show nothing (redirect in progress)
  if (!authChecked) return <PageSkeleton />

  // Dashboard still loading — show skeleton inside the shell only for overview/matches
  if (loading && (activeTab === "overview" || activeTab === "matches" || activeTab === "catalog")) {
    return <PageSkeleton />
  }

  if (error) {
    return <PageError message={error} onRetry={loadDashboard} />
  }

  // ── Render shell + active tab ──────────────────────────────────────────────
  return (
    <PortalShell
      clientId={clientId}
      clientName={clientName}
      sessionInfo={sessionInfo}
      activeTab={activeTab}
      onTabChange={handleTabChange}
    >
      {activeTab === "overview" && (
        <OverviewTab
          clientId={clientId}
          data={data}
          onNavigate={handleTabChange}
        />
      )}
      {activeTab === "matches" && (
        <MatchesTab
          clientId={clientId}
          data={data}
          loading={loading}
          onNavigate={handleTabChange}
        />
      )}
      {activeTab === "catalog" && (
        <CatalogTab
          clientId={clientId}
          data={data}
          onNavigateToMessages={(unit) => {
            // navigate to Messages tab; MessagesTab will auto-select the unit
            handleTabChange("messages")
          }}
        />
      )}
      {activeTab === "viewings" && (
        <ViewingsTab clientId={clientId} />
      )}
      {activeTab === "activity" && (
        <ActivityTab clientId={clientId} />
      )}
      {activeTab === "messages" && (
        <MessagesTab clientId={clientId} data={data} />
      )}
      {activeTab === "profile" && (
        <ProfileTab
          clientId={clientId}
          data={data}
          onPreferencesSaved={() => {
            // Re-fetch dashboard so Matches + Overview reflect new scores immediately
            loadDashboard()
          }}
        />
      )}
    </PortalShell>
  )
}

// ─── Page export — Suspense boundary for useSearchParams ─────────────────────

export default function PortalDashboardPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <PortalPageInner />
    </Suspense>
  )
}
