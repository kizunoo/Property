"use client";
import { useEffect, useState } from "react";

interface Signal {
  id: string;
  type: string;
  client_id: string;
  property_id: string | null;
  message: string;
  created_at: string;
}

let _cachedSignals: Signal[] | null = null;

export function RecentSignalsPanel({ onOpenClient }: { onOpenClient: (clientId: string) => void }) {
  const [signals, setSignals] = useState<Signal[]>(_cachedSignals ?? []);
  const [loading, setLoading] = useState(!_cachedSignals);

  useEffect(() => {
    fetch("/api/signals")
      .then((r) => r.json())
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        _cachedSignals = list;
        setSignals(list);
      })
      .catch(() => setSignals([]))
      .finally(() => setLoading(false));
  }, []);

  const dismiss = async (id: string) => {
    setSignals((prev) => {
      const updated = prev.filter((s) => s.id !== id);
      _cachedSignals = updated;
      return updated;
    }); // optimistic remove
    await fetch(`/api/signals/${id}/dismiss`, { method: "POST" });
  };

  if (signals.length === 0) return null;

  const getAccentColor = (type: string) => {
    switch (type) {
      case "first_vip":
        return "#FFD400"
      case "tier_upgrade":
        return "#FFD400"
      case "viewing_logged":
        return "#00F0FF"
      default:
        return "#A3A3A3"
    }
  }

  return (
    <div
      style={{
        border: "4px solid #000",
        boxShadow: "8px 8px 0px 0px rgba(0,0,0,1)",
        marginBottom: "28px",
        background: "#fff",
      }}
    >
      <div
        style={{
          borderBottom: "4px solid #000",
          padding: "14px 20px",
          fontWeight: 800,
          fontSize: "14px",
          textTransform: "uppercase",
          letterSpacing: "0.6px",
          background: "#f4f4f4",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span>Live Signal Feed</span>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 700,
            background: "#000",
            color: "#fff",
            padding: "2px 8px",
            border: "1px solid #000",
          }}
        >
          {signals.length} ACTIVE
        </span>
      </div>
      <div>
        {signals.map((s) => (
          <div
            key={s.id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderLeft: `8px solid ${getAccentColor(s.type)}`,
              borderBottom: "2px solid #000",
              padding: "16px 20px",
              background: "#fff",
            }}
            className="transition-colors hover:bg-neutral-50"
          >
            <button
              onClick={() => onOpenClient(s.client_id)}
              style={{
                background: "none",
                border: "none",
                textAlign: "left",
                cursor: "pointer",
                fontSize: "14px",
                fontWeight: 700,
                flex: 1,
                color: "#000",
                display: "flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 900,
                  textTransform: "uppercase",
                  padding: "2px 6px",
                  border: "2px solid #000",
                  background: getAccentColor(s.type),
                  color: "#000",
                }}
              >
                {s.type.replace("_", " ")}
              </span>
              <span>{s.message}</span>
            </button>
            <button
              onClick={() => dismiss(s.id)}
              aria-label="Dismiss"
              style={{
                background: "#000",
                color: "#fff",
                border: "2px solid #000",
                cursor: "pointer",
                fontWeight: 900,
                fontSize: "11px",
                padding: "4px 8px",
                marginLeft: "12px",
              }}
              className="transition-transform hover:scale-105"
            >
              DISMISS
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
