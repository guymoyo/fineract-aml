import { alertDetailOptions } from "@/api/queries";
import { useSubmitReview } from "@/api/mutations";
import type { LLMReport, ReviewDecision, ScreeningResult } from "@/api/types";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import {
  alertStatusColor,
  formatCurrency,
  formatDate,
  formatStatusLabel,
  riskLevelColor,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import {
  ArrowLeft,
  CheckCircle,
  FileWarning,
  Shield,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { useState } from "react";

function screeningStatusColor(status: ScreeningResult["status"]): string {
  switch (status) {
    case "clear":
      return "text-green-700 bg-green-50 border-green-200";
    case "potential_match":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "confirmed_match":
      return "text-red-700 bg-red-50 border-red-200";
    case "false_positive":
      return "text-gray-500 bg-gray-50 border-gray-200";
  }
}

export const Route = createFileRoute("/_authenticated/alerts/$alertId")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(alertDetailOptions(params.alertId)),
  component: AlertDetailPage,
});

function AlertDetailPage() {
  const { alertId } = Route.useParams();
  const { data: alert } = useSuspenseQuery(alertDetailOptions(alertId));
  const submitReview = useSubmitReview(alertId);

  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [notes, setNotes] = useState("");
  const [showReviewForm, setShowReviewForm] = useState(false);

  const tx = alert.transaction;
  const triggeredRules: string[] = alert.triggered_rules
    ? JSON.parse(alert.triggered_rules)
    : [];

  let llmReport: LLMReport | null = null;
  try {
    if (alert.investigation_report) {
      llmReport = JSON.parse(alert.investigation_report) as LLMReport;
    }
  } catch {
    // malformed JSON — skip
  }

  const screening = alert.screening_result ?? null;

  const canReview =
    alert.status === "pending" || alert.status === "under_review";

  const handleSubmitReview = () => {
    if (!decision) return;
    submitReview.mutate(
      { decision, notes: notes || undefined },
      {
        onSuccess: () => {
          setShowReviewForm(false);
          setDecision(null);
          setNotes("");
        },
      },
    );
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/alerts"
          className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Alerts
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{alert.title}</h1>
            <p className="mt-1 text-sm text-gray-500">{alert.description}</p>
          </div>
          <StatusBadge
            status={alert.status}
            colorClass={alertStatusColor(alert.status)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main Content */}
        <div className="space-y-6 lg:col-span-2">
          {/* Transaction Details */}
          {tx && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">
                Transaction Details
              </h2>
              <dl className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-sm text-gray-500">Amount</dt>
                  <dd className="text-lg font-semibold text-gray-900">
                    {formatCurrency(tx.amount, tx.currency)}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Type</dt>
                  <dd className="text-sm font-medium capitalize text-gray-900">
                    {tx.transaction_type}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Account ID</dt>
                  <dd className="text-sm font-mono text-gray-900">
                    {tx.fineract_account_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Client ID</dt>
                  <dd className="text-sm font-mono text-gray-900">
                    {tx.fineract_client_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Transaction ID</dt>
                  <dd className="text-sm font-mono text-gray-900">
                    {tx.fineract_transaction_id}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Date</dt>
                  <dd className="text-sm text-gray-900">
                    {formatDate(tx.transaction_date)}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Risk Level</dt>
                  <dd>
                    {tx.risk_level ? (
                      <StatusBadge
                        status={tx.risk_level}
                        colorClass={riskLevelColor(tx.risk_level)}
                      />
                    ) : (
                      <span className="text-sm text-gray-400">Not scored</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Anomaly Score</dt>
                  <dd>
                    <RiskScoreBar score={tx.anomaly_score} />
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {/* Triggered Rules */}
          {triggeredRules.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">
                Triggered Rules
              </h2>
              <ul className="mt-4 space-y-2">
                {triggeredRules.map((rule) => (
                  <li
                    key={rule}
                    className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
                  >
                    <FileWarning className="h-4 w-4 flex-shrink-0" />
                    {formatStatusLabel(rule)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* LLM Investigation Report */}
          {llmReport ? (
            <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-6 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-indigo-900">
                <ShieldAlert className="h-5 w-5" />
                AI Investigation Report
              </h2>
              <p className="mt-3 text-sm text-indigo-800">{llmReport.summary}</p>

              {llmReport.typology_match && (
                <div className="mt-3">
                  <span className="inline-flex items-center gap-1 rounded-full border border-indigo-300 bg-indigo-100 px-3 py-1 text-xs font-medium text-indigo-800">
                    Typology: {llmReport.typology_match}
                  </span>
                </div>
              )}

              {llmReport.risk_factors.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
                    Risk Factors
                  </p>
                  <ul className="mt-2 space-y-1">
                    {llmReport.risk_factors.map((factor, i) => (
                      <li
                        // biome-ignore lint/suspicious/noArrayIndexKey: static list
                        key={i}
                        className="flex items-start gap-2 text-sm text-indigo-800"
                      >
                        <span className="mt-0.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />
                        {factor}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {llmReport.sar_recommendation && (
                <div className="mt-4 rounded-lg border border-indigo-200 bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
                    SAR Recommendation
                  </p>
                  <p className="mt-1 text-sm text-gray-800">
                    {llmReport.sar_recommendation}
                  </p>
                </div>
              )}

              {llmReport.confidence && (
                <p className="mt-3 text-xs text-indigo-500">
                  Confidence: {llmReport.confidence}
                </p>
              )}
            </div>
          ) : (
            (alert.status === "pending" || alert.status === "under_review") && (
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-6 text-center shadow-sm">
                <p className="text-sm text-gray-400 italic">
                  Awaiting AI investigation report…
                </p>
              </div>
            )
          )}

          {/* Sanctions Screening */}
          {screening && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">
                Sanctions Screening
              </h2>
              <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-gray-500">Screened Name</dt>
                  <dd className="font-medium text-gray-900">
                    {screening.screened_name}
                  </dd>
                </div>
                <div>
                  <dt className="text-gray-500">Status</dt>
                  <dd>
                    <StatusBadge
                      status={formatStatusLabel(screening.status)}
                      colorClass={screeningStatusColor(screening.status)}
                    />
                  </dd>
                </div>
                {screening.matched_name && (
                  <div>
                    <dt className="text-gray-500">Matched Name</dt>
                    <dd className="font-medium text-red-700">
                      {screening.matched_name}
                    </dd>
                  </div>
                )}
                {screening.match_score != null && (
                  <div>
                    <dt className="text-gray-500">Match Score</dt>
                    <dd className="font-medium text-gray-900">
                      {Math.round(screening.match_score * 100)}%
                    </dd>
                  </div>
                )}
                {screening.source && (
                  <div>
                    <dt className="text-gray-500">Source List</dt>
                    <dd className="text-gray-900">{screening.source}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}

          {/* Review Form */}
          {canReview && showReviewForm && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-gray-900">
                Submit Review
              </h2>
              <div className="mt-4 space-y-4">
                <div className="flex gap-3">
                  {(
                    [
                      {
                        value: "confirmed_fraud",
                        label: "Confirmed Fraud",
                        icon: XCircle,
                        color: "border-red-300 bg-red-50 text-red-700",
                        selected: "ring-2 ring-red-500",
                      },
                      {
                        value: "legitimate",
                        label: "Legitimate",
                        icon: CheckCircle,
                        color: "border-green-300 bg-green-50 text-green-700",
                        selected: "ring-2 ring-green-500",
                      },
                      {
                        value: "suspicious",
                        label: "Suspicious",
                        icon: Shield,
                        color:
                          "border-purple-300 bg-purple-50 text-purple-700",
                        selected: "ring-2 ring-purple-500",
                      },
                    ] as const
                  ).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setDecision(option.value)}
                      className={`flex flex-1 flex-col items-center gap-2 rounded-lg border p-4 transition-all ${option.color} ${
                        decision === option.value ? option.selected : ""
                      }`}
                    >
                      <option.icon className="h-6 w-6" />
                      <span className="text-sm font-medium">
                        {option.label}
                      </span>
                    </button>
                  ))}
                </div>

                <textarea
                  placeholder="Notes (optional) — explain your reasoning"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={handleSubmitReview}
                    disabled={!decision || submitReview.isPending}
                    className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submitReview.isPending
                      ? "Submitting..."
                      : "Submit Review"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowReviewForm(false)}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Risk Summary */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900">
              Risk Summary
            </h3>
            <div className="mt-4 space-y-3">
              <div>
                <p className="text-xs text-gray-500">Overall Risk Score</p>
                <RiskScoreBar score={alert.risk_score} />
              </div>
              <div>
                <p className="text-xs text-gray-500">Detection Source</p>
                <p className="text-sm font-medium capitalize text-gray-900">
                  {alert.source.replace("_", " ")}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Created</p>
                <p className="text-sm text-gray-900">
                  {formatDate(alert.created_at)}
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          {canReview && !showReviewForm && (
            <button
              type="button"
              onClick={() => setShowReviewForm(true)}
              className="w-full rounded-lg bg-primary-600 px-4 py-3 text-sm font-medium text-white hover:bg-primary-700"
            >
              Review This Alert
            </button>
          )}

          {!canReview && (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-center">
              <p className="text-sm text-gray-500">
                This alert has been{" "}
                <span className="font-medium">
                  {formatStatusLabel(alert.status).toLowerCase()}
                </span>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
