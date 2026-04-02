import { modelDriftOptions, modelHealthOptions, modelHistoryOptions } from "@/api/queries";
import type { ModelHealth } from "@/api/types";
import { formatDate, formatPercent, formatStatusLabel } from "@/lib/utils";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const Route = createFileRoute("/_authenticated/model-health/")({
  loader: ({ context }) =>
    Promise.all([
      context.queryClient.ensureQueryData(modelHealthOptions()),
      context.queryClient.ensureQueryData(modelDriftOptions()),
    ]),
  component: ModelHealthPage,
});

function driftStatusColor(status: string | null): string {
  switch (status) {
    case "stable":
      return "text-green-700 bg-green-50 border-green-200";
    case "warning":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "drift":
      return "text-red-700 bg-red-50 border-red-200";
    default:
      return "text-gray-500 bg-gray-50 border-gray-200";
  }
}

function MetricStat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-gray-900">
        {value != null ? formatPercent(value) : "—"}
      </p>
    </div>
  );
}

function ModelHistoryChart({ name }: { name: string }) {
  const { data, isLoading } = useQuery(modelHistoryOptions(name));

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-gray-400">
        Loading history…
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-400 italic">
        No history data available.
      </p>
    );
  }

  const chartData = data.map((snap) => ({
    date: snap.snapshot_at ? snap.snapshot_at.slice(0, 10) : "—",
    auc: snap.auc_score != null ? Math.round(snap.auc_score * 1000) / 1000 : null,
    precision: snap.precision_score != null ? Math.round(snap.precision_score * 1000) / 1000 : null,
  }));

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10 }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis domain={[0, 1]} tick={{ fontSize: 10 }} />
        <Tooltip formatter={(v: number) => formatPercent(v)} />
        <Line
          type="monotone"
          dataKey="auc"
          name="AUC"
          stroke="#6366f1"
          dot={false}
          strokeWidth={2}
        />
        <Line
          type="monotone"
          dataKey="precision"
          name="Precision"
          stroke="#22c55e"
          dot={false}
          strokeWidth={2}
          strokeDasharray="4 2"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function ModelCard({ model }: { model: ModelHealth }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            {model.model_name}
          </h3>
          {model.model_version && (
            <span className="mt-1 inline-block rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-500">
              v{model.model_version}
            </span>
          )}
        </div>
        <span
          className={`rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${driftStatusColor(model.drift_status)}`}
        >
          {model.drift_status ?? "unknown"}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-4 border-t border-gray-100 pt-4">
        <MetricStat label="AUC" value={model.auc_score} />
        <MetricStat label="Precision" value={model.precision_score} />
        <MetricStat label="Recall" value={model.recall_score} />
      </div>

      {model.psi_score != null && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm">
          <span className="text-gray-500">PSI:</span>
          <span className="font-medium text-gray-900">
            {model.psi_score.toFixed(4)}
          </span>
          <span
            className={`ml-auto rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${driftStatusColor(model.drift_status)}`}
          >
            {model.drift_status ?? "—"}
          </span>
        </div>
      )}

      {model.trained_at && (
        <p className="mt-3 text-xs text-gray-400">
          Trained {formatDate(model.trained_at)}
          {model.training_sample_count != null &&
            ` · ${model.training_sample_count.toLocaleString()} samples`}
        </p>
      )}

      <button
        type="button"
        onClick={() => setExpanded((x) => !x)}
        className="mt-4 flex w-full items-center justify-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
      >
        {expanded ? (
          <>
            <ChevronUp className="h-3.5 w-3.5" />
            Hide History
          </>
        ) : (
          <>
            <ChevronDown className="h-3.5 w-3.5" />
            View History
          </>
        )}
      </button>

      {expanded && (
        <div className="mt-4 border-t border-gray-100 pt-4">
          <p className="mb-2 text-xs font-medium text-gray-500">
            AUC &amp; Precision over time
          </p>
          <ModelHistoryChart name={model.model_name} />
        </div>
      )}
    </div>
  );
}

function ModelHealthPage() {
  const { data: models } = useSuspenseQuery(modelHealthOptions());
  const { data: drifts } = useSuspenseQuery(modelDriftOptions());

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Model Health</h1>
        <p className="mt-1 text-sm text-gray-500">
          ML model performance metrics, drift detection, and training history
        </p>
      </div>

      {/* Drift Summary */}
      {drifts && drifts.length > 0 && (
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {drifts.map((d) => (
            <div
              key={d.model_name}
              className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-900">
                  {d.model_name}
                </p>
                <span
                  className={`rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${driftStatusColor(d.drift_status)}`}
                >
                  {d.drift_status}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">{d.recommendation}</p>
              {d.psi_score != null && (
                <p className="mt-2 text-xs text-gray-400">
                  PSI: {d.psi_score.toFixed(4)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Model Cards */}
      {models && models.length > 0 ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {models.map((model) => (
            <ModelCard key={model.model_name} model={model} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center shadow-sm">
          <p className="text-gray-400">
            No model health records found. Models will appear after the first
            training run.
          </p>
        </div>
      )}
    </div>
  );
}
