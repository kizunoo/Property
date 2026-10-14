// ─── lib/portal-types.ts ─────────────────────────────────────────────────────
// All types here are CLIENT-SAFE: no ML probability, tier, expected_value,
// buy probability, agent reasoning, or scoring breakdowns.
// ─────────────────────────────────────────────────────────────────────────────

export type PortalTab =
  | "overview"
  | "matches"
  | "catalog"
  | "viewings"
  | "activity"
  | "messages"
  | "profile"

// ─── Dashboard (overview + matches) ──────────────────────────────────────────

export interface MatchUnit {
  property_id: string
  name: string
  cost: number | null
  environment: string | null
  image_url: string | null
  property_type: string | null
  estimated_annual_savings: number | null
  payback_months: number | null
  /** Comes from client_facing_reasoning_cache — never from agent internal prompts */
  reasoning: string | null
}

export interface DashboardDemo {
  id: string
  property_name: string | null
  scheduled_at: string | null
  status: string
}

export interface DashboardData {
  client_name: string
  client_id: string
  relationship_stage: string
  matches: MatchUnit[]
  scheduled_demos: DashboardDemo[]
}

// ─── My Viewings ─────────────────────────────────────────────────────────────

export interface Viewing {
  id: string
  status: string
  scheduled_at: string | null
  property_name: string | null
  property_environment: string | null
}

export interface ViewingsData {
  viewings: Viewing[]
}

// ─── Activity ────────────────────────────────────────────────────────────────

export interface ActivityItem {
  viewing_id: string
  property_name: string
  status: string
  date: string | null
}

export interface ActivityData {
  activity: ActivityItem[]
}

// ─── Messages / Inquiries ────────────────────────────────────────────────────

export interface Inquiry {
  id: string
  message: string
  status: string          // 'open' | 'replied' | 'closed'
  agent_reply: string | null
  created_at: string
  property_name: string | null
  property_id: string | null
}

export interface InquiriesData {
  inquiries: Inquiry[]
}

// ─── Profile ─────────────────────────────────────────────────────────────────

export interface ClientProfile {
  client_id: string
  client_name: string
  stated_budget: number | null
  preferred_neighborhood: string | null
  relationship_stage: string | null
}

// ─── Catalog ─────────────────────────────────────────────────────────────────
// matched = true when this property is in the client's top-5 pipeline_evaluations
// by expected_value (same rule used by Matches/Overview tab)

export interface CatalogUnit {
  property_id: string
  name: string
  cost: number | null
  environment: string | null
  image_url: string | null
  property_type: string | null
  /** Repurposed field: payload tier rating 1-5 */
  payload_tier: number | null
  /** Repurposed field: coverage area per 8h shift (sq ft) */
  operational_range_sqft: number | null
  /** Repurposed field: navigation sensor/lidar redundancy count */
  nav_sensors: number | null
  estimated_annual_savings: number | null
  payback_months: number | null
  /** True = property is in client's top-5 matches by expected_value */
  matched: boolean
}

export interface CatalogData {
  units: CatalogUnit[]
  matched_property_ids: string[]
}

// ─── Preferences ─────────────────────────────────────────────────────────────

export type FinancingStatus = 'cash' | 'pre-approved' | 'in-progress' | 'unspecified' | 'leasing'
export type MoveInTimeline = '< 3 months' | '3-6 months' | '6-12 months' | 'flexible'

export interface PreferencesPayload {
  stated_budget?: number | null
  preferred_neighborhood?: string | null
  secondary_neighborhood?: string | null
  financing_status?: FinancingStatus | null
  move_in_timeline?: MoveInTimeline | null
  property_type_preference?: string | null
}

export interface PreferencesData {
  client_id: string
  stated_budget: number | null
  preferred_neighborhood: string | null
  secondary_neighborhood: string | null
  financing_status: FinancingStatus | null
  move_in_timeline: MoveInTimeline | null
  property_type_preference: string | null
  /** Number of evaluation rows re-scored after save */
  matches_refreshed_count: number
  updated_fields: string[]
}
