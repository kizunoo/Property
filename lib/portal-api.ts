// ─── lib/portal-api.ts ───────────────────────────────────────────────────────
// Typed fetch helpers for the client portal.
// All helpers go through the Next.js BFF (/api/portal/...) — never directly
// to FastAPI. No internal scoring fields are requested or returned.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  DashboardData,
  ViewingsData,
  ActivityData,
  InquiriesData,
  ClientProfile,
  CatalogData,
  PreferencesPayload,
  PreferencesData,
} from "@/lib/portal-types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

class PortalApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = "PortalApiError"
  }
}

async function apiFetch<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts)
  const data = await res.json()
  if (!res.ok) {
    throw new PortalApiError(res.status, data?.error ?? `Request failed (${res.status})`)
  }
  return data as T
}

// ─── GET endpoints ───────────────────────────────────────────────────────────

export async function fetchDashboard(clientId: string): Promise<DashboardData> {
  return apiFetch<DashboardData>(`/api/portal/${clientId}/dashboard`)
}

export async function fetchMyViewings(clientId: string): Promise<ViewingsData> {
  return apiFetch<ViewingsData>(`/api/portal/${clientId}/my_viewings`)
}

export async function fetchActivity(clientId: string): Promise<ActivityData> {
  return apiFetch<ActivityData>(`/api/portal/${clientId}/activity`)
}

export async function fetchInquiries(clientId: string): Promise<InquiriesData> {
  return apiFetch<InquiriesData>(`/api/portal/${clientId}/inquiries`)
}

// ─── POST endpoints ───────────────────────────────────────────────────────────

export interface RequestDemoPayload {
  property_id: string
  preferred_date?: string | null
  notes?: string | null
}

export interface RequestDemoResult {
  success: boolean
  message: string
  viewing?: { id: string } | null
  existing_id?: string
}

export async function requestDemo(
  clientId: string,
  payload: RequestDemoPayload,
): Promise<RequestDemoResult> {
  return apiFetch<RequestDemoResult>(`/api/portal/${clientId}/request_demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

export interface SubmitInquiryPayload {
  property_id: string
  message: string
}

export interface SubmitInquiryResult {
  id: string
  client_id: string
  property_id: string
  message: string
  status: string
}

export async function submitInquiry(
  clientId: string,
  payload: SubmitInquiryPayload,
): Promise<SubmitInquiryResult> {
  return apiFetch<SubmitInquiryResult>(`/api/portal/${clientId}/inquiry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

// ─── Profile (from dashboard data — no separate endpoint needed) ──────────────

export function extractProfile(data: DashboardData): ClientProfile {
  return {
    client_id: data.client_id,
    client_name: data.client_name,
    stated_budget: null,          // not returned by dashboard endpoint; show as unknown
    preferred_neighborhood: null,
    relationship_stage: data.relationship_stage ?? null,
  }
}

// ─── Re-export error class ───────────────────────────────────────────────────

export { PortalApiError }

// ─── Catalog ──────────────────────────────────────────────────────────────────

export async function fetchCatalog(clientId: string): Promise<CatalogData> {
  return apiFetch<CatalogData>(`/api/portal/${clientId}/catalog`)
}

// ─── Preferences ──────────────────────────────────────────────────────────────

export async function fetchPreferences(clientId: string): Promise<PreferencesData> {
  return apiFetch<PreferencesData>(`/api/portal/${clientId}/preferences`)
}

export async function savePreferences(
  clientId: string,
  payload: PreferencesPayload,
): Promise<PreferencesData> {
  return apiFetch<PreferencesData>(`/api/portal/${clientId}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

// ─── Auth / Session ──────────────────────────────────────────────────────────

export interface PortalMeData {
  authenticated: boolean
  session_id: string
  contact_id: string | null
  contact_name: string
  portal_role: "admin" | "evaluator" | "finance_viewer" | "legacy_readonly"
  client_id: string
  client_name: string
  is_legacy: boolean
}

export async function fetchAuthMe(): Promise<PortalMeData> {
  return apiFetch<PortalMeData>("/api/portal/auth/me")
}

export async function logoutPortal(): Promise<void> {
  await fetch("/api/portal/auth/logout", { method: "POST" })
}

