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
      case "tier_upgrade":
        return "#FFD400"
      case "viewing_logged":
        return "#00F0FF"
      default:
        return "#A3A3A3"
    }
  }

  return (
    <div className="mb-7 overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.08)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-200 bg-neutral-50 px-5 py-3.5">
        <span className="text-[13px] font-semibold uppercase tracking-wider text-neutral-700">
          Live Signal Feed
        </span>
        <span className="rounded-md bg-neutral-900 px-2 py-0.5 text-[11px] font-semibold text-white">
          {signals.length} ACTIVE
        </span>
      </div>

      {/* Signal rows */}
      <div>
        {signals.map((s) => (
          <div
            key={s.id}
            style={{ borderLeft: `4px solid ${getAccentColor(s.type)}` }}
            className="flex items-center justify-between border-b border-neutral-100 bg-white px-5 py-4 last:border-b-0 transition-colors hover:bg-neutral-50"
          >
            <button
              onClick={() => onOpenClient(s.client_id)}
              className="flex flex-1 items-center gap-3 text-left"
            >
              <span
                style={{ background: getAccentColor(s.type) }}
                className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-900"
              >
                {s.type.replace("_", " ")}
              </span>
              <span className="text-sm font-medium text-neutral-800">{s.message}</span>
            </button>
            <button
              onClick={() => dismiss(s.id)}
              aria-label="Dismiss"
              className="ml-3 rounded-md border border-neutral-200 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-neutral-500 transition-colors hover:border-neutral-400 hover:text-neutral-800"
            >
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
