import { caseDetailOptions } from "@/api/queries";
import { useUpdateCaseStatus } from "@/api/mutations";
import type { CaseStatus } from "@/api/types";
import { StatusBadge } from "@/components/status-badge";
import { caseStatusColor, formatDate, formatStatusLabel } from "@/lib/utils";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/_authenticated/cases/$caseId")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(caseDetailOptions(params.caseId)),
  component: CaseDetailPage,
});

const STATUS_OPTIONS: CaseStatus[] = [
  "open",
  "investigating",
  "escalated",
  "closed_legitimate",
  "closed_fraud",
  "sar_filed",
];

function CaseDetailPage() {
  const { caseId } = Route.useParams();
  const { data: c } = useSuspenseQuery(caseDetailOptions(caseId));
  const updateStatus = useUpdateCaseStatus(caseId);

  const [selectedStatus, setSelectedStatus] = useState<CaseStatus>(c.status);

  const handleStatusUpdate = () => {
    if (selectedStatus === c.status) return;
    updateStatus.mutate(selectedStatus);
  };

  return (
    <div>
      <div className="mb-6">
        <Link
          to="/cases"
          className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Cases
        </Link>
        <div className="mt-2 flex items-start justify-between">
          <div>
            <p className="text-sm font-mono text-gray-500">{c.case_number}</p>
            <h1 className="text-2xl font-bold text-gray-900">{c.title}</h1>
          </div>
          <StatusBadge status={c.status} colorClass={caseStatusColor(c.status)} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="space-y-6 lg:col-span-2">
          {/* Description */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Description</h2>
            <p className="mt-3 text-sm text-gray-700">
              {c.description || (
                <span className="text-gray-400 italic">No description provided.</span>
              )}
            </p>
          </div>

          {/* Status Update */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">Update Status</h2>
            <div className="mt-4 flex items-center gap-3">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as CaseStatus)}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {formatStatusLabel(s)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleStatusUpdate}
                disabled={selectedStatus === c.status || updateStatus.isPending}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {updateStatus.isPending ? "Saving..." : "Save"}
              </button>
            </div>
            {updateStatus.isSuccess && (
              <p className="mt-2 text-sm text-green-600">Status updated.</p>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900">Case Details</h3>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="text-gray-500">Client ID</dt>
                <dd className="font-mono text-gray-900">
                  {c.fineract_client_id || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Assigned To</dt>
                <dd className="text-gray-900">{c.assigned_to || "Unassigned"}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Created</dt>
                <dd className="text-gray-900">{formatDate(c.created_at)}</dd>
              </div>
              <div>
                <dt className="text-gray-500">Last Updated</dt>
                <dd className="text-gray-900">{formatDate(c.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
