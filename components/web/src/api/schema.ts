/**
 * ============================================================================
 *  HAND-WRITTEN API TYPES — TEMPORARY STAND-IN
 * ============================================================================
 *
 * These types mirror the *planned* `/v1` contracts (contracts/REQUIREMENTS.md
 * CON-002/003/012–014/040 and api/REQUIREMENTS.md API-011, API-040–052). The
 * backend in components/whatsapp/api does not expose them yet.
 *
 * When the FastAPI app exports its OpenAPI document (CON-001), replace this file
 * with the output of:
 *
 *     npx openapi-typescript ../contracts/openapi.json -o src/api/schema.gen.ts
 *
 * and re-export the generated component schemas under these names. Nothing
 * outside `src/api` should import from anywhere but `src/api` (index.ts), so
 * the swap stays local.
 *
 * Conventions taken from the contracts:
 * - snake_case field names, as the Pydantic models will emit them.
 * - Instants are UTC ISO-8601 strings (NFR-02); the UI converts to Caracas time.
 * - CON-003: tri-states use the literal "unknown", never 0/false/null. Counts on
 *   an indicator cell are `null` exactly when the cell has no data
 *   (`coverage_label: "none"`) or is suppressed — never 0 as a stand-in.
 * ============================================================================
 */

// ---------- CON-002 common types ----------

export type UUID = string;
/** UTC ISO-8601 instant, e.g. "2026-11-07T14:00:00Z". */
export type UtcInstant = string;
export type TimePrecision = 'exact' | 'approximate' | 'day' | 'unknown';
export type QuantityUnit = 'liters' | 'people' | 'devices';
export interface Quantity {
  value: number;
  unit: QuantityUnit;
}
/** Client-generated idempotency key for a command (WEB-005). */
export type OperationKey = string;

export type NeedCategory = 'water_drinking' | 'water_other' | 'charging';
export type ServiceKind = 'electricity' | 'piped_water';
export type AreaLevel = 'parish' | 'sector';
export type Bucket = '6h' | '24h' | '7d';

export interface AreaRef {
  id: UUID;
  name: string;
  level: AreaLevel;
  parent_id: UUID | null;
  parent_name: string | null;
  aliases: string[];
}

export interface MeetingPoint {
  id: UUID;
  sector_id: UUID;
  name: string;
  kind: 'plaza' | 'church' | 'school' | 'shop' | 'other';
}

// ---------- API-011 context ----------

export type Role =
  | 'org_admin'
  | 'coordinator'
  | 'reviewer'
  | 'intake_volunteer'
  | 'provider'
  | 'analyst';
export type PrivacyProfile = 'protective' | 'standard';
export type VettingStatus = 'unvetted' | 'vetted' | 'suspended';

export interface ProviderOrganizationRef {
  id: UUID;
  name: string;
  vetting_status: VettingStatus;
}

export interface Me {
  user: { id: UUID; display_name: string };
  tenant: { id: UUID; name: string; privacy_profile: PrivacyProfile; suppression_k: number };
  roles: Role[];
  provider_organization: ProviderOrganizationRef | null;
}

// ---------- WEB-007 status (endpoint not yet specified in API-*; assumed GET /v1/status) ----------

export interface SystemStatus {
  generated_at: UtcInstant;
  /** Seconds between webhook receipt and aggregate inclusion (NFR-07). */
  intake_lag_seconds: number;
  stale_indicator_count: number;
  degraded_services: string[];
}

// ---------- CON-012 indicator cells ----------

export type CoverageLabel = 'none' | 'thin' | 'reported';
export type ConfidenceLevel = 'low' | 'medium' | 'high';
export type ConfidenceReason =
  | 'single_source'
  | 'multiple_sources'
  | 'pending_review'
  | 'reviewed'
  | 'stale'
  | 'fresh'
  | 'agrees_external'
  | 'conflicts_external'
  | 'no_external';

export interface Confidence {
  level: ConfidenceLevel;
  reasons: ConfidenceReason[];
}

export interface UrgencyMix {
  urgent: number;
  soon: number;
  can_wait: number;
  unknown: number;
}
export interface SupplyMix {
  none: number;
  under_one_day: number;
  one_to_three_days: number;
  more_than_three_days: number;
  unknown: number;
}
export interface StatusMix {
  on: number;
  off: number;
  intermittent: number;
  unknown: number;
}

export interface IndicatorCell {
  area: AreaRef;
  /** Exactly one of `category` / `service` is set. */
  category: NeedCategory | null;
  service: ServiceKind | null;
  bucket: Bucket;
  suppressed: boolean;
  coverage_label: CoverageLabel;
  active_needs: number | null;
  distinct_reporters: number | null;
  /** Only in the `standard` profile; always null under `protective`. */
  distinct_households: number | null;
  people_affected_known: number | null;
  /** Number of needs whose people count is unknown. */
  people_affected_unknown_count: number | null;
  urgency_mix: UrgencyMix | null;
  supply_mix: SupplyMix | null;
  status_mix: StatusMix | null;
  /** Newest confirmed observation in the bucket. */
  freshness: UtcInstant | null;
  pending_review_share: number | null;
  confidence: Confidence;
  method_version: string;
  input_watermark: UtcInstant;
}

// ---------- CON-013 ranking and coverage ----------

export type RankingCriterionKey =
  | 'urgent_active_needs'
  | 'needs_per_reporter'
  | 'oldest_unmet_need'
  | 'freshness';

export interface RankingCriterion {
  key: RankingCriterionKey;
  direction: 'desc' | 'asc';
}

export interface AreaOfNeed {
  rank: number;
  cell: IndicatorCell;
  criteria_values: {
    urgent_active_needs: number;
    needs_per_reporter: number;
    oldest_unmet_need: UtcInstant;
    freshness: UtcInstant;
  };
}

export interface AreasOfNeedResponse {
  method_version: string;
  criteria: RankingCriterion[];
  bucket: Bucket;
  items: AreaOfNeed[];
  /** Cells that cannot be ranked: suppressed or no data. Listed, never shown as zero. */
  unranked: IndicatorCell[];
}

export type CoverageStatus = 'covered' | 'uncovered' | 'unknown';

export interface CoverageCell {
  area: AreaRef;
  category: NeedCategory;
  status: CoverageStatus;
  /** True when active need is above the coverage threshold (DOM-052). */
  high_need: boolean;
  /** The need cell behind this coverage decision (already suppressed). */
  need: IndicatorCell;
  activities: ActivitySummary[];
}

export interface CoverageResponse {
  bucket: Bucket;
  generated_at: UtcInstant;
  method_version: string;
  items: CoverageCell[];
}

// ---------- CON-014 providers and activities ----------

export type ActivityType =
  | 'water_distribution_point'
  | 'water_delivery'
  | 'charging_point'
  | 'other';
export type ActivityStatus = 'planned' | 'active' | 'paused' | 'ended';
export type ActivityVisibility = 'all_providers' | 'internal' | 'public';
export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';

export type Schedule =
  | { kind: 'one_off'; date: string; start_time: string; end_time: string }
  | { kind: 'recurring'; days: Weekday[]; start_time: string; end_time: string };

export interface PublicLocation {
  kind: 'meeting_point' | 'public_site';
  id: UUID;
  name: string;
}

export interface ActivitySummary {
  id: UUID;
  provider_organization: { id: UUID; name: string };
  type: ActivityType;
  status: ActivityStatus;
  /** DOM-053: internal-only entries from other providers count but hide details. */
  details_hidden: boolean;
}

export interface Activity extends ActivitySummary {
  category: NeedCategory;
  areas: AreaRef[];
  /** Null when `details_hidden`. */
  schedule: Schedule | null;
  capacity: Quantity | null;
  public_location: PublicLocation | null;
  visibility: ActivityVisibility;
  last_confirmed_at: UtcInstant;
  /** DOM-051: not confirmed for 7 days. */
  unconfirmed: boolean;
  /** Optimistic-concurrency version (CON-040 `stale_version`). */
  version: number;
  created_at: UtcInstant;
}

export interface ActivityCreate {
  operation_key: OperationKey;
  type: ActivityType;
  category: NeedCategory;
  area_ids: UUID[];
  schedule: Schedule;
  capacity: Quantity | null;
  public_location_id: UUID | null;
  visibility: ActivityVisibility;
  status: ActivityStatus;
}

export interface ActivityUpdate {
  operation_key: OperationKey;
  version: number;
  status?: ActivityStatus;
  schedule?: Schedule;
  capacity?: Quantity | null;
  visibility?: ActivityVisibility;
}

export interface ActivityQuery {
  /** Only the caller's provider organization. */
  mine?: boolean;
  area_id?: UUID;
  category?: NeedCategory;
}

// ---------- API-043 area detail ----------

export interface ExternalSignal {
  source: 'monitor_ciudad' | 'night_lights';
  observed_at: UtcInstant;
  /** Short, already-localizable code + value; never resident free text. */
  kind: 'outage_reported' | 'outage_cleared' | 'radiance_drop' | 'radiance_normal';
  detail: string | null;
}

export interface DataQualityNote {
  code: 'pending_review_high' | 'single_source' | 'no_recent_reports' | 'outlier_flag';
  bucket: Bucket;
}

export interface HistoryPoint {
  date: string; // YYYY-MM-DD, Caracas local date
  category: NeedCategory;
  suppressed: boolean;
  active_needs: number | null;
}

export interface AreaDetail {
  area: AreaRef;
  method_version: string;
  needs: IndicatorCell[];
  services: IndicatorCell[];
  history: HistoryPoint[];
  activities: Activity[];
  external_context: ExternalSignal[];
  data_quality: DataQualityNote[];
  meeting_points: MeetingPoint[];
}

// ---------- CON-014 alerts ----------

export type AlertTrigger =
  | { kind: 'new_urgent' }
  | { kind: 'active_needs_above'; threshold: number }
  | { kind: 'became_uncovered' }
  | { kind: 'external_outage' };

export interface AlertSubscription {
  id: UUID;
  area_ids: UUID[];
  category: NeedCategory;
  trigger: AlertTrigger;
  muted: boolean;
  created_at: UtcInstant;
}

export interface AlertSubscriptionCreate {
  operation_key: OperationKey;
  area_ids: UUID[];
  category: NeedCategory;
  trigger: AlertTrigger;
}

/** Aggregate fields only (CON-004). */
export interface Alert {
  id: UUID;
  subscription_id: UUID;
  area: AreaRef;
  category: NeedCategory;
  trigger_kind: AlertTrigger['kind'];
  /** Banded or suppressed value; null when suppressed. */
  active_needs: number | null;
  created_at: UtcInstant;
}

// ---------- CON-040 error envelope ----------

export type ErrorCode =
  | 'validation_failed'
  | 'not_found'
  | 'forbidden'
  | 'conflict'
  | 'stale_version'
  | 'invalid_transition'
  | 'idempotency_conflict'
  | 'network_error'
  | 'internal';

export interface ErrorEnvelope {
  code: ErrorCode;
  message_key: string;
  details: Record<string, unknown> | null;
  request_id: string | null;
}
