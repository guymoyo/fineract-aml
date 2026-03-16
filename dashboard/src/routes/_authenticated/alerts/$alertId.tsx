import { alertDetailOptions } from "@/api/queries";
import { useSubmitReview } from "@/api/mutations";
import type { ReviewDecision } from "@/api/types";
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
  XCircle,
} from "lucide-react";
import { useState } from "react";

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
