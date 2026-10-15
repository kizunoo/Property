"use client"

import { useEffect, useMemo, useState } from "react"
import { Calculator, Check, CheckCircle2, DollarSign, Sparkles, TrendingUp } from "lucide-react"
import { computeRoi, type RoiInputs, type RoiResult } from "@/lib/roi"
import { submitInquiry } from "@/lib/portal-api"
import { useToast } from "@/hooks/use-toast"
import type { CatalogUnit } from "@/lib/portal-types"

function formatMYR(n: number | null): string {
  if (n == null) return "—"
  return `RM ${Math.round(n).toLocaleString()}`
}

interface RoiPanelProps {
  unit: CatalogUnit
  clientId: string
  facilityProfile?: Record<string, any> | null
  onSuccess?: () => void
}

export function RoiPanel({
  unit,
  clientId,
  facilityProfile,
  onSuccess,
}: RoiPanelProps) {
  const { toast } = useToast()

  // Initial state derived / prefilled from facilityProfile if present
  const [shifts, setShifts] = useState<1 | 2 | 3>(() => {
    const s = facilityProfile?.shifts
    if (s === 1 || s === 2 || s === 3) return s
    return 2
  })

  const [headcount, setHeadcount] = useState<number>(() => {
    const h = facilityProfile?.headcount_per_shift || facilityProfile?.headcountPerShift
    return typeof h === "number" && h > 0 ? h : 3
  })

  const [laborCost, setLaborCost] = useState<number>(() => {
    const l = facilityProfile?.monthly_labor_cost || facilityProfile?.monthlyLaborCost
    return typeof l === "number" && l > 0 ? l : 4000
  })

  const [mode, setMode] = useState<"purchase" | "lease">("purchase")
  const [submitting, setSubmitting] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

  // Robot pricing
  const purchasePrice = unit.cost ?? 0
  const leaseMonthly = useMemo(() => {
    const fromSpecs = unit.specs?.lease_monthly ?? unit.specs?.leaseMonthly
    if (typeof fromSpecs === "number" && fromSpecs > 0) return fromSpecs
    return purchasePrice > 0 ? Math.round(purchasePrice * 0.035) : 3500
  }, [unit.specs, purchasePrice])

  // Live calculation
  const roi: RoiResult = useMemo(() => {
    const inputs: RoiInputs = {
      shifts,
      headcountPerShift: headcount,
      monthlyLaborCost: laborCost,
    }
    return computeRoi(inputs, { purchasePrice, leaseMonthly }, mode)
  }, [shifts, headcount, laborCost, purchasePrice, leaseMonthly, mode])

  async function handleSaveAndRequestQuote() {
    setSubmitting(true)
    try {
      await submitInquiry(clientId, {
        property_id: unit.property_id,
        roi_scenario: {
          shifts,
          headcountPerShift: headcount,
          monthlyLaborCost: laborCost,
          mode,
        },
      } as any)

      setSavedSuccess(true)
      toast({
        title: "ROI scenario saved & quote requested!",
        description: `Your representative has been notified of your commercial interest in ${unit.name}.`,
      })
      if (onSuccess) {
        setTimeout(onSuccess, 1200)
      }
    } catch (err: any) {
      toast({
        title: "Failed to save scenario",
        description: err?.message || "Please check your network connection.",
        variant: "destructive",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="border border-border bg-card p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <Calculator className="h-4 w-4 text-primary" />
          <h3 className="text-xs font-black uppercase tracking-wider">ROI &amp; Deployment Calculator</h3>
        </div>
        <span className="border border-border bg-secondary px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
          Live Model
        </span>
      </div>

      {/* Mode toggle */}
      <div className="flex border border-border bg-secondary p-0.5">
        <button
          type="button"
          onClick={() => setMode("purchase")}
          className={`flex-1 py-1.5 text-xs font-black uppercase tracking-wider transition-colors ${
            mode === "purchase"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Outright Purchase
        </button>
        <button
          type="button"
          onClick={() => setMode("lease")}
          className={`flex-1 py-1.5 text-xs font-black uppercase tracking-wider transition-colors ${
            mode === "lease"
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          OpEx Lease
        </button>
      </div>

      {/* Inputs */}
      <div className="flex flex-col gap-3">
        {/* Shifts */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <label className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Daily Operational Shifts
            </label>
            <span className="text-xs font-black">{shifts} shift{shifts > 1 ? "s" : ""} / day</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {([1, 2, 3] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setShifts(s)}
                className={`border py-1 text-xs font-black transition-colors ${
                  shifts === s
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-secondary text-muted-foreground hover:bg-muted"
                }`}
              >
                {s} Shift{s > 1 ? "s" : ""}
              </button>
            ))}
          </div>
        </div>

        {/* Headcount */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <label className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Replaced / Augmented Headcount
            </label>
            <span className="text-xs font-black">{headcount} staff / shift</span>
          </div>
          <input
            type="number"
            min={0}
            max={500}
            step={1}
            value={headcount}
            onChange={(e) => setHeadcount(Math.max(0, Math.min(500, Number(e.target.value) || 0)))}
            className="w-full border border-border bg-background px-3 py-1.5 text-xs font-bold focus:outline-none focus-visible:border-primary"
          />
        </div>

        {/* Labor cost */}
        <div>
          <div className="flex justify-between items-center mb-1">
            <label className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              Average Monthly Labor Cost (MYR)
            </label>
            <span className="text-xs font-black">{formatMYR(laborCost)} / staff</span>
          </div>
          <input
            type="number"
            min={0}
            max={1000000}
            step={250}
            value={laborCost}
            onChange={(e) => setLaborCost(Math.max(0, Math.min(1000000, Number(e.target.value) || 0)))}
            className="w-full border border-border bg-background px-3 py-1.5 text-xs font-bold focus:outline-none focus-visible:border-primary"
          />
        </div>
      </div>

      {/* Live Output Cards */}
      <div className="border border-border bg-secondary/80 p-3 flex flex-col gap-2.5">
        <p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground">
          Projected Economic Returns
        </p>

        <div className="grid grid-cols-2 gap-2">
          {/* Monthly Savings */}
          <div className="border border-border bg-card p-2.5">
            <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground block">
              Monthly Labor Replaced
            </span>
            <span className="text-sm font-black text-emerald-600 dark:text-emerald-400">
              {formatMYR(roi.monthlySavings)}
            </span>
          </div>

          {/* Net Monthly Benefit */}
          <div className="border border-border bg-card p-2.5">
            <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground block">
              Net Monthly Benefit
            </span>
            <span className={`text-sm font-black ${roi.netMonthly >= 0 ? "text-foreground" : "text-destructive"}`}>
              {formatMYR(roi.netMonthly)}
            </span>
          </div>

          {/* Payback period */}
          <div className="border border-border bg-card p-2.5">
            <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground block">
              Payback Period
            </span>
            <span className="text-sm font-black">
              {mode === "lease"
                ? "Immediate (OpEx)"
                : roi.paybackMonths != null
                ? `~${roi.paybackMonths.toFixed(1)} mos`
                : "—"}
            </span>
          </div>

          {/* 3-Year ROI */}
          <div className="border border-border bg-card p-2.5">
            <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground block">
              3-Year Net ROI
            </span>
            <span className="text-sm font-black text-primary">
              {roi.threeYearRoiPct != null ? `${Math.round(roi.threeYearRoiPct)}%` : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Action Button */}
      <button
        type="button"
        disabled={submitting || savedSuccess}
        onClick={handleSaveAndRequestQuote}
        className={`flex items-center justify-center gap-2 border border-border py-2.5 text-xs font-black uppercase tracking-wider transition-colors ${
          savedSuccess
            ? "bg-emerald-600 text-white border-emerald-600"
            : "bg-black dark:bg-primary text-white dark:text-primary-foreground hover:opacity-90"
        }`}
      >
        {savedSuccess ? (
          <>
            <CheckCircle2 className="h-4 w-4" />
            Scenario Saved &amp; Quote Requested
          </>
        ) : submitting ? (
          "Computing & Submitting…"
        ) : (
          <>
            <TrendingUp className="h-4 w-4" />
            Save ROI scenario &amp; request quote
          </>
        )}
      </button>
    </div>
  )
}
