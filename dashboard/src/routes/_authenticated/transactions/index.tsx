import { transactionListOptions } from "@/api/queries";
import type { RiskLevel } from "@/api/types";
import { EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import {
  formatCurrency,
  formatDate,
  riskLevelColor,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useSearch } from "@tanstack/react-router";
import { BarChart3 } from "lucide-react";
import { z } from "zod";

const searchSchema = z.object({
  page: z.coerce.number().optional().default(1),
  risk_level: z.enum(["low", "medium", "high", "critical"]).optional(),
});

export const Route = createFileRoute("/_authenticated/transactions/")({
  validateSearch: searchSchema,
  loader: ({ context, deps }) => {
    const search = deps as z.infer<typeof searchSchema>;
    return context.queryClient.ensureQueryData(
      transactionListOptions(search.page, search.risk_level),
    );
  },
  component: TransactionsPage,
});

const RISK_FILTERS: Array<{ label: string; value: RiskLevel | undefined }> = [
  { label: "All", value: undefined },
  { label: "Low", value: "low" },
  { label: "Medium", value: "medium" },
  { label: "High", value: "high" },
  { label: "Critical", value: "critical" },
];

function TransactionsPage() {
  const search = useSearch({ from: "/_authenticated/transactions/" });
  const { data } = useSuspenseQuery(
    transactionListOptions(search.page, search.risk_level),
  );

  const totalPages = Math.ceil(data.total / data.page_size);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Transactions</h1>
        <p className="mt-1 text-sm text-gray-500">
          All transactions received from Fineract
        </p>
      </div>

      {/* Risk Level Filter */}
      <div className="mb-4 flex gap-2">
        {RISK_FILTERS.map((filter) => (
          <Link
            key={filter.label}
            to="/transactions"
            search={{ page: 1, risk_level: filter.value }}
            className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${
              search.risk_level === filter.value
                ? "border-primary-300 bg-primary-50 text-primary-700"
                : "border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {filter.label}
          </Link>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No transactions found"
            description="No transactions match the current filter."
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Transaction
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Risk Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Risk Level
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Date
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {data.items.map((tx) => (
                <tr key={tx.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <p className="text-sm font-medium text-gray-900">
                      {tx.fineract_transaction_id}
                    </p>
                    <p className="text-xs text-gray-500">
                      {tx.fineract_account_id}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-600">
                    {tx.transaction_type}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {formatCurrency(tx.amount, tx.currency)}
                  </td>
                  <td className="px-4 py-3">
                    <RiskScoreBar score={tx.risk_score} />
                  </td>
                  <td className="px-4 py-3">
                    {tx.risk_level ? (
                      <StatusBadge
                        status={tx.risk_level}
                        colorClass={riskLevelColor(tx.risk_level)}
                      />
                    ) : (
                      <span className="text-xs text-gray-400">Pending</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatDate(tx.transaction_date)}
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
            window.location.href = `/transactions?page=${newPage}${search.risk_level ? `&risk_level=${search.risk_level}` : ""}`;
          }}
        />
      </div>
    </div>
  );
}
