import { creditProfileDetailOptions } from "@/api/queries";
import { useRefreshCreditProfile } from "@/api/mutations";
import { StatusBadge } from "@/components/status-badge";
import {
  creditSegmentColor,
  creditSegmentLabel,
  formatCurrency,
  formatDate,
  formatPercent,
  formatStatusLabel,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, RefreshCw } from "lucide-react";

export const Route = createFileRoute(
  "/_authenticated/credit-profiles/$clientId",
)({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(
      creditProfileDetailOptions(params.clientId),
    ),
  component: CreditProfileDetailPage,
});

interface ScoreComponents {
  deposit_consistency?: number;
  net_flow?: number;
  savings_rate?: number;
  tx_frequency?: number;
  account_age?: number;
  repayment_rate?: number;
  fraud_history?: number;
}

const COMPONENT_LABELS: Record<string, string> = {
  deposit_consistency: "Deposit Consistency",
  net_flow: "Net Flow",
  savings_rate: "Savings Rate",
  tx_frequency: "Transaction Frequency",
  account_age: "Account Age",
  repayment_rate: "Loan Repayment",
  fraud_history: "Fraud History",
};

function ScoreBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70
      ? "bg-green-500"
      : pct >= 45
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-gray-600">{label}</span>
        <span className="font-medium text-gray-900">{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-2 rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function CreditProfileDetailPage() {
  const { clientId } = Route.useParams();
  const { data: profile } = useSuspenseQuery(
    creditProfileDetailOptions(clientId),
  );
  const refresh = useRefreshCreditProfile(clientId);

  let components: ScoreComponents | null = null;
  try {
    if (profile.score_components) {
      components = JSON.parse(profile.score_components) as ScoreComponents;
    }
  } catch {
    // malformed JSON — skip
  }

  return (
    <div>
      <div className="mb-6">
        <Link
          to="/credit-profiles"
          className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Credit Profiles
        </Link>
        <div className="mt-2 flex items-start justify-between">
          <div>
            <p className="text-sm text-gray-500">Client</p>
            <h1 className="font-mono text-2xl font-bold text-gray-900">
              {profile.fineract_client_id}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge
              status={creditSegmentLabel(profile.segment)}
              colorClass={creditSegmentColor(profile.segment)}
            />
            <button
              type="button"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw
                className={`h-4 w-4 ${refresh.isPending ? "animate-spin" : ""}`}
              />
              {refresh.isPending ? "Rescoring..." : "Refresh Score"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="space-y-6 lg:col-span-2">
          {/* Score Breakdown */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              Score Breakdown
            </h2>
            {components ? (
              <div className="mt-4 space-y-4">
                {(Object.keys(COMPONENT_LABELS) as Array<keyof ScoreComponents>).map(
                  (key) => {
                    const val = components![key];
                    if (val == null) return null;
                    return (
                      <ScoreBar
                        key={key}
                        value={val}
                        label={COMPONENT_LABELS[key]}
                      />
                    );
                  },
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-400 italic">
                Score component breakdown not available.
              </p>
            )}
          </div>

          {/* ML Cluster */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">
              ML Cluster Validation
            </h2>
            <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-gray-500">Cluster ID</dt>
                <dd className="font-medium text-gray-900">
                  {profile.ml_cluster_id != null
                    ? `Cluster ${profile.ml_cluster_id}`
                    : "Not clustered yet"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">ML Segment Suggestion</dt>
                <dd>
                  {profile.ml_segment_suggestion ? (
                    <StatusBadge
                      status={creditSegmentLabel(profile.ml_segment_suggestion)}
                      colorClass={creditSegmentColor(
                        profile.ml_segment_suggestion,
                      )}
                    />
                  ) : (
                    <span className="text-gray-400">Not available</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Scoring Method</dt>
                <dd>
                  <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs font-medium capitalize text-gray-700">
                    {formatStatusLabel(profile.scoring_method)}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Agreement</dt>
                <dd className="font-medium text-gray-900">
                  {profile.ml_segment_suggestion
                    ? profile.ml_segment_suggestion === profile.segment
                      ? "✓ Agree"
                      : "⚠ Disagree — review"
                    : "—"}
                </dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Score Summary */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm text-center">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              Credit Score
            </p>
            <p className="mt-2 text-5xl font-bold text-gray-900">
              {formatPercent(profile.credit_score)}
            </p>
            <div className="mt-3">
              <StatusBadge
                status={creditSegmentLabel(profile.segment)}
                colorClass={creditSegmentColor(profile.segment)}
              />
            </div>
            <p className="mt-4 text-sm text-gray-500">Max Credit</p>
            <p className="text-xl font-semibold text-gray-900">
              {formatCurrency(profile.max_credit_amount, "XAF")}
            </p>
          </div>

          {/* Meta */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900">Meta</h3>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="text-gray-500">Last Scored</dt>
                <dd className="text-gray-900">
                  {formatDate(profile.last_computed_at)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Status</dt>
                <dd>
                  <span
                    className={`font-medium ${profile.is_active ? "text-green-600" : "text-gray-400"}`}
                  >
                    {profile.is_active ? "Active" : "Inactive"}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Created</dt>
                <dd className="text-gray-900">
                  {formatDate(profile.created_at)}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
