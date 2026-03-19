/** TanStack Query mutations for the AML API. */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { queryKeys } from "./queries";
import type {
  Alert,
  AlertStatus,
  Case,
  CaseCreateRequest,
  CaseStatus,
  CreditProfile,
  CreditRequest,
  CreditRequestCreateBody,
  CreditReviewActionBody,
  LoginRequest,
  Review,
  ReviewCreateRequest,
  TokenResponse,
} from "./types";

export function useLogin() {
  return useMutation({
    mutationFn: (data: LoginRequest) =>
      api.post<TokenResponse>("/auth/login", data),
    onSuccess: (data) => {
      localStorage.setItem("aml_token", data.access_token);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return () => {
    localStorage.removeItem("aml_token");
    queryClient.clear();
    window.location.href = "/login";
  };
}

export function useSubmitReview(alertId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ReviewCreateRequest) =>
      api.post<Review>(`/alerts/${alertId}/review`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.transactions.stats });
    },
  });
}

export function useAssignAlert(alertId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assignedTo: string) =>
      api.patch<Alert>(`/alerts/${alertId}/assign`, {
        assigned_to: assignedTo,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useUpdateAlertStatus(alertId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (status: AlertStatus) =>
      api.patch<Alert>(`/alerts/${alertId}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useCreateCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CaseCreateRequest) =>
      api.post<Case>("/cases", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.cases.all });
    },
  });
}

export function useUpdateCaseStatus(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (status: CaseStatus) =>
      api.patch<Case>(`/cases/${caseId}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.cases.all });
    },
  });
}

// ── Credit Scoring Mutations ─────────────────────────────

export function useCreateCreditRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreditRequestCreateBody) =>
      api.post<CreditRequest>("/credit/request", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.credit.all });
    },
  });
}

export function useReviewCreditRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreditReviewActionBody) =>
      api.put<CreditRequest>(`/credit/requests/${requestId}/review`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.credit.all });
    },
  });
}

export function useRefreshCreditProfile(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<CreditProfile>(`/credit/profiles/${clientId}/refresh`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.credit.all });
    },
  });
}
