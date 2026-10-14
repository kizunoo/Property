"use client";

import { useEffect, useState } from "react";
import { DecryptedText } from "@/components/animation/decrypted-text";
import { Sparkles, RefreshCw, AlertCircle } from "lucide-react";

interface BriefingItem {
  client_id: string;
  client_name: string;
  property_name: string;
  neighborhood: string;
  expected_value: number;
  briefing?: string;
  reasoning: string;
}

// Module-level cache so switching tabs within the session is instantaneous and never unmounts/disappears
let _cachedBriefingItems: BriefingItem[] | null = null;

export function AIBriefingHero({ onOpenClient }: { onOpenClient: (clientId: string) => void }) {
  const [items, setItems] = useState<BriefingItem[]>(_cachedBriefingItems ?? []);
  const [loading, setLoading] = useState(!_cachedBriefingItems);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState<number>(() => Date.now());

  const fetchBriefing = (force = false) => {
    if (!force && _cachedBriefingItems && _cachedBriefingItems.length > 0) {
      setItems(_cachedBriefingItems);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    fetch("/api/dashboard_briefing")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          _cachedBriefingItems = data;
          setItems(data);
          setRefreshKey(Date.now());
        } else {
          setItems([]);
        }
      })
      .catch((err: Error) => {
        console.error("Failed to load AI briefing:", err);
        setError(err.message ?? "Failed to load briefing");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchBriefing();
  }, []);

  const handleRefresh = () => {
    _cachedBriefingItems = null;
    fetchBriefing(true);
  };

  if (items.length === 0 && !loading && !error) return null;

  return (
    <div className="mb-6 overflow-hidden rounded-[var(--radius)] border border-border bg-card shadow-[var(--shadow-sm)]">
      {/* Signature Black Header — matches AI Pipeline Insight */}
      <div className="flex items-center justify-between gap-3 border-b border-neutral-800 bg-black px-5 py-3.5 sm:px-6">
        <div className="flex items-center gap-2 text-white">
          <Sparkles className="h-4 w-4 text-primary" strokeWidth={2.5} />
          <span className="text-xs font-bold uppercase tracking-wider text-white sm:text-sm">
            AI Deployment Briefing
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-[var(--radius-sm)] bg-primary px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-black sm:text-xs">
            Groq · GPT-OSS 120B
          </span>
          <button
            type="button"
            aria-label="Refresh briefing"
            disabled={loading}
            onClick={handleRefresh}
            title="Re-generate briefing"
            className="flex items-center justify-center rounded-[var(--radius-sm)] border border-neutral-700 bg-neutral-900 p-1.5 text-white transition-colors hover:bg-neutral-800 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${loading ? "animate-spin text-primary" : "text-white"}`}
              strokeWidth={2.5}
            />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-4 sm:px-6 sm:py-5">
        {/* Loading Shimmer */}
        {loading && items.length === 0 && (
          <div className="flex flex-col gap-2.5 py-2">
            <div className="h-4 w-full animate-pulse bg-black/10" />
            <div className="h-4 w-[85%] animate-pulse bg-black/10" />
            <div className="h-4 w-[65%] animate-pulse bg-black/10" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="flex items-start gap-3 border border-neutral-200 bg-[#fff0f0] px-4 py-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-black" strokeWidth={2.5} />
            <div>
              <div className="text-xs font-black uppercase tracking-wider">Briefing unavailable</div>
              <div className="mt-1 text-xs font-bold text-muted-foreground">{error}</div>
            </div>
          </div>
        )}

        {/* Top Opportunities Grid */}
        {items.length > 0 && (
          <div className="flex flex-col gap-3">
            <div className="h-1.5 w-16 border border-black bg-primary mb-2" />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 divide-y md:divide-y-0 md:divide-x divide-border">
              {items.map((item) => (
                <button
                  key={item.client_id}
                  onClick={() => onOpenClient(item.client_id)}
                  className="group flex flex-col pt-3 md:pt-0 md:px-4 first:md:pl-0 last:md:pr-0 text-left transition-colors focus:outline-none"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-foreground group-hover:text-primary transition-colors underline-offset-2 group-hover:underline">
                      {item.client_name}
                    </span>
                    <span className="font-mono text-xs font-bold bg-neutral-100 text-neutral-900 border border-neutral-200 px-2 py-0.5 rounded-[var(--radius-sm)] shrink-0">
                      RM {Math.round(item.expected_value).toLocaleString()}
                    </span>
                  </div>

                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground truncate">
                    {item.property_name} · {item.neighborhood}
                  </div>

                  <div className="font-mono text-xs sm:text-[13px] leading-relaxed">
                    <DecryptedText
                      key={`${item.client_id}-${refreshKey}`}
                      text={item.briefing || item.reasoning}
                      animateOn="view"
                      sequential={true}
                      speed={20}
                      maxIterations={10}
                      useOriginalCharsOnly={true}
                      className="decrypt-revealed text-xs sm:text-[13px] font-bold leading-relaxed tracking-wide text-neutral-900"
                      encryptedClassName="decrypt-encrypted text-xs sm:text-[13px] font-bold leading-relaxed tracking-wide text-neutral-400"
                    />
                  </div>
                </button>
              ))}
            </div>

            <div className="mt-4 border-t border-border pt-3 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Top 3 high-probability deployment opportunities generated in real time
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
