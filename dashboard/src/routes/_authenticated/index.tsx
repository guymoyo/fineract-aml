import { transactionStatsOptions } from "@/api/queries";
import { StatCard } from "@/components/stat-card";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle,
  Clock,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";

export const Route = createFileRoute("/_authenticated/")({
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(transactionStatsOptions()),
  component: DashboardPage,
});

function DashboardPage() {
  const { data: stats } = useSuspenseQuery(transactionStatsOptions());

  const falsePositiveRate =
    stats.total_false_positives + stats.total_confirmed_fraud > 0
      ? stats.total_false_positives /
        (stats.total_false_positives + stats.total_confirmed_fraud)
      : 0;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          AML monitoring overview and key metrics
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Transactions Today"
          value={stats.transactions_today.toLocaleString()}
          icon={Activity}
        />
        <StatCard
          title="Pending Alerts"
          value={stats.alerts_pending}
          icon={Clock}
          className={
            stats.alerts_pending > 10 ? "border-amber-300 bg-amber-50" : ""
          }
        />
        <StatCard
          title="Confirmed Fraud"
          value={stats.total_confirmed_fraud}
          icon={ShieldAlert}
        />
        <StatCard
          title="False Positives"
          value={stats.total_false_positives}
          icon={CheckCircle}
        />
      </div>

      {/* Second Row */}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          title="Total Transactions"
          value={stats.total_transactions.toLocaleString()}
          icon={TrendingUp}
        />
        <StatCard
          title="Total Flagged"
          value={stats.total_flagged.toLocaleString()}
          subtitle={`${((stats.total_flagged / Math.max(stats.total_transactions, 1)) * 100).toFixed(2)}% flag rate`}
          icon={AlertTriangle}
        />
        <StatCard
          title="False Positive Rate"
          value={`${(falsePositiveRate * 100).toFixed(1)}%`}
          subtitle={falsePositiveRate > 0.7 ? "Consider tuning" : "Healthy"}
          trend={falsePositiveRate > 0.7 ? "up" : "neutral"}
          icon={Ban}
        />
      </div>

      {/* Average Risk Score */}
      <div className="mt-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900">
          System Health
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <p className="text-sm font-medium text-gray-500">
              Average Risk Score
            </p>
            <div className="mt-2">
              <RiskScoreBar score={stats.average_risk_score} />
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">
              Detection Sources
            </p>
            <div className="mt-2 space-y-1 text-sm text-gray-600">
              <p>Rule Engine: Active</p>
              <p>Anomaly Detection: Active</p>
              <p>
                ML Classifier:{" "}
                {stats.total_confirmed_fraud >= 50 ? "Active" : "Collecting labels"}
                {stats.total_confirmed_fraud < 50 && (
                  <span className="text-gray-400">
                    {" "}
                    ({stats.total_confirmed_fraud}/50 fraud labels)
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
