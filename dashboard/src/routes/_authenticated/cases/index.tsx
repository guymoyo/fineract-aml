import { caseListOptions } from "@/api/queries";
import { useCreateCase } from "@/api/mutations";
import type { CaseStatus } from "@/api/types";
import { EmptyState } from "@/components/empty-state";
import { Pagination } from "@/components/pagination";
import { StatusBadge } from "@/components/status-badge";
import { caseStatusColor, formatDate } from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute, useSearch } from "@tanstack/react-router";
import { FolderOpen, Plus } from "lucide-react";
import { useState } from "react";
import { z } from "zod";

const searchSchema = z.object({
  page: z.coerce.number().optional().default(1),
  status: z
    .enum([
      "open",
      "investigating",
      "escalated",
      "closed_legitimate",
      "closed_fraud",
      "sar_filed",
    ])
    .optional(),
});

export const Route = createFileRoute("/_authenticated/cases/")({
  validateSearch: searchSchema,
  loader: ({ context, deps }) => {
    const search = deps as z.infer<typeof searchSchema>;
    return context.queryClient.ensureQueryData(
      caseListOptions(search.page, search.status),
    );
  },
  component: CasesPage,
});

const STATUS_FILTERS: Array<{ label: string; value: CaseStatus | undefined }> = [
  { label: "All", value: undefined },
  { label: "Open", value: "open" },
  { label: "Investigating", value: "investigating" },
  { label: "Escalated", value: "escalated" },
  { label: "Closed (Fraud)", value: "closed_fraud" },
  { label: "SAR Filed", value: "sar_filed" },
];

function CasesPage() {
  const search = useSearch({ from: "/_authenticated/cases/" });
  const { data } = useSuspenseQuery(
    caseListOptions(search.page, search.status),
  );
  const createCase = useCreateCase();

  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const totalPages = Math.ceil(data.total / data.page_size);

  const handleCreate = () => {
    if (!newTitle.trim()) return;
    createCase.mutate(
      { title: newTitle, description: newDescription || undefined },
      {
        onSuccess: () => {
          setShowCreate(false);
          setNewTitle("");
          setNewDescription("");
        },
      },
    );
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cases</h1>
          <p className="mt-1 text-sm text-gray-500">
            Investigation cases for related suspicious activity
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          <Plus className="h-4 w-4" />
          New Case
        </button>
      </div>

      {/* Create Case Modal */}
      {showCreate && (
        <div className="mb-6 rounded-xl border border-primary-200 bg-primary-50 p-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Create New Case
          </h2>
          <div className="mt-4 space-y-3">
            <input
              type="text"
              placeholder="Case title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
            <textarea
              placeholder="Description (optional)"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
            <div className="flex gap-3">
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newTitle.trim() || createCase.isPending}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {createCase.isPending ? "Creating..." : "Create Case"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status Filter */}
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {STATUS_FILTERS.map((filter) => (
          <Link
            key={filter.label}
            to="/cases"
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

      {/* Cases Table */}
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {data.items.length === 0 ? (
          <EmptyState
            icon={FolderOpen}
            title="No cases found"
            description="Create a case to group related suspicious transactions."
          />
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Case
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Client
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Updated
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {data.items.map((c) => (
                <tr key={c.id} className="cursor-pointer hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to="/cases/$caseId"
                      params={{ caseId: c.id }}
                      className="block"
                    >
                      <p className="text-sm font-medium text-gray-900">
                        {c.case_number}
                      </p>
                      <p className="text-xs text-gray-500">{c.title}</p>
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-600">
                    {c.fineract_client_id || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={c.status}
                      colorClass={caseStatusColor(c.status)}
                    />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatDate(c.created_at)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatDate(c.updated_at)}
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
            window.location.href = `/cases?page=${newPage}${search.status ? `&status=${search.status}` : ""}`;
          }}
        />
      </div>
    </div>
  );
}
