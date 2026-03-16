import { alertListOptions } from "@/api/queries";
import type { AlertStatus } from "@/api/types";
import { EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import { alertStatusColor, formatCurrency, formatRelativeDate } from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useSearch } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import { z } from "zod";

const searchSchema = z.object({
  page: z.coerce.number().optional().default(1),
  status: z
    .enum([
      "pending",
      "under_review",
      "confirmed_fraud",
      "false_positive",
      "escalated",
      "dismissed",
    ])
    .optional(),
});

export const Route = createFileRoute("/_authenticated/alerts/")({
  validateSearch: searchSchema,
  loader: ({ context, deps }) => {
    const search = deps as z.infer<typeof searchSchema>;
    return context.queryClient.ensureQueryData(
      alertListOptions(search.page, search.status),
    );
  },
  component: AlertsPage,
});

const STATUS_FILTERS: Array<{ label: string; value: AlertStatus | undefined }> = [
  { label: "All", value: undefined },
  { label: "Pending", value: "pending" },
  { label: "Under Review", value: "under_review" },
  { label: "Confirmed Fraud", value: "confirmed_fraud" },
  { label: "False Positive", value: "false_positive" },
  { label: "Escalated", value: "escalated" },
];

function AlertsPage() {
  const search = useSearch({ from: "/_authenticated/alerts/" });
  const { data } = useSuspenseQuery(
    alertListOptions(search.page, search.status),
  );

  const totalPages = Math.ceil(data.total / data.page_size);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review flagged transactions and submit decisions
        </p>
      </div>

      {/* Status Filter Tabs */}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {STATUS_FILTERS.map((filter) => (
          <Link
            key={filter.label}
            to="/alerts"
            search={{ page: 1, status: filter.value }}
            className={`rounded-full border px-4 py-1.5 text-sm font-medium whitespace-nowrap transition-colors ${
              search.status === filter.value
                ? "border-primary-300 bg-primary-50 text-primary-700"
                : "border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {filter.label}
          </Link>
        ))}
      </div>

      {/* Alert List */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.length === 0 ? (
          <EmptyState
            icon={AlertTriangle}
            title="No alerts found"
            description="No alerts match the current filter."
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Alert
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Risk Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Source
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {data.items.map((alert) => (
                <tr key={alert.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to="/alerts/$alertId"
                      params={{ alertId: alert.id }}
                      className="font-medium text-primary-600 hover:text-primary-800"
                    >
                      {alert.title}
                    </Link>
                    {alert.transaction && (
                      <p className="mt-0.5 text-xs text-gray-500">
                        Account: {alert.transaction.fineract_account_id}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {alert.transaction
                      ? formatCurrency(
                          alert.transaction.amount,
                          alert.transaction.currency,
                        )
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <RiskScoreBar score={alert.risk_score} />
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-600">
                    {alert.source.replace("_", " ")}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={alert.status}
                      colorClass={alertStatusColor(alert.status)}
                    />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatRelativeDate(alert.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <Pagination
          page={data.page}
          totalPages={totalPages}
          onPageChange={(newPage) => {
            // Navigation handled by Link, but we provide the handler for the Pagination component
            window.location.href = `/alerts?page=${newPage}${search.status ? `&status=${search.status}` : ""}`;
          }}
        />
      </div>
    </div>
  );
}
