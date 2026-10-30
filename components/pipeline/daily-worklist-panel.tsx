"use client";
import { useEffect, useState } from "react";
import { DecryptedText } from "@/components/animation/decrypted-text";
import { priceTextForRobotName, type DisplayPriceByNameEntry } from "@/lib/display-price";

interface WorklistEntry {
  client_id: string;
  client_name: string;
  property_id: string;
  property_name: string;
  neighborhood: string;
  tier: string;
  blended_probability: number;
  blended_ev: number | null;
  reason: string;
}

export function DailyWorklistPanel({
  agentId,
  onGenerateInvite,
  onScheduleViewing,
  byName,
}: {
  agentId?: string | null
  onGenerateInvite: (clientId: string, propertyId: string) => void;
  onScheduleViewing: (clientId: string, propertyId: string) => void;
  byName?: Record<string, DisplayPriceByNameEntry | undefined>;
}) {
  const [entries, setEntries] = useState<WorklistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchWorklist = (force = false) => {
    const params = new URLSearchParams()
    if (force) params.set("force_refresh", "true")
    if (agentId) params.set("agent_id", agentId)
    const qs = params.toString()
    fetch(`/api/daily_worklist${qs ? `?${qs}` : ""}`)

      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setEntries(data);
        } else {
          setEntries([]);
        }
      })
      .catch(() => setEntries([]))
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  };

  useEffect(() => {
    fetchWorklist();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchWorklist(true);
  };

  if (loading) return null;

  return (
    <div
      style={{
        background: "#000",
        color: "#fff",
        borderRadius: "12px",
        boxShadow: "0px 4px 20px rgba(0,0,0,0.15)",
        overflow: "hidden",
        marginBottom: "24px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 22px",
          borderBottom: "1px solid #333",
        }}
      >
        <span style={{ fontWeight: 700, fontSize: "14px", textTransform: "uppercase", color: "#FFD400" }}>
          Today&apos;s Outreach Worklist — Top {entries.length} to Contact
        </span>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          style={{
            padding: "6px 14px",
            borderRadius: "8px",
            border: "1px solid #FFD400",
            background: "transparent",
            color: "#FFD400",
            fontWeight: 700,
            fontSize: "11px",
            textTransform: "uppercase",
            cursor: refreshing ? "default" : "pointer",
          }}
        >
          {refreshing ? "Refreshing..." : "Regenerate"}
        </button>
      </div>

      {entries.length === 0 ? (
        <div style={{ padding: "28px", textAlign: "center", color: "#999", fontSize: "13px" }}>
          No pending companies to contact right now — all prospects are either scheduled for demos or deployed.
        </div>
      ) : (
        entries.map((e, i) => (
          <div
            key={e.client_id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "16px 22px",
              borderBottom: i < entries.length - 1 ? "1px solid #222" : "none",
              gap: "16px",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
                <span style={{ fontWeight: 700, fontSize: "14px" }}>{e.client_name}</span>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "6px",
                    background: e.tier === "TIER_1" ? "#FFD400" : "#333",
                    color: e.tier === "TIER_1" ? "#000" : "#fff",
                  }}
                >
                  {e.tier === "TIER_1" ? "HIGH-FIT" : e.tier === "TIER_2" ? "POSSIBLE-FIT" : "LOW-FIT"}
                </span>
                <span style={{ fontSize: "12px", color: "#999" }}>
                  {e.property_name} ·{" "}
                  {e.blended_ev != null
                    ? `RM ${Math.round(e.blended_ev).toLocaleString()}`
                    : priceTextForRobotName(e.property_name, byName) ?? "Awaiting price"}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "#ccc", fontFamily: "var(--font-mono)" }}>
                <DecryptedText text={e.reason} animateOn="view" sequential speed={18} useOriginalCharsOnly />
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px", flexShrink: 0 }}>
              <button
                onClick={() => onGenerateInvite(e.client_id, e.property_id)}
                style={{
                  padding: "8px 14px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#FFD400",
                  color: "#000",
                  fontWeight: 700,
                  fontSize: "11px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                Pitch
              </button>
              <button
                onClick={() => onScheduleViewing(e.client_id, e.property_id)}
                style={{
                  padding: "8px 14px",
                  borderRadius: "8px",
                  border: "1px solid #555",
                  background: "transparent",
                  color: "#fff",
                  fontWeight: 700,
                  fontSize: "11px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                Schedule Demo
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
