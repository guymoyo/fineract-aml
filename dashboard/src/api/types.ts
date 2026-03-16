/** Core domain types matching the backend schemas. */

export type TransactionType = "deposit" | "withdrawal" | "transfer";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export type AlertStatus =
  | "pending"
  | "under_review"
  | "confirmed_fraud"
  | "false_positive"
  | "escalated"
  | "dismissed";

export type AlertSource =
  | "rule_engine"
  | "anomaly_detection"
  | "ml_model"
  | "manual";

export type ReviewDecision = "legitimate" | "suspicious" | "confirmed_fraud";

export type CaseStatus =
  | "open"
  | "investigating"
  | "escalated"
  | "closed_legitimate"
  | "closed_fraud"
  | "sar_filed";

export type UserRole =
  | "analyst"
  | "senior_analyst"
  | "compliance_officer"
  | "admin";

// ── Entities ──────────────────────────────────────────────

export interface Transaction {
  id: string;
  fineract_transaction_id: string;
  fineract_account_id: string;
  fineract_client_id: string;
  transaction_type: TransactionType;
  amount: number;
  currency: string;
  transaction_date: string;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  anomaly_score: number | null;
  ip_address: string | null;
  country_code: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  transaction_id: string;
  status: AlertStatus;
  source: AlertSource;
  risk_score: number;
  title: string;
  description: string | null;
  triggered_rules: string | null;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  transaction?: Transaction;
}

export interface Review {
  id: string;
  alert_id: string;
  reviewer_id: string;
  decision: ReviewDecision;
  notes: string | null;
  evidence: string | null;
  sar_filed: boolean;
  sar_reference: string | null;
  created_at: string;
}

export interface Case {
  id: string;
  case_number: string;
  title: string;
  description: string | null;
  status: CaseStatus;
  assigned_to: string | null;
  fineract_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
}

// ── API Responses ─────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TransactionStats {
  total_transactions: number;
  total_flagged: number;
  total_confirmed_fraud: number;
  total_false_positives: number;
  average_risk_score: number | null;
  transactions_today: number;
  alerts_pending: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ── Request Bodies ────────────────────────────────────────

export interface ReviewCreateRequest {
  decision: ReviewDecision;
  notes?: string;
  evidence?: string;
  sar_filed?: boolean;
  sar_reference?: string;
}

export interface CaseCreateRequest {
  title: string;
  description?: string;
  fineract_client_id?: string;
  transaction_ids?: string[];
}

export interface LoginRequest {
  username: string;
  password: string;
}
