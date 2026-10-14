"use client"

import { useCallback, useEffect, useState } from "react"
import {
  ArrowRight, CheckCircle2, ChevronDown, Loader2,
  Settings2, User2, XCircle,
} from "lucide-react"
import type { DashboardData, FinancingStatus, MoveInTimeline, PreferencesData, PreferencesPayload } from "@/lib/portal-types"
import { fetchPreferences, savePreferences } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Constants (must match backend _VALID_* sets exactly) ─────────────────────

const ENVIRONMENTS = [
  "Agriculture & Forestry",
  "Healthcare Facilities",
  "Logistics & Warehousing",
  "Manufacturing",
  "Outdoor / Industrial Sites",
  "Retail & Commercial",
]

const FINANCING_OPTIONS: { value: FinancingStatus; label: string }[] = [
  { value: "cash",        label: "Cash purchase" },
  { value: "pre-approved", label: "Pre-approved financing" },
  { value: "in-progress", label: "Financing in progress" },
  { value: "leasing",     label: "Leasing / OPEX model" },
  { value: "unspecified", label: "Not decided yet" },
]

const TIMELINE_OPTIONS: { value: MoveInTimeline; label: string }[] = [
  { value: "< 3 months",  label: "< 3 months — urgent deployment" },
  { value: "3-6 months",  label: "3–6 months" },
  { value: "6-12 months", label: "6–12 months" },
  { value: "flexible",    label: "Flexible / exploratory" },
]

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border border-border bg-card shadow-[var(--shadow-sm)]">
      <div className="border-b border-border px-5 py-3">
        <h2 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">{title}</h2>
      </div>
      <div className="px-5 py-4 flex flex-col gap-4">{children}</div>
    </section>
  )
}

// ─── Form field wrappers ──────────────────────────────────────────────────────

function FieldLabel({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-black uppercase tracking-wider">{label}</span>
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </div>
  )
}

// ─── Profile Tab ─────────────────────────────────────────────────────────────

export function ProfileTab({
  clientId,
  data: dashboardData,
  onPreferencesSaved,
}: {
  clientId: string
  data: DashboardData | null
  onPreferencesSaved?: (updated: PreferencesData) => void
}) {
  const { toast } = useToast()

  const [prefs, setPrefs]             = useState<PreferencesData | null>(null)
  const [availableTypes, setAvailableTypes] = useState<string[]>([])
  const [loading, setLoading]         = useState(true)
  const [saving, setSaving]           = useState(false)
  const [loadError, setLoadError]     = useState<string | null>(null)
  const [saveError, setSaveError]     = useState<string | null>(null)

  // Form state (draft)
  const [budget, setBudget]                     = useState("")
  const [primaryEnv, setPrimaryEnv]             = useState("")
  const [secondaryEnv, setSecondaryEnv]         = useState("")
  const [financing, setFinancing]               = useState<FinancingStatus | "">("")
  const [timeline, setTimeline]                 = useState<MoveInTimeline | "">("")
  const [unitType, setUnitType]                 = useState("")

  const load = useCallback(async () => {
    setLoading(true); setLoadError(null)
    try {
      const d = await fetchPreferences(clientId)
      setPrefs(d)
      // Seed form with current values
      setBudget(d.stated_budget != null ? String(d.stated_budget) : "")
      setPrimaryEnv(d.preferred_neighborhood ?? "")
      setSecondaryEnv(d.secondary_neighborhood ?? "")
      setFinancing((d.financing_status ?? "") as FinancingStatus | "")
      setTimeline((d.move_in_timeline ?? "") as MoveInTimeline | "")
      setUnitType(d.property_type_preference ?? "")
      // backend returns available_property_types in GET response (extra field not in TS type)
      const raw = d as PreferencesData & { available_property_types?: string[] }
      if (raw.available_property_types) setAvailableTypes(raw.available_property_types)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load preferences.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => { load() }, [load])

  // Inline validation
  const budgetNum   = budget ? parseFloat(budget.replace(/,/g, "")) : null
  const budgetError = budget && (isNaN(budgetNum!) || budgetNum! <= 0 || budgetNum! > 10_000_000)
    ? "Enter a valid amount between RM 1 and RM 10,000,000"
    : null

  const isDirty =
    (budgetNum != null && budgetNum !== (prefs?.stated_budget ?? null)) ||
    (budget === "" && prefs?.stated_budget != null) ||
    primaryEnv   !== (prefs?.preferred_neighborhood   ?? "") ||
    secondaryEnv !== (prefs?.secondary_neighborhood   ?? "") ||
    financing    !== (prefs?.financing_status         ?? "") ||
    timeline     !== (prefs?.move_in_timeline         ?? "") ||
    unitType     !== (prefs?.property_type_preference ?? "")

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (budgetError || saving) return
    setSaving(true); setSaveError(null)

    const payload: PreferencesPayload = {}
    if (budget !== "")    payload.stated_budget          = budgetNum
    if (primaryEnv)       payload.preferred_neighborhood  = primaryEnv
    if (secondaryEnv)     payload.secondary_neighborhood  = secondaryEnv || null
    if (financing)        payload.financing_status        = financing as FinancingStatus
    if (timeline)         payload.move_in_timeline        = timeline as MoveInTimeline
    if (unitType)         payload.property_type_preference = unitType

    try {
      const result = await savePreferences(clientId, payload)
      setPrefs(result)
      onPreferencesSaved?.(result)
      const count = result.matches_refreshed_count
      toast({
        title: "Preferences saved",
        description: count > 0
          ? `Your matches have been refreshed (${count} units re-scored).`
          : "Preferences saved. Matches will refresh on your next visit.",
      })
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save preferences."
      setSaveError(msg)
      toast({ title: "Save failed", description: msg, variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 sm:px-6 py-10 flex flex-col gap-5">
        <Skeleton className="h-6 w-52" />
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
        <Skeleton className="h-32" />
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-2xl px-4 sm:px-6 py-10">
        <div className="border border-border bg-card p-8 text-center">
          <XCircle className="mx-auto h-5 w-5 text-destructive mb-2" />
          <p className="text-sm font-semibold text-destructive mb-3">{loadError}</p>
          <button onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white">
            Try again
          </button>
        </div>
      </div>
    )
  }

  // Determine which fields are set (for onboarding awareness)
  const coreFieldsFilled = !!(primaryEnv && budget && financing && timeline)

  return (
    <div className="mx-auto max-w-2xl px-4 sm:px-6 py-10">
      <form onSubmit={handleSave} noValidate className="flex flex-col gap-6">
        {/* Page header */}
        <div>
          <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Settings2 className="h-3.5 w-3.5" />
            My preferences
          </h1>
          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
            These preferences help us match you to the right robot units.
            Your{" "}
            <span className="font-semibold text-foreground">Matches</span> tab
            updates automatically each time you save.
          </p>
        </div>

        {/* ── Organisation ─────────────────────────────────────────── */}
        <Section title="Organisation">
          <div className="flex items-center gap-3 py-1">
            <div className="flex h-9 w-9 items-center justify-center border border-border bg-secondary shrink-0">
              <User2 className="h-4 w-4 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-bold">{dashboardData?.client_name ?? "—"}</p>
              <p className="text-[10px] text-muted-foreground">Assigned to your PIPELINE.EV representative</p>
            </div>
          </div>
        </Section>

        {/* ── Budget ───────────────────────────────────────────────── */}
        <Section title="Procurement budget">
          <div className="flex flex-col gap-2">
            <FieldLabel
              label="Total CapEx budget (RM)"
              hint="Maximum you are authorised to deploy for robotics this cycle"
            />
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold text-muted-foreground pointer-events-none">RM</span>
              <input
                id="pref-budget"
                type="number"
                min={1}
                max={10_000_000}
                step={1000}
                placeholder="e.g. 350000"
                value={budget}
                onChange={e => setBudget(e.target.value)}
                className={`w-full border pl-10 pr-4 py-2.5 text-sm focus:outline-none focus-visible:border-primary ${
                  budgetError ? "border-destructive" : "border-border"
                } bg-white`}
              />
            </div>
            {budgetError && (
              <p className="text-[10px] font-semibold text-destructive">{budgetError}</p>
            )}
            {!budgetError && budgetNum && (
              <p className="text-[10px] text-muted-foreground">
                RM {budgetNum.toLocaleString("en-MY", { maximumFractionDigits: 0 })}
              </p>
            )}
          </div>
        </Section>

        {/* ── Deployment environment ───────────────────────────────── */}
        <Section title="Deployment environment">
          {/* Primary */}
          <div className="flex flex-col gap-2">
            <FieldLabel
              label="Primary environment"
              hint="The main facility type where the robot will operate — weighted heavily in matching"
            />
            <div className="relative">
              <select
                id="pref-primary-env"
                value={primaryEnv}
                onChange={e => setPrimaryEnv(e.target.value)}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select environment…</option>
                {ENVIRONMENTS.map(env => (
                  <option key={env} value={env}>{env}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>

          {/* Secondary */}
          <div className="flex flex-col gap-2">
            <FieldLabel
              label="Secondary environment (optional)"
              hint="A second facility type — adds up to +10% to matches in this environment"
            />
            <div className="relative">
              <select
                id="pref-secondary-env"
                value={secondaryEnv}
                onChange={e => setSecondaryEnv(e.target.value)}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">None</option>
                {ENVIRONMENTS.filter(e => e !== primaryEnv).map(env => (
                  <option key={env} value={env}>{env}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
        </Section>

        {/* ── Purchase approach ─────────────────────────────────────── */}
        <Section title="Purchase approach">
          {/* Financing */}
          <div className="flex flex-col gap-2">
            <FieldLabel label="Financing model" hint="How you plan to fund the deployment" />
            <div className="relative">
              <select
                id="pref-financing"
                value={financing}
                onChange={e => setFinancing(e.target.value as FinancingStatus | "")}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select…</option>
                {FINANCING_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>

          {/* Timeline */}
          <div className="flex flex-col gap-2">
            <FieldLabel label="Deployment timeline" hint="How soon you're planning to deploy" />
            <div className="relative">
              <select
                id="pref-timeline"
                value={timeline}
                onChange={e => setTimeline(e.target.value as MoveInTimeline | "")}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select…</option>
                {TIMELINE_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
        </Section>

        {/* ── Unit type interest ────────────────────────────────────── */}
        {availableTypes.length > 0 && (
          <Section title="Unit type interest">
            <div className="flex flex-col gap-2">
              <FieldLabel
                label="Preferred category"
                hint="Focus matching on a specific robot category — leave blank for all types"
              />
              <div className="relative">
                <select
                  id="pref-unit-type"
                  value={unitType}
                  onChange={e => setUnitType(e.target.value)}
                  className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
                >
                  <option value="">Any category</option>
                  {availableTypes.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>
          </Section>
        )}

        {/* Save error */}
        {saveError && (
          <div className="border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive font-semibold">
            {saveError}
          </div>
        )}

        {/* Save button */}
        <div className="flex items-center gap-4">
          <button
            type="submit"
            id="save-preferences-btn"
            disabled={!isDirty || !!budgetError || saving}
            className="group flex items-center gap-2 border border-border bg-black px-6 py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40"
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : (
              <>
                Save preferences
                <ArrowRight className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5" strokeWidth={3} />
              </>
            )}
          </button>
          {!isDirty && prefs?.updated_fields && prefs.updated_fields.length === 0 && coreFieldsFilled && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
              All set
            </span>
          )}
        </div>

        {/* Footer note */}
        <p className="text-[10px] text-muted-foreground leading-relaxed border-t border-border pt-4">
          Your PIPELINE.EV representative can see that you updated your preferences and will review your new matches.
          Internal scoring details and probabilities are never shown in the client portal.
        </p>
      </form>
    </div>
  )
}
