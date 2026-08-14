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

export function RecentSignalsPanel({ onOpenClient }: { onOpenClient: (clientId: string) => void }) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/signals")
      .then((r) => r.json())
      .then((data) => setSignals(Array.isArray(data) ? data : []))
      .catch(() => setSignals([]))
      .finally(() => setLoading(false));
  }, []);

  const dismiss = async (id: string) => {
    setSignals((prev) => prev.filter((s) => s.id !== id)); // optimistic remove
    await fetch(`/api/signals/${id}/dismiss`, { method: "POST" });
  };

  if (loading) return null;
  if (signals.length === 0) return null;

  return (
    <div style={{
      border: "3px solid #000",
      boxShadow: "6px 6px 0px 0px rgba(0,0,0,1)",
      marginBottom: "24px",
      background: "#fff",
    }}>
      <div style={{
        borderBottom: "3px solid #000",
        padding: "10px 16px",
        fontWeight: 700,
        fontSize: "13px",
        textTransform: "uppercase",
        letterSpacing: "0.4px",
      }}>
        Recent Signals
      </div>
      <div>
        {signals.map((s) => (
          <div
            key={s.id}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderLeft: "6px solid #FFD400",
              borderBottom: "1px solid #ddd",
              padding: "12px 16px",
            }}
          >
            <button
              onClick={() => onOpenClient(s.client_id)}
              style={{
                background: "none",
                border: "none",
                textAlign: "left",
                cursor: "pointer",
                fontSize: "14px",
                flex: 1,
              }}
            >
              {s.message}
            </button>
            <button
              onClick={() => dismiss(s.id)}
              aria-label="Dismiss"
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                fontWeight: 700,
                padding: "0 8px",
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
