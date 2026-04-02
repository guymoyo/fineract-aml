import { transactionDetailOptions } from "@/api/queries";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import {
  formatCurrency,
  formatDate,
  formatPercent,
  formatStatusLabel,
  riskLevelColor,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

export const Route = createFileRoute("/_authenticated/transactions/$txId")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(transactionDetailOptions(params.txId)),
  component: TransactionDetailPage,
});

function TransactionDetailPage() {
  const { txId } = Route.useParams();
  const { data: tx } = useSuspenseQuery(transactionDetailOptions(txId));

  return (
    <div>
      <div className="mb-6">
        <Link
          to="/transactions"
          className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Transactions
        </Link>
        <div className="mt-2 flex items-start justify-between">
          <div>
            <p className="text-sm font-mono text-gray-500">
              {tx.fineract_transaction_id}
            </p>
            <h1 className="text-2xl font-bold capitalize text-gray-900">
              {tx.transaction_type.replace(/_/g, " ")}
            </h1>
          </div>
          {tx.risk_level ? (
            <StatusBadge
              status={tx.risk_level}
              colorClass={riskLevelColor(tx.risk_level)}
            />
          ) : (
            <span className="text-sm text-gray-400">Not scored</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="space-y-6 lg:col-span-2">
          {/* Transaction fields */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              Transaction Details
            </h2>
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
              <div>
                <dt className="text-gray-500">Amount</dt>
                <dd className="text-lg font-semibold text-gray-900">
                  {formatCurrency(tx.amount, tx.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Currency</dt>
                <dd className="font-medium text-gray-900">{tx.currency}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Transaction ID</dt>
                <dd className="font-mono text-gray-900">
                  {tx.fineract_transaction_id}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Account ID</dt>
                <dd className="font-mono text-gray-900">
                  {tx.fineract_account_id}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Client ID</dt>
                <dd className="font-mono text-gray-900">
                  {tx.fineract_client_id}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Date</dt>
                <dd className="text-gray-900">
                  {formatDate(tx.transaction_date)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">IP Address</dt>
                <dd className="font-mono text-gray-900">
                  {tx.ip_address || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Country</dt>
                <dd className="text-gray-900">{tx.country_code || "—"}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Created At</dt>
                <dd className="text-gray-900">{formatDate(tx.created_at)}</dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Risk Scores */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900">Risk Scores</h3>
            <div className="mt-4 space-y-4">
              <div>
                <p className="mb-1 text-xs text-gray-500">
                  Risk Score{" "}
                  {tx.risk_score != null && (
                    <span className="font-medium text-gray-700">
                      ({formatPercent(tx.risk_score)})
                    </span>
                  )}
                </p>
                <RiskScoreBar score={tx.risk_score} />
              </div>
              <div>
                <p className="mb-1 text-xs text-gray-500">
                  Anomaly Score{" "}
                  {tx.anomaly_score != null && (
                    <span className="font-medium text-gray-700">
                      ({formatPercent(tx.anomaly_score)})
                    </span>
                  )}
                </p>
                <RiskScoreBar score={tx.anomaly_score} />
              </div>
              {tx.risk_level && (
                <div>
                  <p className="mb-1 text-xs text-gray-500">Risk Level</p>
                  <StatusBadge
                    status={formatStatusLabel(tx.risk_level)}
                    colorClass={riskLevelColor(tx.risk_level)}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Location */}
          {(tx.country_code || tx.ip_address) && (
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-900">
                Location Context
              </h3>
              <dl className="mt-4 space-y-3 text-sm">
                {tx.country_code && (
                  <div>
                    <dt className="text-gray-500">Country</dt>
                    <dd className="font-medium text-gray-900">
                      {tx.country_code}
                    </dd>
                  </div>
                )}
                {tx.ip_address && (
                  <div>
                    <dt className="text-gray-500">IP Address</dt>
                    <dd className="font-mono text-gray-900">{tx.ip_address}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
