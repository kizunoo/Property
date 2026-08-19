"use client"

import { useState } from "react"
import { DecryptedText } from "@/components/animation/decrypted-text"

export function useChartInsight() {
  const [insight, setInsight] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const fetchInsight = async (sliceType: string, sliceData: Record<string, any>) => {
    setLoading(true)
    setInsight(null)
    try {
      const res = await fetch("/api/chart_insight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slice_type: sliceType, slice_data: sliceData }),
      })
      const data = await res.json()
      setInsight(data.insight ?? "Insight generation failed")
    } catch (err) {
      setInsight("Failed to generate insight.")
    } finally {
      setLoading(false)
    }
  }

  return { insight, loading, fetchInsight }
}

export function ChartInsightPanel({ insight, loading }: { insight: string | null; loading: boolean }) {
  if (!loading && !insight) return null
  return (
    <div
      style={{
        marginTop: "12px",
        padding: "14px 18px",
        background: "#000",
        color: "#fff",
        border: "3px solid #000",
        boxShadow: "4px 4px 0px 0px rgba(0,0,0,1)",
        fontFamily: "var(--font-mono)",
        fontSize: "13px",
        lineHeight: 1.5,
      }}
    >
      {loading ? (
        <span className="animate-pulse text-[#FFD400]">Analyzing selected data slice with Groq AI…</span>
      ) : (
        <DecryptedText
          text={insight!}
          animateOn="view"
          sequential
          speed={15}
          maxIterations={10}
          useOriginalCharsOnly
          className="text-white font-bold"
          encryptedClassName="text-[#666]"
        />
      )}
    </div>
  )
}
