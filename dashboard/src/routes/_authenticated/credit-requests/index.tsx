import { creditRequestListOptions, queryKeys } from "@/api/queries";
import { api } from "@/api/client";
import type { CreditRequestStatus, CreditReviewActionBody } from "@/api/types";
import { EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import {
  creditRecommendationColor,
  creditRequestStatusColor,
  creditSegmentColor,
  creditSegmentLabel,
  formatCurrency,
  formatRelativeDate,
  formatStatusLabel,
} from "@/lib/utils";
import { useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useSearch } from "@tanstack/react-router";
import { ClipboardCheck } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

const searchSchema = z.object({
  page: z.coerce.number().optional().default(1),
  status: z
    .enum(["pending_review", "approved", "rejected", "expired"])
    .optional(),
});

export const Route = createFileRoute("/_authenticated/credit-requests/")({
  validateSearch: searchSchema,
  loader: ({ context, deps }) => {
    const search = deps as z.infer<typeof searchSchema>;
    return context.queryClient.ensureQueryData(
      creditRequestListOptions(search.page, search.status),
    );
  },
  component: CreditRequestsPage,
});

const STATUS_FILTERS: Array<{
  label: string;
  value: CreditRequestStatus | undefined;
}> = [
  { label: "All", value: undefined },
  { label: "Pending Review", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
];

function CreditRequestsPage() {
  const search = useSearch({ from: "/_authenticated/credit-requests/" });
  const { data } = useSuspenseQuery(
    creditRequestListOptions(search.page, search.status),
  );
  const queryClient = useQueryClient();
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  const reviewMutation = useMutation({
    mutationFn: ({
      requestId,
      body,
    }: {
      requestId: string;
      body: CreditReviewActionBody;
    }) => api.put(`/credit/requests/${requestId}/review`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.credit.all });
      setReviewingId(null);
      setNotes("");
    },
  });

  const totalPages = Math.ceil(data.total / data.page_size);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Credit Requests</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review and approve or reject credit applications
        </p>
      </div>

      {/* Status Filter Tabs */}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {STATUS_FILTERS.map((filter) => (
          <Link
            key={filter.label}
            to="/credit-requests"
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

      {/* Request List */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.length === 0 ? (
          <EmptyState
            icon={ClipboardCheck}
            title="No credit requests"
            description="Credit requests will appear when customers apply for loans."
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Client
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Amount
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Segment
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Recommendation
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {data.items.map((req) => (
                <tr key={req.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">
                      {req.fineract_client_id}
                    </span>
                    <p className="mt-0.5 text-xs text-gray-500">
                      Max: {formatCurrency(req.max_credit_at_request, "XAF")}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {formatCurrency(req.requested_amount, "XAF")}
                  </td>
                  <td className="px-4 py-3">
                    <RiskScoreBar score={req.credit_score_at_request} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={creditSegmentLabel(req.segment_at_request)}
                      colorClass={creditSegmentColor(req.segment_at_request)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={formatStatusLabel(req.recommendation)}
                      colorClass={creditRecommendationColor(req.recommendation)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={formatStatusLabel(req.status)}
                      colorClass={creditRequestStatusColor(req.status)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    {req.status === "pending_review" ? (
                      reviewingId === req.id ? (
                        <div className="flex flex-col gap-2">
                          <input
                            type="text"
                            placeholder="Notes (optional)"
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            className="rounded border border-gray-300 px-2 py-1 text-xs"
                          />
                          <div className="flex gap-1">
                            <button
                              type="button"
                              onClick={() =>
                                reviewMutation.mutate({
                                  requestId: req.id,
                                  body: {
                                    status: "approved",
                                    reviewer_notes: notes || undefined,
                                  },
                                })
                              }
                              disabled={reviewMutation.isPending}
                              className="rounded bg-green-600 px-2 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                reviewMutation.mutate({
                                  requestId: req.id,
                                  body: {
                                    status: "rejected",
                                    reviewer_notes: notes || undefined,
                                  },
                                })
                              }
                              disabled={reviewMutation.isPending}
                              className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                            >
                              Reject
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setReviewingId(null);
                                setNotes("");
                              }}
                              className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setReviewingId(req.id)}
                          className="rounded border border-primary-300 px-3 py-1 text-xs font-medium text-primary-700 hover:bg-primary-50"
                        >
                          Review
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-gray-400">
                        {req.reviewed_at
                          ? formatRelativeDate(req.reviewed_at)
                          : "—"}
                      </span>
                    )}
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
            window.location.href = `/credit-requests?page=${newPage}${search.status ? `&status=${search.status}` : ""}`;
          }}
        />
      </div>
    </div>
  );
}
