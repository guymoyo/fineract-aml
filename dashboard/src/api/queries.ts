/** TanStack Query keys and query functions for the AML API. */

import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Alert,
  AlertStatus,
  Case,
  CaseStatus,
  CreditAnalytics,
  CreditProfile,
  CreditRequest,
  CreditRequestStatus,
  CreditSegment,
  PaginatedResponse,
  RiskLevel,
  Transaction,
  TransactionStats,
  User,
} from "./types";

// ── Query Keys ────────────────────────────────────────────

export const queryKeys = {
  transactions: {
    all: ["transactions"] as const,
    list: (page: number, riskLevel?: RiskLevel) =>
      ["transactions", "list", page, riskLevel] as const,
    detail: (id: string) => ["transactions", id] as const,
    stats: ["transactions", "stats"] as const,
  },
  alerts: {
    all: ["alerts"] as const,
    list: (page: number, status?: AlertStatus) =>
      ["alerts", "list", page, status] as const,
    detail: (id: string) => ["alerts", id] as const,
  },
  cases: {
    all: ["cases"] as const,
    list: (page: number, status?: CaseStatus) =>
      ["cases", "list", page, status] as const,
    detail: (id: string) => ["cases", id] as const,
  },
  credit: {
    all: ["credit"] as const,
    profiles: (page: number, segment?: CreditSegment) =>
      ["credit", "profiles", page, segment] as const,
    profile: (clientId: string) => ["credit", "profiles", clientId] as const,
    requests: (page: number, status?: CreditRequestStatus) =>
      ["credit", "requests", page, status] as const,
    request: (id: string) => ["credit", "requests", id] as const,
    analytics: ["credit", "analytics"] as const,
  },
  auth: {
    me: ["auth", "me"] as const,
  },
};

// ── Query Options ─────────────────────────────────────────

export function transactionListOptions(page = 1, riskLevel?: RiskLevel) {
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (riskLevel) params.set("risk_level", riskLevel);

  return queryOptions({
    queryKey: queryKeys.transactions.list(page, riskLevel),
    queryFn: () =>
      api.get<PaginatedResponse<Transaction>>(
        `/transactions?${params.toString()}`,
      ),
  });
}

export function transactionDetailOptions(id: string) {
  return queryOptions({
    queryKey: queryKeys.transactions.detail(id),
    queryFn: () => api.get<Transaction>(`/transactions/${id}`),
  });
}

export function transactionStatsOptions() {
  return queryOptions({
    queryKey: queryKeys.transactions.stats,
    queryFn: () => api.get<TransactionStats>("/transactions/stats"),
    refetchInterval: 30_000,
  });
}

export function alertListOptions(page = 1, status?: AlertStatus) {
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (status) params.set("status", status);

  return queryOptions({
    queryKey: queryKeys.alerts.list(page, status),
    queryFn: () =>
      api.get<PaginatedResponse<Alert>>(`/alerts?${params.toString()}`),
  });
}

export function alertDetailOptions(id: string) {
  return queryOptions({
    queryKey: queryKeys.alerts.detail(id),
    queryFn: () => api.get<Alert>(`/alerts/${id}`),
  });
}

export function caseListOptions(page = 1, status?: CaseStatus) {
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (status) params.set("status", status);

  return queryOptions({
    queryKey: queryKeys.cases.list(page, status),
    queryFn: () =>
      api.get<PaginatedResponse<Case>>(`/cases?${params.toString()}`),
  });
}

export function caseDetailOptions(id: string) {
  return queryOptions({
    queryKey: queryKeys.cases.detail(id),
    queryFn: () => api.get<Case>(`/cases/${id}`),
  });
}

// ── Credit Query Options ──────────────────────────────────

export function creditProfileListOptions(page = 1, segment?: CreditSegment) {
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (segment) params.set("segment", segment);

  return queryOptions({
    queryKey: queryKeys.credit.profiles(page, segment),
    queryFn: () =>
      api.get<PaginatedResponse<CreditProfile>>(
        `/credit/profiles?${params.toString()}`,
      ),
  });
}

export function creditProfileDetailOptions(clientId: string) {
  return queryOptions({
    queryKey: queryKeys.credit.profile(clientId),
    queryFn: () => api.get<CreditProfile>(`/credit/profiles/${clientId}`),
  });
}

export function creditRequestListOptions(page = 1, status?: CreditRequestStatus) {
  const params = new URLSearchParams({ page: String(page), page_size: "25" });
  if (status) params.set("status", status);

  return queryOptions({
    queryKey: queryKeys.credit.requests(page, status),
    queryFn: () =>
      api.get<PaginatedResponse<CreditRequest>>(
        `/credit/requests?${params.toString()}`,
      ),
  });
}

export function creditAnalyticsOptions() {
  return queryOptions({
    queryKey: queryKeys.credit.analytics,
    queryFn: () => api.get<CreditAnalytics>("/credit/analytics"),
    refetchInterval: 60_000,
  });
}

export function currentUserOptions() {
  return queryOptions({
    queryKey: queryKeys.auth.me,
    queryFn: () => api.get<User>("/auth/me"),
    retry: false,
  });
}
