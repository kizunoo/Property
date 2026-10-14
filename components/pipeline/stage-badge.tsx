import React from "react"

export const STAGE_LABELS: Record<string, { label: string; color: string; bg: string; border?: string }> = {
  new: { label: "New", color: "#666666", bg: "#f0f0f0", border: "#e0e0e0" },
  contacted: { label: "Contacted", color: "#8a6d00", bg: "#FFF8DC", border: "#f3e292" },
  viewing: { label: "Viewing", color: "#8a6d00", bg: "#FFF3B0", border: "#f0d96d" },
  negotiation: { label: "Negotiation", color: "#000000", bg: "#FFD400", border: "#e6be00" },
  closed_won: { label: "Closed — Won", color: "#000000", bg: "#FFD400", border: "#e6be00" },
  closed_lost: { label: "Closed — Lost", color: "#666666", bg: "#f0f0f0", border: "#e0e0e0" },
}

export function StageBadge({
  stage,
  className = "",
}: {
  stage?: string | null
  className?: string
}) {
  const normalizedKey = (stage || "new").toLowerCase()
  const s = STAGE_LABELS[normalizedKey] ?? STAGE_LABELS.new

  return (
    <span
      className={`inline-flex items-center justify-center font-bold tracking-wide uppercase transition-colors shrink-0 ${className}`}
      style={{
        fontSize: "10px",
        padding: "2px 8px",
        borderRadius: "6px",
        background: s.bg,
        color: s.color,
        border: s.border ? `1px solid ${s.border}` : undefined,
      }}
    >
      {s.label}
    </span>
  )
}
