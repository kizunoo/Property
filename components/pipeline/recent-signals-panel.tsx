"use client";

import { useEffect, useState, useMemo } from "react";
import { Clock, TrendingUp, Sparkles, Eye, ChevronDown, ChevronUp, Settings, CalendarCheck, CalendarX, Bell, MessageSquare } from "lucide-react";

interface Signal {
  id: string;
  type: string;
  client_id: string | null;
  property_id: string | null;
  message: string;
  created_at: string;
}

type SignalFilterTab = "ALL" | "PRICE" | "TIER";

const INITIAL_VISIBLE_COUNT = 5;
let _cachedSignals: Signal[] | null = null;

function formatSignalTime(dateString: string): { relative: string; exact: string } {
  if (!dateString) return { relative: "Just now", exact: "" };
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return { relative: "Just now", exact: "" };

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  let relative = "Just now";
  if (diffMins >= 1 && diffMins < 60) {
    relative = `${diffMins}m ago`;
  } else if (diffHours >= 1 && diffHours < 24) {
    relative = `${diffHours}h ago`;
  } else if (diffDays >= 1) {
    relative = `${diffDays}d ago`;
  }

  const exact = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
  return { relative, exact };
}

function cleanSignalMessage(raw: string): string {
  if (!raw) return "";
  // Check if string repeats prefix format: "Foo price rose 3.7% — Foo jumped 3.7% to..."
  const parts = raw.split(" — ");
  if (parts.length >= 2) {
    const first = parts[0].trim();
    const rest = parts.slice(1).join(" — ").trim();
    // Check if the remainder begins with the same property name / essence as the first
    const firstBase = first.split(/\s+(?:price|rose|dropped|jumped|fell|\d)/i)[0].trim().toLowerCase();
    if (firstBase.length > 3 && rest.toLowerCase().startsWith(firstBase)) {
      return rest;
    }
  }
  return raw;
}

export function RecentSignalsPanel({
  onOpenClient,
  onOpenProperty,
}: {
  onOpenClient: (clientId: string) => void;
  onOpenProperty?: (propertyId: string) => void;
}) {
  const [signals, setSignals] = useState<Signal[]>(_cachedSignals ?? []);
  const [loading, setLoading] = useState(!_cachedSignals);
  const [activeTab, setActiveTab] = useState<SignalFilterTab>("ALL");
  const [expanded, setExpanded] = useState(false);

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
    });
    await fetch(`/api/signals/${id}/dismiss`, { method: "POST" });
  };

  const priceSignals = useMemo(
    () => signals.filter((s) => s.type === "price_change"),
    [signals]
  );

  const tierSignals = useMemo(
    () => signals.filter((s) => s.type !== "price_change"),
    [signals]
  );

  const displayedSignals = useMemo(() => {
    if (activeTab === "PRICE") return priceSignals;
    if (activeTab === "TIER") return tierSignals;
    return signals;
  }, [activeTab, signals, priceSignals, tierSignals]);

  const visibleSignals = useMemo(() => {
    return expanded ? displayedSignals : displayedSignals.slice(0, INITIAL_VISIBLE_COUNT);
  }, [displayedSignals, expanded]);

  const hasMore = displayedSignals.length > INITIAL_VISIBLE_COUNT;
  const remainingCount = displayedSignals.length - INITIAL_VISIBLE_COUNT;

  if (signals.length === 0 && !loading) return null;

  const getSignalMeta = (type: string) => {
    switch (type) {
      case "price_change":
        return {
          label: "Price Change",
          badgeBg: "bg-amber-400 text-black border-amber-500",
          borderAccent: "border-l-amber-400",
          icon: TrendingUp,
        };
      case "first_vip":
        return {
          label: "High-Fit Prospect",
          badgeBg: "bg-primary text-black border-primary",
          borderAccent: "border-l-primary",
          icon: Sparkles,
        };
      case "tier_upgrade":
        return {
          label: "Tier Upgrade",
          badgeBg: "bg-primary text-black border-primary",
          borderAccent: "border-l-primary",
          icon: Sparkles,
        };
      case "viewing_logged":
        return {
          label: "Demo Logged",
          badgeBg: "bg-cyan-400 text-black border-cyan-500",
          borderAccent: "border-l-cyan-400",
          icon: Eye,
        };
      case "whatsapp_meeting_booked":
        return {
          label: "WhatsApp Auto-Booked",
          badgeBg: "bg-emerald-600 text-white border-emerald-700",
          borderAccent: "border-l-emerald-600",
          icon: CalendarCheck,
        };
      case "whatsapp_human_handoff":
        return {
          label: "Rep Action Required",
          badgeBg: "bg-amber-500 text-black border-amber-600 font-bold",
          borderAccent: "border-l-amber-500",
          icon: Bell,
        };
      case "whatsapp_pitch_declined":
        return {
          label: "Pitch Declined",
          badgeBg: "bg-neutral-600 text-white border-neutral-700",
          borderAccent: "border-l-neutral-600",
          icon: CalendarX,
        };
      case "client_preferences_updated":
        return {
          label: "Preferences Updated",
          badgeBg: "bg-blue-100 text-blue-800 border-blue-200",
          borderAccent: "border-l-blue-400",
          icon: Settings,
        };
      case "whatsapp_processing_error":
        return {
          label: "WhatsApp Warning",
          badgeBg: "bg-rose-100 text-rose-800 border-rose-300",
          borderAccent: "border-l-rose-500",
          icon: Bell,
        };
      default:
        return {
          label: (type || "Signal").replace(/_/g, " "),
          badgeBg: "bg-neutral-200 text-neutral-800 border-neutral-300",
          borderAccent: "border-l-neutral-400",
          icon: Sparkles,
        };
    }
  };

  return (
    <div className="mb-7 overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-[0px_2px_8px_rgba(0,0,0,0.06)]">
      {/* Header with 2 dedicated category feeds */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-200 bg-neutral-50/80 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-bold uppercase tracking-wider text-neutral-700">
            Live Signal Feed
          </span>
          <span className="rounded bg-black px-2 py-0.5 font-mono text-[10px] font-bold text-white">
            {signals.length} ACTIVE
          </span>
        </div>

        {/* Feed tabs */}
        <div className="flex items-center gap-1 rounded-lg border border-neutral-200 bg-white p-1 shadow-sm">
          <button
            onClick={() => {
              setActiveTab("ALL");
            }}
            className={`rounded px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-all ${
              activeTab === "ALL"
                ? "bg-black text-white shadow-sm"
                : "text-neutral-500 hover:text-neutral-900"
            }`}
          >
            All ({signals.length})
          </button>
          <button
            onClick={() => {
              setActiveTab("PRICE");
            }}
            className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-all ${
              activeTab === "PRICE"
                ? "bg-amber-400 text-black shadow-sm"
                : "text-neutral-500 hover:text-neutral-900"
            }`}
          >
            <TrendingUp className="h-3 w-3" strokeWidth={2.5} />
            Price Changes ({priceSignals.length})
          </button>
          <button
            onClick={() => {
              setActiveTab("TIER");
            }}
            className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-all ${
              activeTab === "TIER"
                ? "bg-primary text-black shadow-sm"
                : "text-neutral-500 hover:text-neutral-900"
            }`}
          >
            <Sparkles className="h-3 w-3" strokeWidth={2.5} />
            Tier Movements ({tierSignals.length})
          </button>
        </div>
      </div>

      {/* Signal Rows */}
      {displayedSignals.length === 0 ? (
        <div className="px-5 py-8 text-center text-xs font-semibold text-neutral-400">
          No active signals in this category.
        </div>
      ) : (
        <div className="divide-y divide-neutral-100">
          {visibleSignals.map((s) => {
            const meta = getSignalMeta(s.type);
            const Icon = meta.icon;
            const time = formatSignalTime(s.created_at);
            const cleanMsg = cleanSignalMessage(s.message);

            return (
              <div
                key={s.id}
                className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-l-4 ${meta.borderAccent} bg-white px-4 py-3.5 sm:px-5 transition-colors hover:bg-neutral-50/80`}
              >
                <button
                  onClick={() => {
                    if (s.client_id) {
                      onOpenClient(s.client_id);
                    } else if (s.property_id && onOpenProperty) {
                      onOpenProperty(s.property_id);
                    }
                  }}
                  className="flex flex-1 items-start sm:items-center gap-3 text-left group"
                >
                  <span
                    className={`inline-flex items-center gap-1 shrink-0 rounded border px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${meta.badgeBg}`}
                  >
                    <Icon className="h-2.5 w-2.5" strokeWidth={3} />
                    {meta.label}
                  </span>

                  <div className="flex-1">
                    <span className="text-sm font-medium text-neutral-900 group-hover:text-black transition-colors leading-snug">
                      {cleanMsg}
                    </span>
                  </div>
                </button>

                {/* Time + Dismiss action */}
                <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-1 sm:pt-0 border-t sm:border-t-0 border-neutral-100">
                  <div
                    className="flex items-center gap-1 font-mono text-[11px] text-neutral-500"
                    title={time.exact ? `Recorded at ${time.exact}` : undefined}
                  >
                    <Clock className="h-3 w-3 text-neutral-400" strokeWidth={2} />
                    <span>{time.relative}</span>
                    {time.exact && (
                      <span className="text-neutral-400 hidden md:inline">({time.exact})</span>
                    )}
                  </div>

                  <button
                    onClick={() => dismiss(s.id)}
                    aria-label="Dismiss signal"
                    className="rounded border border-neutral-200 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-neutral-500 transition-colors hover:border-neutral-400 hover:bg-neutral-100 hover:text-neutral-900"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Show More / Show Less footer */}
      {hasMore && (
        <div className="border-t border-neutral-200 bg-neutral-50/60 px-4 py-2.5 text-center sm:px-5">
          <button
            onClick={() => setExpanded((prev) => !prev)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-200 bg-white px-4 py-1.5 text-xs font-bold text-neutral-700 shadow-sm transition-all hover:bg-neutral-100 hover:text-neutral-900"
          >
            {expanded ? (
              <>
                <ChevronUp className="h-3.5 w-3.5" strokeWidth={2.5} />
                Show Less (collapse to 5)
              </>
            ) : (
              <>
                <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.5} />
                Show More ({remainingCount} more)
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
