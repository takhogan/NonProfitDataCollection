import type {
  Activity,
  ActivityCreate,
  ActivityQuery,
  ActivityUpdate,
  Alert,
  AlertSubscription,
  AlertSubscriptionCreate,
  AreaDetail,
  AreaLevel,
  AreaRef,
  AreasOfNeedResponse,
  Bucket,
  CoverageResponse,
  ErrorEnvelope,
  IndicatorCell,
  Me,
  MeetingPoint,
  NeedCategory,
  OperationKey,
  ServiceKind,
  SystemStatus,
  UUID,
} from './schema';

export interface IndicatorQuery {
  level: AreaLevel;
  bucket: Bucket;
  category?: NeedCategory | ServiceKind;
}

export interface AreasOfNeedQuery {
  level: AreaLevel;
  bucket: Bucket;
  category?: NeedCategory;
}

export interface CoverageQuery {
  bucket: Bucket;
  category?: NeedCategory;
}

/**
 * The web app's view of the planned `/v1` API. One method per endpoint; the
 * HTTP path each maps to is noted. Implemented by `HttpApiClient` (real) and
 * `MockApiClient` (synthetic Caracas data).
 */
export interface ApiClient {
  /** GET /v1/me (API-011) */
  getMe(): Promise<Me>;
  /** GET /v1/status — assumed endpoint for WEB-007; not yet in API-*. */
  getStatus(): Promise<SystemStatus>;
  /** GET /v1/areas — parishes and sectors with aliases (area picker). */
  listAreas(): Promise<AreaRef[]>;
  /** GET /v1/meeting-points?sector_id= (API-032 read) */
  listMeetingPoints(sectorIds?: UUID[]): Promise<MeetingPoint[]>;
  /** GET /v1/indicators (API-040) */
  getIndicators(q: IndicatorQuery): Promise<IndicatorCell[]>;
  /** GET /v1/areas-of-need (API-041) */
  getAreasOfNeed(q: AreasOfNeedQuery): Promise<AreasOfNeedResponse>;
  /** GET /v1/coverage (API-042) */
  getCoverage(q: CoverageQuery): Promise<CoverageResponse>;
  /** GET /v1/areas/{id} (API-043) */
  getAreaDetail(id: UUID): Promise<AreaDetail>;
  /** GET /v1/activities (API-051) */
  listActivities(q?: ActivityQuery): Promise<Activity[]>;
  /** POST /v1/activities (API-051) */
  createActivity(cmd: ActivityCreate): Promise<Activity>;
  /** PATCH /v1/activities/{id} (API-051) */
  updateActivity(id: UUID, cmd: ActivityUpdate): Promise<Activity>;
  /** POST /v1/activities/{id}/confirm (API-051) */
  confirmActivity(id: UUID, operationKey: OperationKey): Promise<Activity>;
  /** GET /v1/alert-subscriptions (API-052) */
  listAlertSubscriptions(): Promise<AlertSubscription[]>;
  /** POST /v1/alert-subscriptions (API-052) */
  createAlertSubscription(cmd: AlertSubscriptionCreate): Promise<AlertSubscription>;
  /** PATCH /v1/alert-subscriptions/{id} (API-052) */
  setAlertSubscriptionMuted(id: UUID, muted: boolean): Promise<AlertSubscription>;
  /** DELETE /v1/alert-subscriptions/{id} (API-052) */
  deleteAlertSubscription(id: UUID): Promise<void>;
  /** GET /v1/alerts (API-052) */
  listAlerts(): Promise<Alert[]>;
}

/** Error raised by every client; carries the CON-040 envelope. */
export class ApiError extends Error {
  readonly envelope: ErrorEnvelope;
  readonly status: number;

  constructor(envelope: ErrorEnvelope, status: number) {
    super(`${envelope.code}: ${envelope.message_key}`);
    this.name = 'ApiError';
    this.envelope = envelope;
    this.status = status;
  }

  get code() {
    return this.envelope.code;
  }
}

export function newOperationKey(): OperationKey {
  return crypto.randomUUID();
}
