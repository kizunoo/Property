"use client"

import { useCallback, useEffect, useState } from "react"
import {
  ArrowRight,
  Building,
  CheckCircle2,
  ChevronDown,
  Clock,
  Loader2,
  Mail,
  Settings2,
  Shield,
  User2,
  Users,
  XCircle,
} from "lucide-react"
import type {
  ContactPerson,
  DashboardData,
  FinancingStatus,
  MoveInTimeline,
  PreferencesData,
  PreferencesPayload,
  FacilityProfileData,
} from "@/lib/portal-types"
import { fetchPreferences, savePreferences, patchPreferences } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"

// ─── Constants ────────────────────────────────────────────────────────────────

const ENVIRONMENTS = [
  "Agriculture & Forestry",
  "Healthcare Facilities",
  "Logistics & Warehousing",
  "Manufacturing",
  "Outdoor / Industrial Sites",
  "Retail & Commercial",
]

const FINANCING_OPTIONS: { value: FinancingStatus; label: string }[] = [
  { value: "cash", label: "Cash purchase" },
  { value: "pre-approved", label: "Pre-approved financing" },
  { value: "in-progress", label: "Financing in progress" },
  { value: "leasing", label: "Leasing / OPEX model" },
  { value: "unspecified", label: "Not decided yet" },
]

const TIMELINE_OPTIONS: { value: MoveInTimeline; label: string }[] = [
  { value: "< 3 months", label: "< 3 months — urgent deployment" },
  { value: "3-6 months", label: "3–6 months" },
  { value: "6-12 months", label: "6–12 months" },
  { value: "flexible", label: "Flexible / exploratory" },
]

const FACILITY_TYPES = [
  { value: "warehouse", label: "Warehouse / Logistics Hub" },
  { value: "manufacturing", label: "Manufacturing / Plant" },
  { value: "healthcare", label: "Healthcare / Hospital" },
  { value: "cleaning", label: "Commercial Cleaning Site" },
  { value: "retail_hospitality", label: "Retail & Hospitality" },
] as const

const PRIMARY_USE_CASES = [
  { value: "transport", label: "Material Transport / AGV" },
  { value: "cleaning", label: "Autonomous Floor Cleaning" },
  { value: "palletizing", label: "Robotic Palletizing & Stacking" },
  { value: "security", label: "Autonomous Security & Patrol" },
  { value: "delivery", label: "Indoor / Last-Yard Delivery" },
] as const

const DEPLOYMENT_TIMELINES = [
  { value: "0-3m", label: "Immediate (0–3 months)" },
  { value: "3-6m", label: "Near-Term (3–6 months)" },
  { value: "6-12m", label: "Medium-Term (6–12 months)" },
  { value: "12m+", label: "Planning / Long-Term (12+ months)" },
] as const

const BUDGET_BANDS = [
  { value: "<50k", label: "< RM 50,000" },
  { value: "50-150k", label: "RM 50,000 – 150,000" },
  { value: "150-500k", label: "RM 150,000 – 500,000" },
  { value: "500k+", label: "RM 500,000+" },
] as const

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Never"
  try {
    return new Date(iso).toLocaleDateString("en-MY", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}

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

  const [prefs, setPrefs] = useState<PreferencesData | null>(null)
  const [availableTypes, setAvailableTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Form state (draft)
  const [budget, setBudget] = useState("")
  const [primaryEnv, setPrimaryEnv] = useState("")
  const [secondaryEnv, setSecondaryEnv] = useState("")
  const [financing, setFinancing] = useState<FinancingStatus | "">("")
  const [timeline, setTimeline] = useState<MoveInTimeline | "">("")
  const [unitType, setUnitType] = useState("")

  // B2B Facility Profile (JSONB)
  const [facilityType, setFacilityType] = useState<string>("")
  const [floorAreaSqm, setFloorAreaSqm] = useState<string>("")
  const [environmentNotes, setEnvironmentNotes] = useState<string>("")
  const [primaryUseCase, setPrimaryUseCase] = useState<string>("")
  const [deploymentTimeline, setDeploymentTimeline] = useState<string>("")
  const [budgetBand, setBudgetBand] = useState<string>("")
  const [industry, setIndustry] = useState("")
  const [existingAutomation, setExistingAutomation] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const d = await fetchPreferences(clientId)
      setPrefs(d)
      setBudget(d.stated_budget != null ? String(d.stated_budget) : "")
      setPrimaryEnv(d.preferred_neighborhood ?? "")
      setSecondaryEnv(d.secondary_neighborhood ?? "")
      setFinancing((d.financing_status ?? "") as FinancingStatus | "")
      setTimeline((d.move_in_timeline ?? "") as MoveInTimeline | "")
      setUnitType(d.property_type_preference ?? "")

      // B2B Facility Profile
      const fp = d.facility_profile || {}
      setFacilityType(fp.facility_type || d.facility_type || "")
      setFloorAreaSqm(fp.floor_area_sqm != null ? String(fp.floor_area_sqm) : (d.facility_size_sqm != null ? String(d.facility_size_sqm) : ""))
      setEnvironmentNotes(fp.environment_notes || "")
      setPrimaryUseCase(fp.primary_use_case || d.use_case || "")
      setDeploymentTimeline(fp.timeline || "")
      setBudgetBand(fp.budget_band || "")
      setIndustry(d.industry ?? "")
      setExistingAutomation(d.existing_automation ?? "")

      const raw = d as PreferencesData & { available_property_types?: string[] }
      if (raw.available_property_types) setAvailableTypes(raw.available_property_types)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load preferences.")
    } finally {
      setLoading(false)
    }
  }, [clientId])

  useEffect(() => {
    load()
  }, [load])

  // Validation
  const budgetNum = budget ? parseFloat(budget.replace(/,/g, "")) : null
  const budgetError =
    budget && (isNaN(budgetNum!) || budgetNum! <= 0 || budgetNum! > 10_000_000)
      ? "Enter a valid amount between RM 1 and RM 10,000,000"
      : null

  const sizeNum = floorAreaSqm ? parseFloat(floorAreaSqm.replace(/,/g, "")) : null
  const sizeError =
    floorAreaSqm && (isNaN(sizeNum!) || sizeNum! < 0 || sizeNum! > 10_000_000)
      ? "Enter a valid floor area up to 10,000,000 sqm"
      : null

  const fpPref = prefs?.facility_profile || {}
  const isDirty =
    (budgetNum != null && budgetNum !== (prefs?.stated_budget ?? null)) ||
    (budget === "" && prefs?.stated_budget != null) ||
    primaryEnv !== (prefs?.preferred_neighborhood ?? "") ||
    secondaryEnv !== (prefs?.secondary_neighborhood ?? "") ||
    financing !== (prefs?.financing_status ?? "") ||
    timeline !== (prefs?.move_in_timeline ?? "") ||
    unitType !== (prefs?.property_type_preference ?? "") ||
    industry !== (prefs?.industry ?? "") ||
    existingAutomation !== (prefs?.existing_automation ?? "") ||
    facilityType !== (fpPref.facility_type || prefs?.facility_type || "") ||
    (sizeNum != null && sizeNum !== (fpPref.floor_area_sqm ?? prefs?.facility_size_sqm ?? null)) ||
    environmentNotes !== (fpPref.environment_notes ?? "") ||
    primaryUseCase !== (fpPref.primary_use_case ?? "") ||
    deploymentTimeline !== (fpPref.timeline ?? "") ||
    budgetBand !== (fpPref.budget_band ?? "")

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (budgetError || sizeError || saving) return
    setSaving(true)
    setSaveError(null)

    const payload: PreferencesPayload = {}
    if (budget !== "") payload.stated_budget = budgetNum
    if (primaryEnv) payload.preferred_neighborhood = primaryEnv
    if (secondaryEnv) payload.secondary_neighborhood = secondaryEnv || null
    if (financing) payload.financing_status = financing as FinancingStatus
    if (timeline) payload.move_in_timeline = timeline as MoveInTimeline
    if (unitType) payload.property_type_preference = unitType

    // Standard B2B fields
    payload.industry = industry || null
    payload.existing_automation = existingAutomation || null

    // Facility Profile (JSONB)
    payload.facility_profile = {
      facility_type: (facilityType || null) as any,
      floor_area_sqm: sizeNum,
      environment_notes: environmentNotes ? environmentNotes.trim() : null,
      primary_use_case: (primaryUseCase || null) as any,
      timeline: (deploymentTimeline || null) as any,
      budget_band: (budgetBand || null) as any,
    }

    try {
      const result = await patchPreferences(clientId, payload)
      setPrefs(result)
      onPreferencesSaved?.(result)
      toast({
        title: "Company profile updated",
        description: "Your operational profile and deployment specs have been securely saved.",
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
          <button
            onClick={load}
            className="border border-border bg-black px-4 py-2 text-xs font-black uppercase tracking-wider text-white"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 sm:px-6 py-10">
      <form onSubmit={handleSave} noValidate className="flex flex-col gap-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border pb-4">
          <div>
            <h1 className="text-[10px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Settings2 className="h-3.5 w-3.5" /> Company Profile &amp; Requirements
            </h1>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              Define your facility operations and robotics procurement criteria.
            </p>
          </div>
          {prefs?.profile_updated_at && (
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground shrink-0">
              <Clock className="h-3 w-3" />
              <span>Updated {formatDate(prefs.profile_updated_at)}</span>
            </div>
          )}
        </div>

        {/* ── Organisation ─────────────────────────────────────────── */}
        <Section title="Organisation">
          <div className="flex items-center gap-3 py-1">
            <div className="flex h-9 w-9 items-center justify-center border border-border bg-secondary shrink-0">
              <Building className="h-4 w-4 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-bold">{dashboardData?.client_name ?? "—"}</p>
              <p className="text-[10px] text-muted-foreground">
                Managed account · Client ID: {clientId.slice(0, 8)}…
              </p>
            </div>
          </div>
        </Section>

        {/* ── B2B Facility & Deployment Specifications ──────────────── */}
        <Section title="Facility &amp; Deployment Specifications (B2B POC)">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Facility Type" hint="Operating facility classification" />
              <div className="relative">
                <select
                  id="pref-facility-type"
                  value={facilityType}
                  onChange={(e) => setFacilityType(e.target.value)}
                  className="w-full border border-border bg-white px-3 pr-9 py-2 text-sm appearance-none focus:outline-none focus-visible:border-primary"
                >
                  <option value="">Select facility type…</option>
                  {FACILITY_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Floor Area (sqm)" hint="Total operational floor space (up to 10,000,000)" />
              <input
                id="pref-facility-size"
                type="number"
                min={0}
                max={10000000}
                value={floorAreaSqm}
                onChange={(e) => setFloorAreaSqm(e.target.value)}
                placeholder="e.g. 15000"
                className="border border-border bg-white px-3 py-2 text-sm focus:outline-none focus-visible:border-primary"
              />
              {sizeError && <p className="text-[10px] text-destructive">{sizeError}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Primary Use Case" hint="Primary automation workflow" />
              <div className="relative">
                <select
                  id="pref-primary-use-case"
                  value={primaryUseCase}
                  onChange={(e) => setPrimaryUseCase(e.target.value)}
                  className="w-full border border-border bg-white px-3 pr-9 py-2 text-sm appearance-none focus:outline-none focus-visible:border-primary"
                >
                  <option value="">Select primary workflow…</option>
                  {PRIMARY_USE_CASES.map((uc) => (
                    <option key={uc.value} value={uc.value}>
                      {uc.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Target POC Timeline" hint="Expected deployment timeframe" />
              <div className="relative">
                <select
                  id="pref-deployment-timeline"
                  value={deploymentTimeline}
                  onChange={(e) => setDeploymentTimeline(e.target.value)}
                  className="w-full border border-border bg-white px-3 pr-9 py-2 text-sm appearance-none focus:outline-none focus-visible:border-primary"
                >
                  <option value="">Select deployment timeline…</option>
                  {DEPLOYMENT_TIMELINES.map((tl) => (
                    <option key={tl.value} value={tl.value}>
                      {tl.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Budget Band (MYR)" hint="Target investment envelope" />
              <div className="relative">
                <select
                  id="pref-budget-band"
                  value={budgetBand}
                  onChange={(e) => setBudgetBand(e.target.value)}
                  className="w-full border border-border bg-white px-3 pr-9 py-2 text-sm appearance-none focus:outline-none focus-visible:border-primary"
                >
                  <option value="">Select budget band…</option>
                  {BUDGET_BANDS.map((bb) => (
                    <option key={bb.value} value={bb.value}>
                      {bb.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <FieldLabel label="Industry Sector" hint="e.g. E-Commerce, Automotive, Cold Storage" />
              <input
                id="pref-industry"
                type="text"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="e.g. Semiconductor Manufacturing"
                className="border border-border bg-white px-3 py-2 text-sm focus:outline-none focus-visible:border-primary"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <FieldLabel label="Facility &amp; Environment Notes" hint="Obstacles, ramps, lighting, flooring conditions, ceiling clearances (max 1000 chars)" />
            <textarea
              id="pref-environment-notes"
              value={environmentNotes}
              maxLength={1000}
              onChange={(e) => setEnvironmentNotes(e.target.value)}
              placeholder="e.g. Smooth epoxy flooring, 4m aisle clearance, 2 ramp inclines at receiving dock..."
              rows={3}
              className="resize-none border border-border bg-white px-3 py-2 text-sm focus:outline-none focus-visible:border-primary"
            />
          </div>
        </Section>

        {/* ── Procurement Budget ───────────────────────────────────── */}
        <Section title="Procurement Budget">
          <div className="flex flex-col gap-2">
            <FieldLabel
              label="Total CapEx budget (RM)"
              hint="Maximum authorised capital expenditure for this automation cycle"
            />
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold text-muted-foreground pointer-events-none">
                RM
              </span>
              <input
                id="pref-budget"
                type="number"
                min={1}
                max={10_000_000}
                step={1000}
                placeholder="e.g. 350000"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className={`w-full border pl-10 pr-4 py-2.5 text-sm focus:outline-none focus-visible:border-primary ${
                  budgetError ? "border-destructive" : "border-border"
                } bg-white`}
              />
            </div>
            {budgetError && <p className="text-[10px] font-semibold text-destructive">{budgetError}</p>}
            {!budgetError && budgetNum && (
              <p className="text-[10px] text-muted-foreground">
                RM {budgetNum.toLocaleString("en-MY", { maximumFractionDigits: 0 })}
              </p>
            )}
          </div>
        </Section>

        {/* ── Deployment Environment ───────────────────────────────── */}
        <Section title="Operating Environment">
          <div className="flex flex-col gap-2">
            <FieldLabel label="Primary Environment" hint="Main setting where the units operate" />
            <div className="relative">
              <select
                id="pref-primary-env"
                value={primaryEnv}
                onChange={(e) => setPrimaryEnv(e.target.value)}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select environment…</option>
                {ENVIRONMENTS.map((env) => (
                  <option key={env} value={env}>
                    {env}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <FieldLabel label="Secondary Environment (optional)" hint="Secondary zone" />
            <div className="relative">
              <select
                id="pref-secondary-env"
                value={secondaryEnv}
                onChange={(e) => setSecondaryEnv(e.target.value)}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">None</option>
                {ENVIRONMENTS.filter((e) => e !== primaryEnv).map((env) => (
                  <option key={env} value={env}>
                    {env}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
        </Section>

        {/* ── Financing & Timeline ─────────────────────────────────── */}
        <Section title="Commercial Terms">
          <div className="flex flex-col gap-2">
            <FieldLabel label="Commercial Model" hint="Payment and financing structure" />
            <div className="relative">
              <select
                id="pref-financing"
                value={financing}
                onChange={(e) => setFinancing(e.target.value as FinancingStatus | "")}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select…</option>
                {FINANCING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <FieldLabel label="Deployment Timeline" hint="Target commissioning date" />
            <div className="relative">
              <select
                id="pref-timeline"
                value={timeline}
                onChange={(e) => setTimeline(e.target.value as MoveInTimeline | "")}
                className="w-full border border-border bg-white px-3 pr-9 py-2.5 text-sm appearance-none focus:outline-none focus-visible:border-primary"
              >
                <option value="">Select…</option>
                {TIMELINE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            </div>
          </div>
        </Section>

        {/* ── Authorized Contacts (Read-only) ──────────────────────── */}
        {prefs?.contacts && prefs.contacts.length > 0 && (
          <Section title="Authorised Company Representatives">
            <p className="text-xs text-muted-foreground">
              These team members have designated access to this company portal. Contact your
              PIPELINE.EV representative to add or revoke access.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              {prefs.contacts.map((c) => (
                <div key={c.id} className="border border-border bg-secondary/30 p-3.5 flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs">{c.name}</span>
                    <span className="inline-flex items-center gap-1 border border-border bg-card px-2 py-0.5 text-[9px] font-black uppercase text-muted-foreground">
                      <Shield className="h-2.5 w-2.5" />
                      {c.role}
                    </span>
                  </div>
                  {c.title && <p className="text-[11px] text-muted-foreground">{c.title}</p>}
                  {c.email && (
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/80 mt-1">
                      <Mail className="h-3 w-3" />
                      <span>{c.email}</span>
                    </div>
                  )}
                </div>
              ))}
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
            disabled={!isDirty || !!budgetError || !!sizeError || saving}
            className="group flex items-center gap-2 border border-border bg-black px-6 py-3 text-sm font-black uppercase tracking-wider text-white hover:shadow-[var(--shadow-sm)] transition-shadow disabled:opacity-40"
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : (
              <>
                Save changes
                <ArrowRight
                  className="h-4 w-4 text-primary transition-transform group-hover:translate-x-0.5"
                  strokeWidth={3}
                />
              </>
            )}
          </button>
          {!isDirty && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              Up to date
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
