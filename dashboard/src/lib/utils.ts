import { clsx, type ClassValue } from "clsx";
import { format, formatDistanceToNow } from "date-fns";
import type { AlertStatus, CaseStatus, RiskLevel } from "../api/types";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCurrency(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatDate(date: string): string {
  return format(new Date(date), "MMM d, yyyy HH:mm");
}

export function formatRelativeDate(date: string): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true });
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function riskLevelColor(level: RiskLevel | null): string {
  switch (level) {
    case "low":
      return "text-green-600 bg-green-50 border-green-200";
    case "medium":
      return "text-amber-600 bg-amber-50 border-amber-200";
    case "high":
      return "text-red-600 bg-red-50 border-red-200";
    case "critical":
      return "text-red-900 bg-red-100 border-red-300";
    default:
      return "text-gray-500 bg-gray-50 border-gray-200";
  }
}

export function alertStatusColor(status: AlertStatus): string {
  switch (status) {
    case "pending":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "under_review":
      return "text-blue-700 bg-blue-50 border-blue-200";
    case "confirmed_fraud":
      return "text-red-700 bg-red-50 border-red-200";
    case "false_positive":
      return "text-green-700 bg-green-50 border-green-200";
    case "escalated":
      return "text-purple-700 bg-purple-50 border-purple-200";
    case "dismissed":
      return "text-gray-500 bg-gray-50 border-gray-200";
  }
}

export function caseStatusColor(status: CaseStatus): string {
  switch (status) {
    case "open":
      return "text-blue-700 bg-blue-50 border-blue-200";
    case "investigating":
      return "text-amber-700 bg-amber-50 border-amber-200";
    case "escalated":
      return "text-purple-700 bg-purple-50 border-purple-200";
    case "closed_legitimate":
      return "text-green-700 bg-green-50 border-green-200";
    case "closed_fraud":
      return "text-red-700 bg-red-50 border-red-200";
    case "sar_filed":
      return "text-red-900 bg-red-100 border-red-300";
  }
}

export function formatStatusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
