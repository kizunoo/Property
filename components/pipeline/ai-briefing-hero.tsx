"use client"

import { useEffect, useState } from "react"
import { DecryptedText } from "@/components/animation/decrypted-text"
import { Sparkles } from "lucide-react"

interface BriefingItem {
  client_id: string
  client_name: string
  property_name: string
  neighborhood: string
  expected_value: number
  briefing?: string
  reasoning: string
}

// Module-level cache so switching tabs within the session is instantaneous and never unmounts/disappears
let _cachedBriefingItems: BriefingItem[] | null = null

export function AIBriefingHero({ onOpenClient }: { onOpenClient: (clientId: string) => void }) {
  const [items, setItems] = useState<BriefingItem[]>(_cachedBriefingItems ?? [])
  const [loading, setLoading] = useState(!_cachedBriefingItems)

  useEffect(() => {
    fetch("/api/dashboard_briefing")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          _cachedBriefingItems = data
          setItems(data)
        }
      })
      .catch((err) => console.error("Failed to load AI briefing:", err))
      .finally(() => setLoading(false))
  }, [])

  if (items.length === 0) return null

  return (
    <div
      style={{
        border: "4px solid #000",
        boxShadow: "10px 10px 0px 0px rgba(0,0,0,1)",
        marginBottom: "28px",
        background: "#000",
        color: "#fff",
      }}
    >
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "3px solid #FFD400",
          fontWeight: 800,
          fontSize: "14px",
          textTransform: "uppercase",
          letterSpacing: "0.6px",
          color: "#FFD400",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <Sparkles className="h-4 w-4 text-[#FFD400]" />
        <span>AI Pipeline Briefing — Top Opportunities Right Now</span>
      </div>
      <div
        className="grid grid-cols-1 md:grid-cols-3"
        style={{
          gap: "1px",
          background: "#333",
        }}
      >
        {items.map((item) => (
          <button
            key={item.client_id}
            onClick={() => onOpenClient(item.client_id)}
            style={{
              background: "#000",
              border: "none",
              textAlign: "left",
              padding: "18px",
              cursor: "pointer",
              color: "#fff",
            }}
            className="transition-colors hover:bg-neutral-900 focus:outline-none"
          >
            <div
              style={{
                fontSize: "12px",
                color: "#FFD400",
                fontWeight: 700,
                marginBottom: "6px",
              }}
            >
              {item.client_name} · RM {Math.round(item.expected_value).toLocaleString()}
            </div>
            <div
              style={{
                fontSize: "13px",
                lineHeight: 1.5,
                fontFamily: "var(--font-mono)",
              }}
            >
              <DecryptedText
                text={item.briefing || item.reasoning}
                animateOn="view"
                sequential
                speed={12}
                maxIterations={8}
                useOriginalCharsOnly
                className="briefing-revealed"
                encryptedClassName="briefing-encrypted"
              />
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
