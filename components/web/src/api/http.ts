import type { ApiClient, AreasOfNeedQuery, CoverageQuery, IndicatorQuery } from './client';
import { ApiError } from './client';
import type {
  Activity,
  ActivityCreate,
  ActivityQuery,
  ActivityUpdate,
  Alert,
  AlertSubscription,
  AlertSubscriptionCreate,
  AreaDetail,
  AreaRef,
  AreasOfNeedResponse,
  CoverageResponse,
  ErrorEnvelope,
  IndicatorCell,
  Me,
  MeetingPoint,
  SystemStatus,
  UUID,
} from './schema';

type Query = Record<string, string | number | boolean | string[] | undefined>;

function qs(q: Query = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined) continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

/**
 * Real client for the FastAPI `/v1` API. Cookie-authenticated (SEC-05), so
 * requests use `credentials: 'include'` and `cache: 'no-store'` (SEC-07).
 * CSRF handling (API-013) is TODO until the backend defines the header.
 */
export class HttpApiClient implements ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}${path}`, {
        method,
        credentials: 'include',
        cache: 'no-store',
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(
        { code: 'network_error', message_key: 'errors.network', details: null, request_id: null },
        0,
      );
    }
    if (res.status === 204) return undefined as T;
    const json: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const env = (json ?? {}) as Partial<ErrorEnvelope>;
      throw new ApiError(
        {
          code: env.code ?? 'internal',
          message_key: env.message_key ?? 'errors.internal',
          details: env.details ?? null,
          request_id: env.request_id ?? res.headers.get('x-request-id'),
        },
        res.status,
      );
    }
    return json as T;
  }

  getMe() {
    return this.request<Me>('GET', '/v1/me');
  }
  getStatus() {
    return this.request<SystemStatus>('GET', '/v1/status');
  }
  listAreas() {
    return this.request<AreaRef[]>('GET', '/v1/areas');
  }
  listMeetingPoints(sectorIds?: UUID[]) {
    return this.request<MeetingPoint[]>(
      'GET',
      `/v1/meeting-points${qs({ sector_id: sectorIds })}`,
    );
  }
  getIndicators(q: IndicatorQuery) {
    return this.request<IndicatorCell[]>('GET', `/v1/indicators${qs({ ...q })}`);
  }
  getAreasOfNeed(q: AreasOfNeedQuery) {
    return this.request<AreasOfNeedResponse>(
      'GET',
      `/v1/areas-of-need${qs({ ...q })}`,
    );
  }
  getCoverage(q: CoverageQuery) {
    return this.request<CoverageResponse>('GET', `/v1/coverage${qs({ ...q })}`);
  }
  getAreaDetail(id: UUID) {
    return this.request<AreaDetail>('GET', `/v1/areas/${encodeURIComponent(id)}`);
  }
  listActivities(q: ActivityQuery = {}) {
    return this.request<Activity[]>('GET', `/v1/activities${qs({ ...q })}`);
  }
  createActivity(cmd: ActivityCreate) {
    return this.request<Activity>('POST', '/v1/activities', cmd);
  }
  updateActivity(id: UUID, cmd: ActivityUpdate) {
    return this.request<Activity>(
      'PATCH',
      `/v1/activities/${encodeURIComponent(id)}`,
      cmd,
    );
  }
  confirmActivity(id: UUID, operationKey: string) {
    return this.request<Activity>(
      'POST',
      `/v1/activities/${encodeURIComponent(id)}/confirm`,
      { operation_key: operationKey },
    );
  }
  listAlertSubscriptions() {
    return this.request<AlertSubscription[]>('GET', '/v1/alert-subscriptions');
  }
  createAlertSubscription(cmd: AlertSubscriptionCreate) {
    return this.request<AlertSubscription>(
      'POST',
      '/v1/alert-subscriptions',
      cmd,
    );
  }
  setAlertSubscriptionMuted(id: UUID, muted: boolean) {
    return this.request<AlertSubscription>(
      'PATCH',
      `/v1/alert-subscriptions/${encodeURIComponent(id)}`,
      { muted },
    );
  }
  deleteAlertSubscription(id: UUID) {
    return this.request<void>('DELETE', `/v1/alert-subscriptions/${encodeURIComponent(id)}`);
  }
  listAlerts() {
    return this.request<Alert[]>('GET', '/v1/alerts');
  }
}
