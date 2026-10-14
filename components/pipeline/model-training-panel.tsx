"use client";

import { useEffect, useState } from "react";
import { Brain, RefreshCw, Sparkles } from "lucide-react";

interface ModelStatus {
  trained: boolean;
  trained_at?: string;
  real_outcome_count?: number;
  synthetic_outcome_count?: number;
  test_accuracy?: number;
  test_auc?: number;
}

export function ModelTrainingPanel() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [training, setTraining] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/model_status");
      const data = await res.json();
      setStatus(data);
    } catch (err) {
      console.error("Failed to fetch model status:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleRetrain = async () => {
    setTraining(true);
    try {
      await fetch("/api/retrain_model", { method: "POST" });
      await fetchStatus();
    } catch (err) {
      console.error("Retrain error:", err);
    } finally {
      setTraining(false);
    }
  };

  return (
    <div className="relative flex flex-col gap-3 rounded-[var(--radius)] border border-border bg-white p-5 shadow-[var(--shadow-sm)] sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded-[8px] bg-foreground p-1.5 text-primary">
            <Brain className="h-4 w-4" strokeWidth={2} />
          </span>
          <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground sm:text-xs">
            Trained Prediction Model
          </span>
        </div>
        <button
          onClick={handleRetrain}
          disabled={training}
          className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border border-black bg-primary px-3 py-1 text-[11px] font-black uppercase tracking-wider text-black transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${training ? "animate-spin" : ""}`} strokeWidth={2.5} />
          {training ? "Training..." : "Retrain Model"}
        </button>
      </div>

      {loading ? (
        <div className="py-3 text-sm font-bold text-muted-foreground">Checking model status...</div>
      ) : !status?.trained ? (
        <div className="py-2 text-sm font-bold text-muted-foreground">
          No model trained yet. Click <span className="font-black text-black">&quot;Retrain Model&quot;</span> to train an initial model.
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Cold-start disclaimer banner when real outcomes = 0 */}
          {(status.real_outcome_count ?? 0) === 0 && (
            <div className="flex items-center justify-between rounded-[6px] border border-amber-300 bg-amber-50 px-3.5 py-2 text-xs text-amber-900">
              <div className="flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
                <span className="font-bold">0 Real Outcomes Recorded</span>
                <span className="text-amber-800/80">· Baseline model trained exclusively on synthetic bootstrap data until deployments close</span>
              </div>
              <span className="rounded bg-amber-200/60 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider">
                Cold Start
              </span>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-[var(--radius-sm)] border border-l-[3px] border-l-primary border-border bg-card p-3.5 shadow-[var(--shadow-xs)]">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Test Accuracy</span>
              <div className="mt-1 font-display text-2xl font-bold">
                {((status.test_accuracy ?? 0) * 100).toFixed(1)}%
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                {(status.real_outcome_count ?? 0) === 0
                  ? "Synthetic bootstrap validation (0 real outcomes)"
                  : "Logistic regression validation"}
              </div>
            </div>

            {status.test_auc != null && (
              <div className="rounded-[var(--radius-sm)] border border-l-[3px] border-l-primary border-border bg-card p-3.5 shadow-[var(--shadow-xs)]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Discrimination (AUC)</span>
                <div className="mt-1 font-display text-2xl font-bold font-mono">
                  {status.test_auc.toFixed(3)}
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">ROC area under curve</div>
              </div>
            )}

            <div className={`rounded-[var(--radius-sm)] border border-l-[3px] border-border bg-card p-3.5 shadow-[var(--shadow-xs)] ${(status.real_outcome_count ?? 0) === 0 ? "border-l-amber-500" : "border-l-neutral-300"}`}>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Sample Composition</span>
              <div className="mt-1 font-mono text-sm font-bold leading-tight text-foreground">
                <span className={(status.real_outcome_count ?? 0) === 0 ? "text-amber-700 font-black" : ""}>
                  {status.real_outcome_count ?? 0} Real
                </span>{" "}
                &middot; {status.synthetic_outcome_count ?? 300} Synthetic
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                {(status.real_outcome_count ?? 0) === 0
                  ? "Awaiting first closed deployment outcome"
                  : "Real outcomes weighted 5x heavier"}
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-[8px] bg-[#FFF8DC] border border-[#FFE48A] p-3 text-xs text-[#8a6d00]">
            <Sparkles className="h-4 w-4 shrink-0 mt-0.5 text-[#8a6d00]" strokeWidth={2} />
            <div className="leading-relaxed">
              Trained on <strong>{status.real_outcome_count ?? 0} real</strong> outcome{(status.real_outcome_count ?? 0) === 1 ? "" : "s"} and{" "}
              <strong>{status.synthetic_outcome_count ?? 300} synthetic</strong> examples. Real outcomes are weighted 5x more heavily — as more deals are marked Won/Lost, this model learns progressively more from actual results.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
