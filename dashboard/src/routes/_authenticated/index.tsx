import { transactionStatsOptions, creditAnalyticsOptions } from "@/api/queries";
import { StatCard } from "@/components/stat-card";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { creditSegmentLabel, formatCurrency } from "@/lib/utils";
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
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

export const Route = createFileRoute("/_authenticated/")({
  loader: ({ context }) =>
    Promise.all([
      context.queryClient.ensureQueryData(transactionStatsOptions()),
      context.queryClient.ensureQueryData(creditAnalyticsOptions()),
    ]),
  component: DashboardPage,
});

const SEGMENT_COLORS: Record<string, string> = {
  tier_a: "#22c55e",
  tier_b: "#3b82f6",
  tier_c: "#f59e0b",
  tier_d: "#f97316",
  tier_e: "#ef4444",
};

function DashboardPage() {
  const { data: stats } = useSuspenseQuery(transactionStatsOptions());
  const { data: creditAnalytics } = useSuspenseQuery(creditAnalyticsOptions());

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

      {/* Credit Segment Distribution */}
      {creditAnalytics.segment_distribution.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              Credit Segment Distribution
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              {creditAnalytics.total_profiles.toLocaleString()} profiles · avg
              score {Math.round(creditAnalytics.avg_credit_score * 100)}%
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={creditAnalytics.segment_distribution.map((s) => ({
                    name: creditSegmentLabel(s.segment),
                    value: s.count,
                    segment: s.segment,
                  }))}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {creditAnalytics.segment_distribution.map((s) => (
                    <Cell
                      key={s.segment}
                      fill={SEGMENT_COLORS[s.segment] ?? "#9ca3af"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [
                    value.toLocaleString(),
                    name,
                  ]}
                />
                <Legend
                  iconType="circle"
                  iconSize={10}
                  wrapperStyle={{ fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              Credit Requests
            </h2>
            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Pending Review</span>
                <span className="font-semibold text-amber-700">
                  {creditAnalytics.total_pending_requests}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Approved</span>
                <span className="font-semibold text-green-700">
                  {creditAnalytics.total_approved}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-500">Rejected</span>
                <span className="font-semibold text-red-700">
                  {creditAnalytics.total_rejected}
                </span>
              </div>
              <div className="mt-4 border-t border-gray-100 pt-4">
                <p className="text-xs text-gray-400">Approval rate</p>
                {creditAnalytics.total_approved + creditAnalytics.total_rejected > 0 ? (
                  <p className="text-2xl font-bold text-gray-900">
                    {Math.round(
                      (creditAnalytics.total_approved /
                        (creditAnalytics.total_approved +
                          creditAnalytics.total_rejected)) *
                        100,
                    )}
                    %
                  </p>
                ) : (
                  <p className="text-2xl font-bold text-gray-400">—</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
