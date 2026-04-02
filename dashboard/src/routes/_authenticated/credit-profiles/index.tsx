import { creditProfileListOptions } from "@/api/queries";
import type { CreditSegment } from "@/api/types";
import { EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { RiskScoreBar } from "@/components/risk-score-bar";
import { StatusBadge } from "@/components/status-badge";
import {
  creditSegmentColor,
  creditSegmentLabel,
  formatCurrency,
  formatRelativeDate,
} from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useSearch } from "@tanstack/react-router";
import { CreditCard } from "lucide-react";
import { z } from "zod";

const searchSchema = z.object({
  page: z.coerce.number().optional().default(1),
  segment: z
    .enum(["tier_a", "tier_b", "tier_c", "tier_d", "tier_e"])
    .optional(),
});

export const Route = createFileRoute("/_authenticated/credit-profiles/")({
  validateSearch: searchSchema,
  loader: ({ context, deps }) => {
    const search = deps as z.infer<typeof searchSchema>;
    return context.queryClient.ensureQueryData(
      creditProfileListOptions(search.page, search.segment),
    );
  },
  component: CreditProfilesPage,
});

const SEGMENT_FILTERS: Array<{
  label: string;
  value: CreditSegment | undefined;
}> = [
  { label: "All", value: undefined },
  { label: "Tier A", value: "tier_a" },
  { label: "Tier B", value: "tier_b" },
  { label: "Tier C", value: "tier_c" },
  { label: "Tier D", value: "tier_d" },
  { label: "Tier E", value: "tier_e" },
];

function CreditProfilesPage() {
  const search = useSearch({ from: "/_authenticated/credit-profiles/" });
  const { data } = useSuspenseQuery(
    creditProfileListOptions(search.page, search.segment),
  );

  const totalPages = Math.ceil(data.total / data.page_size);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Credit Profiles</h1>
        <p className="mt-1 text-sm text-gray-500">
          Customer credit scores and segment classifications
        </p>
      </div>

      {/* Segment Filter Tabs */}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {SEGMENT_FILTERS.map((filter) => (
          <Link
            key={filter.label}
            to="/credit-profiles"
            search={{ page: 1, segment: filter.value }}
            className={`rounded-full border px-4 py-1.5 text-sm font-medium whitespace-nowrap transition-colors ${
              search.segment === filter.value
                ? "border-primary-300 bg-primary-50 text-primary-700"
                : "border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {filter.label}
          </Link>
        ))}
      </div>

      {/* Profile List */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.length === 0 ? (
          <EmptyState
            icon={CreditCard}
            title="No credit profiles found"
            description="Credit profiles will appear after the nightly scoring task runs."
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Client ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Credit Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Segment
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Max Credit
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Method
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Last Scored
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {data.items.map((profile) => (
                <tr key={profile.id} className="cursor-pointer hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to="/credit-profiles/$clientId"
                      params={{ clientId: profile.fineract_client_id }}
                      className="font-medium text-gray-900 hover:text-primary-600"
                    >
                      {profile.fineract_client_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <RiskScoreBar score={profile.credit_score} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={creditSegmentLabel(profile.segment)}
                      colorClass={creditSegmentColor(profile.segment)}
                    />
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">
                    {formatCurrency(profile.max_credit_amount, "XAF")}
                  </td>
                  <td className="px-4 py-3 text-sm capitalize text-gray-600">
                    {profile.scoring_method.replace("_", " ")}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatRelativeDate(profile.last_computed_at)}
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
            window.location.href = `/credit-profiles?page=${newPage}${search.segment ? `&segment=${search.segment}` : ""}`;
          }}
        />
      </div>
    </div>
  );
}
