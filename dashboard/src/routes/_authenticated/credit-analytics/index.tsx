import { creditAnalyticsOptions } from "@/api/queries";
import { StatCard } from "@/components/stat-card";
import { StatusBadge } from "@/components/status-badge";
import {
  creditSegmentColor,
  creditSegmentLabel,
  formatCurrency,
  formatPercent,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  CheckCircle,
  Clock,
  CreditCard,
  TrendingUp,
} from "lucide-react";

export const Route = createFileRoute("/_authenticated/credit-analytics/")({
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(creditAnalyticsOptions()),
  component: CreditAnalyticsPage,
});

function CreditAnalyticsPage() {
  const { data } = useSuspenseQuery(creditAnalyticsOptions());

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Credit Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">
          Overview of customer credit scoring and segmentation
        </p>
      </div>

      {/* Summary Stats */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Profiles"
          value={data.total_profiles}
          icon={CreditCard}
        />
        <StatCard
          title="Avg Credit Score"
          value={formatPercent(data.avg_credit_score)}
          icon={TrendingUp}
        />
        <StatCard
          title="Pending Reviews"
          value={data.total_pending_requests}
          icon={Clock}
          trend={data.total_pending_requests > 0 ? "up" : "neutral"}
        />
        <StatCard
          title="Approved / Rejected"
          value={`${data.total_approved} / ${data.total_rejected}`}
          icon={CheckCircle}
        />
      </div>

      {/* Segment Distribution */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">
          Segment Distribution
        </h2>

        {data.segment_distribution.length === 0 ? (
          <p className="text-sm text-gray-500">
            No credit profiles computed yet. Run the nightly scoring task to
            populate segments.
          </p>
        ) : (
          <div className="space-y-4">
            {data.segment_distribution.map((seg) => {
              const percentage =
                data.total_profiles > 0
                  ? (seg.count / data.total_profiles) * 100
                  : 0;

              return (
                <div key={seg.segment} className="flex items-center gap-4">
                  <div className="w-36">
                    <StatusBadge
                      status={creditSegmentLabel(seg.segment)}
                      colorClass={creditSegmentColor(seg.segment)}
                    />
                  </div>

                  {/* Bar */}
                  <div className="flex-1">
                    <div className="h-6 w-full overflow-hidden rounded-full bg-gray-100">
                      <div
                        className="h-full rounded-full bg-primary-500 transition-all"
                        style={{ width: `${Math.max(percentage, 1)}%` }}
                      />
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="flex w-64 gap-4 text-sm text-gray-600">
                    <span className="w-16 text-right font-medium">
                      {seg.count}
                    </span>
                    <span className="w-16 text-right">
                      {percentage.toFixed(1)}%
                    </span>
                    <span className="w-16 text-right">
                      {formatPercent(seg.avg_score)}
                    </span>
                    <span className="w-24 text-right">
                      {formatCurrency(seg.avg_max_amount, "XAF")}
                    </span>
                  </div>
                </div>
              );
            })}

            {/* Column headers */}
            <div className="flex items-center gap-4 border-t border-gray-100 pt-2 text-xs text-gray-400">
              <div className="w-36" />
              <div className="flex-1" />
              <div className="flex w-64 gap-4">
                <span className="w-16 text-right">Count</span>
                <span className="w-16 text-right">Share</span>
                <span className="w-16 text-right">Avg Score</span>
                <span className="w-24 text-right">Avg Max</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
