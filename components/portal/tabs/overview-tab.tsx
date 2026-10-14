"use client"

import { useState, useEffect } from "react"
import { ArrowRight, Bot, CalendarClock, ChevronRight, Clock, MessageSquare, Sliders, Sparkles, TrendingUp } from "lucide-react"
import type { DashboardData, PortalTab, PreferencesData } from "@/lib/portal-types"
import { fetchPreferences } from "@/lib/portal-api"
import { Skeleton } from "@/components/ui/skeleton"

function formatCost(c: number | null): string {
  if (!c) return "Contact us"
  return `RM ${c.toLocaleString("en-MY", { maximumFractionDigits: 0 })}`
}

function formatDate(s: string | null): string {
  if (!s) return "Date TBC"
  return new Date(s).toLocaleDateString("en-MY", {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

const STAGE_LABELS: Record<string, string> = {
  new:      "Exploring options",
  viewing:  "Active evaluation",
  proposal: "Under review",
  negotiation: "In discussion",
  closed:   "Completed",
}

interface OverviewTabProps {
  clientId: string
  data: DashboardData | null
  onNavigate: (tab: PortalTab) => void
}

export function OverviewTab({ clientId, data, onNavigate }: OverviewTabProps) {
  const [prefs, setPrefs] = useState<PreferencesData | null>(null)
  const [prefsLoading, setPrefsLoading] = useState(true)

  useEffect(() => {
    let active = true
    fetchPreferences(clientId)
      .then((p) => {
        if (active) setPrefs(p)
      })
      .catch(() => {})
      .finally(() => {
        if (active) setPrefsLoading(false)
      })
    return () => {
      active = false
    }
  }, [clientId])

  if (!data) {
    return (
      <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 flex flex-col gap-8">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-40" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-56" />)}
        </div>
      </div>
    )
  }

  const firstName = data.client_name.split(" ")[0]
  const upcoming  = data.scheduled_demos.filter(d => d.status === "upcoming")
  const pending   = data.scheduled_demos.filter(d => d.status === "requested")
  const confirmed = upcoming.length
  const stage     = STAGE_LABELS[data.relationship_stage] ?? data.relationship_stage
  const nextDemo  = upcoming[0] ?? pending[0] ?? null
  const topMatches = data.matches.slice(0, 3)

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 flex flex-col gap-8">

      {/* ── Welcome ───────────────────────────────────────────────────────── */}
      <section>
        <span className="inline-flex items-center gap-1.5 border border-border bg-primary px-3 py-1 text-[10px] font-black uppercase tracking-wider mb-3">
          <Sparkles className="h-3 w-3" strokeWidth={3} />
          Personalised for you
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-tight">
          Welcome back, {firstName}
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground leading-relaxed">
          Based on{" "}
          <button
            type="button"
            onClick={() => onNavigate("profile")}
            className="font-bold text-foreground underline decoration-primary underline-offset-4 hover:text-primary transition-colors cursor-pointer"
          >
            your operational profile
          </button>
          , we&apos;ve curated the robot units below. Request a live demonstration to see any of them in action.
        </p>
      </section>

      {/* ── Operational Preferences Banners ───────────────────────────────── */}
      {!prefsLoading && (!prefs?.preferred_neighborhood || !prefs?.stated_budget) && (
        <section className="border border-amber-300 bg-amber-50/70 p-5 shadow-[var(--shadow-xs)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center border border-amber-300 bg-amber-100 text-amber-800">
              <Sliders className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-amber-950">Complete your operational preferences</h3>
              <p className="text-xs text-amber-800/80 mt-0.5 max-w-xl leading-relaxed">
                Tell us your deployment environment, budget, and timeline so our AI scoring engine can curate units tailored specifically to your facility.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onNavigate("profile")}
            className="group shrink-0 flex items-center gap-1.5 border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow"
          >
            Complete preferences
            <ArrowRight className="h-3.5 w-3.5 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />
          </button>
        </section>
      )}

      {!prefsLoading && prefs?.preferred_neighborhood && prefs?.stated_budget && (
        <section className="border border-border bg-card p-4 shadow-[var(--shadow-xs)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mr-1">
              Matched using:
            </span>
            <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2.5 py-1 text-xs font-semibold">
              Budget: RM {prefs.stated_budget.toLocaleString("en-MY")}
            </span>
            <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2.5 py-1 text-xs font-semibold">
              {prefs.preferred_neighborhood}
            </span>
            {prefs.financing_status && prefs.financing_status !== "unspecified" && (
              <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2.5 py-1 text-xs font-semibold uppercase">
                {prefs.financing_status}
              </span>
            )}
            {prefs.move_in_timeline && (
              <span className="inline-flex items-center gap-1 border border-border bg-secondary px-2.5 py-1 text-xs font-semibold">
                {prefs.move_in_timeline}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => onNavigate("profile")}
            className="text-xs font-black uppercase tracking-wider text-foreground hover:text-primary transition-colors flex items-center gap-1 shrink-0"
          >
            Edit preferences
            <ChevronRight className="h-3 w-3 text-primary" strokeWidth={3} />
          </button>
        </section>
      )}

      {/* ── Stat cards ────────────────────────────────────────────────────── */}
      <section
        className="grid grid-cols-2 sm:grid-cols-4 gap-4"
        aria-label="Summary statistics"
      >
        {[
          {
            label: "Matched units",
            value: data.matches.length,
            suffix: "",
            accent: false,
            id: "stat-matches",
          },
          {
            label: "Confirmed demos",
            value: confirmed,
            suffix: "",
            accent: confirmed > 0,
            id: "stat-confirmed",
          },
          {
            label: "Pending requests",
            value: pending.length,
            suffix: "",
            accent: false,
            id: "stat-pending",
          },
          {
            label: "Journey stage",
            value: null,
            text: stage,
            accent: false,
            id: "stat-stage",
          },
        ].map((stat) => (
          <div
            key={stat.id}
            id={stat.id}
            className={`flex flex-col justify-between gap-2 border p-5 shadow-[var(--shadow-sm)] ${
              stat.accent
                ? "border-primary bg-primary"
                : "border-border bg-card"
            }`}
          >
            <span className="text-[10px] font-black uppercase tracking-wider text-current opacity-70">
              {stat.label}
            </span>
            {stat.text !== undefined ? (
              <span className="text-sm font-bold leading-snug">{stat.text}</span>
            ) : (
              <span className="font-display text-3xl font-bold leading-none">
                {stat.value}
              </span>
            )}
          </div>
        ))}
      </section>

      {/* ── Next demo ─────────────────────────────────────────────────────── */}
      {nextDemo && (
        <section aria-label="Next upcoming demo">
          <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
            <CalendarClock className="h-3.5 w-3.5" />
            Next demo
          </h2>
          <div className="border border-border bg-card shadow-[var(--shadow-sm)] p-5 flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="font-bold text-base leading-snug">{nextDemo.property_name ?? "Unit TBC"}</p>
              <p className="text-sm text-muted-foreground mt-1">{formatDate(nextDemo.scheduled_at)}</p>
            </div>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider border ${
              nextDemo.status === "upcoming"
                ? "bg-primary border-primary/30"
                : "bg-amber-50 border-amber-200 text-amber-700"
            }`}>
              <Clock className="h-3 w-3" />
              {nextDemo.status === "upcoming" ? "Confirmed" : "Awaiting confirmation"}
            </span>
          </div>
        </section>
      )}

      {/* ── Top 3 matches preview ─────────────────────────────────────────── */}
      {topMatches.length > 0 && (
        <section aria-label="Top matched units">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <TrendingUp className="h-3.5 w-3.5" />
              Top matches
            </h2>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => onNavigate("catalog")}
                className="flex items-center gap-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
              >
                Browse all units
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onNavigate("matches")}
                className="flex items-center gap-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
              >
                View all matches
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {topMatches.map((unit, i) => (
              <div
                key={unit.property_id}
                className="border border-border bg-card shadow-[var(--shadow-sm)] p-5 flex flex-col gap-3 hover:shadow-[var(--shadow-md)] transition-shadow"
              >
                {/* Rank + name */}
                <div>
                  <span className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-2">
                    {i === 0 && <Sparkles className="h-3 w-3 text-primary" strokeWidth={3} />}
                    {i === 0 ? "Top match" : `#${i + 1} match`}
                  </span>
                  <h3 className="font-bold text-sm leading-snug">{unit.name}</h3>
                  {unit.cost && (
                    <p className="text-xs text-muted-foreground mt-1">{formatCost(unit.cost)}</p>
                  )}
                </div>
                {/* ROI */}
                {unit.payback_months && (
                  <p className="text-xs text-muted-foreground">
                    Est. payback: <span className="font-bold text-foreground">~{unit.payback_months} months</span>
                  </p>
                )}
                {/* Reasoning snippet */}
                {unit.reasoning && (
                  <p className="text-xs text-foreground/70 leading-relaxed line-clamp-2">{unit.reasoning}</p>
                )}
                <button
                  onClick={() => onNavigate("matches")}
                  className="mt-auto group flex items-center gap-1.5 border border-border bg-black px-3 py-2 text-[10px] font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-xs)] transition-shadow w-full justify-center"
                >
                  View details
                  <ChevronRight className="h-3.5 w-3.5 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {data.matches.length === 0 && (
        <section className="border border-border bg-card p-12 text-center shadow-[var(--shadow-sm)]">
          <Bot className="mx-auto h-8 w-8 text-muted-foreground mb-3 opacity-50" />
          <p className="text-sm text-muted-foreground">
            Your agent is preparing your recommendations. Check back soon.
          </p>
        </section>
      )}

      {/* ── Process steps ─────────────────────────────────────────────────── */}
      <section aria-label="How it works">
        <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground mb-3">
          How it works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            {
              step: "01",
              icon: <Sparkles className="h-5 w-5 text-primary" />,
              title: "AI-matched units",
              body: "Every unit has been selected based on your operational environment, budget, and automation goals.",
            },
            {
              step: "02",
              icon: <CalendarClock className="h-5 w-5 text-primary" />,
              title: "Request a live demo",
              body: "Click 'Request demonstration' on any unit. Our team will reach out within 24 hours to confirm.",
            },
            {
              step: "03",
              icon: <MessageSquare className="h-5 w-5 text-primary" />,
              title: "Ask us anything",
              body: "Use the Messages tab to send questions about specific units — no commitment required.",
            },
          ].map((item) => (
            <div key={item.step} className="border border-border bg-card p-5 shadow-[var(--shadow-xs)]">
              <div className="mb-3 flex items-center justify-between">
                {item.icon}
                <span className="font-mono text-[10px] font-bold text-muted-foreground/50">{item.step}</span>
              </div>
              <h3 className="text-sm font-bold tracking-tight mb-1.5">{item.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

    </div>
  )
}
