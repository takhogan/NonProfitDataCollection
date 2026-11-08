import type { ApiClient, AreasOfNeedQuery, CoverageQuery, IndicatorQuery } from '../client';
import { ApiError } from '../client';
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
  DataQualityNote,
  ErrorCode,
  ExternalSignal,
  HistoryPoint,
  Me,
  NeedCategory,
  Role,
  ServiceKind,
  SystemStatus,
  UUID,
  VettingStatus,
} from '../schema';
import {
  coverageCells,
  METHOD_VERSION,
  NEED_CATEGORIES,
  needCells,
  RANKING_CRITERIA,
  rankAreas,
  serviceCells,
} from './compute';
import { MEETING_POINTS, MY_PROVIDER, OTHER_PROVIDERS, PARISH_AREAS, SECTOR_AREAS, SECTOR_SEEDS, TENANT } from './data';

const HOUR = 3600_000;
const DAY = 24 * HOUR;
const SEVEN_DAYS = 7 * DAY;

export interface DevIdentity {
  roles: Role[];
  vetting_status: VettingStatus;
}

export type SimulatedStatus = 'normal' | 'intake_lag' | 'degraded';

export interface MockOptions {
  /** Fixed clock for tests. Defaults to Date.now at construction. */
  now?: number;
  /** Artificial latency range in ms; 0 for tests. */
  latencyMs?: number;
}

function area(id: string): AreaRef {
  const a = [...SECTOR_AREAS, ...PARISH_AREAS].find((x) => x.id === id);
  if (!a) throw new ApiError({ code: 'not_found', message_key: 'errors.not_found', details: { id }, request_id: null }, 404);
  return a;
}

function clone<T>(x: T): T {
  return structuredClone(x);
}

/**
 * In-memory implementation of `ApiClient` with synthetic Caracas data. Writes
 * live only in this object (WEB-060: nothing is persisted in the browser).
 */
export class MockApiClient implements ApiClient {
  private readonly now: number;
  private readonly latencyMs: number;
  private activities: Activity[];
  private subscriptions: AlertSubscription[];
  private alerts: Alert[];
  private readonly idempotency = new Map<string, unknown>();
  private failNext: ErrorCode | null = null;
  private identity: DevIdentity = { roles: ['provider'], vetting_status: 'vetted' };
  private simulatedStatus: SimulatedStatus = 'normal';

  constructor(opts: MockOptions = {}) {
    this.now = opts.now ?? Date.now();
    this.latencyMs = opts.latencyMs ?? 250;
    this.activities = this.seedActivities();
    this.subscriptions = this.seedSubscriptions();
    this.alerts = this.seedAlerts();
  }

  // ---- dev / test controls (not part of ApiClient) ----

  /** Switch the signed-in mock identity (dev role switcher, tests). */
  setIdentity(identity: DevIdentity) {
    this.identity = identity;
  }

  setSimulatedStatus(status: SimulatedStatus) {
    this.simulatedStatus = status;
  }

  /** Make the next write fail with the given error code (WEB-005 testing). */
  failNextWrite(code: ErrorCode = 'network_error') {
    this.failNext = code;
  }

  private async delay() {
    if (this.latencyMs <= 0) return;
    await new Promise((r) => setTimeout(r, this.latencyMs * (0.6 + Math.random() * 0.8)));
  }

  private async read<T>(fn: () => T): Promise<T> {
    await this.delay();
    return clone(fn());
  }

  private async write<T>(operationKey: string | null, fn: () => T): Promise<T> {
    await this.delay();
    if (this.failNext) {
      const code = this.failNext;
      this.failNext = null;
      throw new ApiError(
        { code, message_key: `errors.${code}`, details: null, request_id: `mock-${crypto.randomUUID().slice(0, 8)}` },
        code === 'network_error' ? 0 : 409,
      );
    }
    if (operationKey && this.idempotency.has(operationKey)) {
      return clone(this.idempotency.get(operationKey) as T);
    }
    const result = fn();
    if (operationKey) this.idempotency.set(operationKey, clone(result));
    return clone(result);
  }

  private get isProvider() {
    return this.identity.roles.includes('provider');
  }

  private forbidUnlessProvider() {
    if (!this.isProvider) {
      throw new ApiError({ code: 'forbidden', message_key: 'errors.forbidden', details: null, request_id: null }, 403);
    }
  }

  // ---- ApiClient ----

  getMe(): Promise<Me> {
    return this.read(() => ({
      user: { id: 'user-dev', display_name: 'Usuario de desarrollo' },
      tenant: { id: TENANT.id, name: TENANT.name, privacy_profile: 'protective', suppression_k: TENANT.k },
      roles: this.identity.roles,
      provider_organization: this.isProvider
        ? { ...MY_PROVIDER, vetting_status: this.identity.vetting_status }
        : null,
    }));
  }

  getStatus(): Promise<SystemStatus> {
    return this.read(() => ({
      generated_at: new Date(this.now).toISOString(),
      intake_lag_seconds: this.simulatedStatus === 'intake_lag' ? 540 : 35,
      stale_indicator_count: this.simulatedStatus === 'degraded' ? 4 : 0,
      degraded_services: this.simulatedStatus === 'degraded' ? ['whatsapp_webhook'] : [],
    }));
  }

  listAreas() {
    return this.read(() => [...PARISH_AREAS, ...SECTOR_AREAS]);
  }

  listMeetingPoints(sectorIds?: UUID[]) {
    return this.read(() => MEETING_POINTS.filter((m) => !sectorIds || sectorIds.includes(m.sector_id)));
  }

  getIndicators(q: IndicatorQuery) {
    return this.read(() => {
      const isService = q.category === 'electricity' || q.category === 'piped_water';
      if (isService) return serviceCells(q.level, q.bucket, this.now, q.category as ServiceKind);
      if (q.category) return needCells(q.level, q.bucket, this.now, q.category as NeedCategory);
      return [...needCells(q.level, q.bucket, this.now), ...serviceCells(q.level, q.bucket, this.now)];
    });
  }

  getAreasOfNeed(q: AreasOfNeedQuery) {
    return this.read(() => {
      const { items, unranked } = rankAreas(needCells(q.level, q.bucket, this.now, q.category));
      return { method_version: METHOD_VERSION, criteria: RANKING_CRITERIA, bucket: q.bucket, items, unranked };
    });
  }

  getCoverage(q: CoverageQuery) {
    return this.read(() => ({
      bucket: q.bucket,
      generated_at: new Date(this.now).toISOString(),
      method_version: METHOD_VERSION,
      items: coverageCells(q.bucket, this.now, this.visibleActivities(), q.category),
    }));
  }

  getAreaDetail(id: UUID) {
    return this.read((): AreaDetail => {
      const a = area(id);
      const level = a.level;
      const buckets = ['6h', '24h', '7d'] as const;
      const needs = buckets.flatMap((b) => needCells(level, b, this.now).filter((c) => c.area.id === id));
      const services = buckets.flatMap((b) => serviceCells(level, b, this.now).filter((c) => c.area.id === id));
      const history: HistoryPoint[] = [];
      for (let d = 6; d >= 0; d--) {
        const date = new Date(this.now - d * DAY).toLocaleDateString('en-CA', { timeZone: 'America/Caracas' });
        for (const cat of NEED_CATEGORIES) {
          const cell = needCells(level, '24h', this.now, cat).find((c) => c.area.id === id)!;
          if (cell.coverage_label === 'none') {
            history.push({ date, category: cat, suppressed: false, active_needs: null });
          } else if (cell.suppressed) {
            history.push({ date, category: cat, suppressed: true, active_needs: null });
          } else {
            const wobble = 0.6 + (((d * 3 + cat.length) % 5) * 0.12);
            const v = Math.round((cell.active_needs ?? 0) * wobble);
            const tooFew = v < TENANT.k;
            history.push({ date, category: cat, suppressed: tooFew, active_needs: tooFew ? null : v });
          }
        }
      }
      const seed = SECTOR_SEEDS.find((s) => s.id === id);
      const external_context: ExternalSignal[] =
        seed?.external === 'agrees'
          ? [
              { source: 'monitor_ciudad', observed_at: new Date(this.now - 5 * HOUR).toISOString(), kind: 'outage_reported', detail: null },
              { source: 'night_lights', observed_at: new Date(this.now - 20 * HOUR).toISOString(), kind: 'radiance_drop', detail: null },
            ]
          : seed?.external === 'conflicts'
            ? [{ source: 'monitor_ciudad', observed_at: new Date(this.now - 8 * HOUR).toISOString(), kind: 'outage_cleared', detail: null }]
            : [];
      const data_quality: DataQualityNote[] = [];
      for (const c of needs.filter((c) => c.bucket === '24h')) {
        if ((c.pending_review_share ?? 0) >= 0.3) data_quality.push({ code: 'pending_review_high', bucket: '24h' });
        if (c.confidence.reasons.includes('single_source') && c.coverage_label !== 'none') data_quality.push({ code: 'single_source', bucket: '24h' });
      }
      if (needs.every((c) => c.coverage_label === 'none')) data_quality.push({ code: 'no_recent_reports', bucket: '7d' });
      const sectorIds = level === 'sector' ? [id] : SECTOR_AREAS.filter((s) => s.parent_id === id).map((s) => s.id);
      return {
        area: a,
        method_version: METHOD_VERSION,
        needs,
        services,
        history,
        activities: this.visibleActivities().filter((act) => act.areas.some((ar) => sectorIds.includes(ar.id))),
        external_context,
        data_quality: dedupeNotes(data_quality),
        meeting_points: MEETING_POINTS.filter((m) => sectorIds.includes(m.sector_id)),
      };
    });
  }

  listActivities(q: ActivityQuery = {}) {
    return this.read(() =>
      this.visibleActivities().filter(
        (a) =>
          (!q.mine || a.provider_organization.id === MY_PROVIDER.id) &&
          (!q.area_id || a.areas.some((ar) => ar.id === q.area_id)) &&
          (!q.category || a.category === q.category),
      ),
    );
  }

  createActivity(cmd: ActivityCreate) {
    return this.write(cmd.operation_key, () => {
      this.forbidUnlessProvider();
      if (cmd.area_ids.length === 0) {
        throw new ApiError({ code: 'validation_failed', message_key: 'errors.validation_failed', details: { area_ids: 'required' }, request_id: null }, 422);
      }
      const mp = cmd.public_location_id ? MEETING_POINTS.find((m) => m.id === cmd.public_location_id) : null;
      const nowIso = new Date(this.now).toISOString();
      const act: Activity = {
        id: `act-${crypto.randomUUID()}`,
        provider_organization: { id: MY_PROVIDER.id, name: MY_PROVIDER.name },
        type: cmd.type,
        status: cmd.status,
        details_hidden: false,
        category: cmd.category,
        areas: cmd.area_ids.map(area),
        schedule: cmd.schedule,
        capacity: cmd.capacity,
        public_location: mp ? { kind: 'meeting_point', id: mp.id, name: mp.name } : null,
        visibility: cmd.visibility,
        last_confirmed_at: nowIso,
        unconfirmed: false,
        version: 1,
        created_at: nowIso,
      };
      this.activities.unshift(act);
      return act;
    });
  }

  updateActivity(id: UUID, cmd: ActivityUpdate) {
    return this.write(cmd.operation_key, () => {
      const act = this.ownActivity(id);
      if (act.version !== cmd.version) {
        throw new ApiError({ code: 'stale_version', message_key: 'errors.stale_version', details: { current_version: act.version }, request_id: null }, 409);
      }
      if (act.status === 'ended' && cmd.status && cmd.status !== 'ended') {
        throw new ApiError({ code: 'invalid_transition', message_key: 'errors.invalid_transition', details: null, request_id: null }, 409);
      }
      if (cmd.status) act.status = cmd.status;
      if (cmd.schedule) act.schedule = cmd.schedule;
      if (cmd.capacity !== undefined) act.capacity = cmd.capacity;
      if (cmd.visibility) act.visibility = cmd.visibility;
      act.version += 1;
      return act;
    });
  }

  confirmActivity(id: UUID, operationKey: string) {
    return this.write(operationKey, () => {
      const act = this.ownActivity(id);
      act.last_confirmed_at = new Date(this.now).toISOString();
      act.unconfirmed = false;
      act.version += 1;
      return act;
    });
  }

  listAlertSubscriptions() {
    return this.read(() => (this.isProvider ? this.subscriptions : []));
  }

  createAlertSubscription(cmd: AlertSubscriptionCreate) {
    return this.write(cmd.operation_key, () => {
      this.forbidUnlessProvider();
      const sub: AlertSubscription = {
        id: `sub-${crypto.randomUUID()}`,
        area_ids: cmd.area_ids,
        category: cmd.category,
        trigger: cmd.trigger,
        muted: false,
        created_at: new Date(this.now).toISOString(),
      };
      this.subscriptions.unshift(sub);
      return sub;
    });
  }

  setAlertSubscriptionMuted(id: UUID, muted: boolean) {
    return this.write(null, () => {
      const sub = this.subscriptions.find((s) => s.id === id);
      if (!sub) throw new ApiError({ code: 'not_found', message_key: 'errors.not_found', details: null, request_id: null }, 404);
      sub.muted = muted;
      return sub;
    });
  }

  deleteAlertSubscription(id: UUID) {
    return this.write(null, () => {
      this.subscriptions = this.subscriptions.filter((s) => s.id !== id);
    });
  }

  listAlerts() {
    return this.read(() => (this.isProvider ? this.alerts : []));
  }

  // ---- internals ----

  private ownActivity(id: UUID): Activity {
    this.forbidUnlessProvider();
    const act = this.activities.find((a) => a.id === id);
    if (!act) throw new ApiError({ code: 'not_found', message_key: 'errors.not_found', details: null, request_id: null }, 404);
    if (act.provider_organization.id !== MY_PROVIDER.id) {
      throw new ApiError({ code: 'forbidden', message_key: 'errors.forbidden', details: null, request_id: null }, 403);
    }
    return act;
  }

  /** DOM-053: other providers' internal-only entries keep counting but hide details. */
  private visibleActivities(): Activity[] {
    return this.activities.map((a) => {
      const unconfirmed = a.status === 'active' && this.now - Date.parse(a.last_confirmed_at) > SEVEN_DAYS;
      const view = { ...a, unconfirmed };
      const mine = this.isProvider && a.provider_organization.id === MY_PROVIDER.id;
      if (a.visibility === 'internal' && !mine) {
        return { ...view, details_hidden: true, schedule: null, capacity: null, public_location: null };
      }
      return view;
    });
  }

  private seedActivities(): Activity[] {
    const iso = (msAgo: number) => new Date(this.now - msAgo).toISOString();
    const base = (over: Partial<Activity> & Pick<Activity, 'id' | 'type' | 'category' | 'areas'>): Activity => ({
      provider_organization: { id: MY_PROVIDER.id, name: MY_PROVIDER.name },
      status: 'active',
      details_hidden: false,
      schedule: { kind: 'recurring', days: ['mon', 'wed', 'fri'], start_time: '08:00', end_time: '12:00' },
      capacity: null,
      public_location: null,
      visibility: 'all_providers',
      last_confirmed_at: iso(2 * DAY),
      unconfirmed: false,
      version: 1,
      created_at: iso(20 * DAY),
      ...over,
    });
    const [carga, fund] = OTHER_PROVIDERS as [typeof MY_PROVIDER, typeof MY_PROVIDER];
    return [
      base({
        id: 'act-1',
        type: 'water_distribution_point',
        category: 'water_drinking',
        areas: [area('sec-acacias')],
        capacity: { value: 2000, unit: 'liters' },
        public_location: { kind: 'meeting_point', id: 'mp-acacias-plaza', name: 'Plaza Las Acacias' },
        visibility: 'public',
      }),
      base({
        id: 'act-2',
        type: 'charging_point',
        category: 'charging',
        areas: [area('sec-mirador')],
        capacity: { value: 40, unit: 'devices' },
        last_confirmed_at: iso(9 * DAY),
        schedule: { kind: 'recurring', days: ['sat', 'sun'], start_time: '14:00', end_time: '18:00' },
      }),
      base({
        id: 'act-3',
        type: 'water_delivery',
        category: 'water_drinking',
        areas: [area('sec-quebradita')],
        status: 'planned',
        schedule: { kind: 'one_off', date: new Date(this.now + 2 * DAY).toLocaleDateString('en-CA', { timeZone: 'America/Caracas' }), start_time: '09:00', end_time: '13:00' },
      }),
      base({
        id: 'act-4',
        provider_organization: carga,
        type: 'charging_point',
        category: 'charging',
        areas: [area('sec-carmen')],
        capacity: { value: 60, unit: 'devices' },
        public_location: { kind: 'meeting_point', id: 'mp-carmen-plaza', name: 'Plaza El Carmen' },
      }),
      base({
        id: 'act-5',
        provider_organization: fund,
        type: 'water_distribution_point',
        category: 'water_drinking',
        areas: [area('sec-cedros')],
        visibility: 'internal',
      }),
      base({
        id: 'act-6',
        provider_organization: carga,
        type: 'other',
        category: 'water_other',
        areas: [area('sec-brisas')],
        status: 'ended',
      }),
    ];
  }

  private seedSubscriptions(): AlertSubscription[] {
    return [
      { id: 'sub-1', area_ids: ['sec-acacias', 'sec-mirador'], category: 'water_drinking', trigger: { kind: 'new_urgent' }, muted: false, created_at: new Date(this.now - 10 * DAY).toISOString() },
      { id: 'sub-2', area_ids: ['par-23enero'], category: 'charging', trigger: { kind: 'became_uncovered' }, muted: true, created_at: new Date(this.now - 4 * DAY).toISOString() },
    ];
  }

  private seedAlerts(): Alert[] {
    return [
      { id: 'al-1', subscription_id: 'sub-1', area: area('sec-acacias'), category: 'water_drinking', trigger_kind: 'new_urgent', active_needs: 24, created_at: new Date(this.now - 3 * HOUR).toISOString() },
      { id: 'al-2', subscription_id: 'sub-1', area: area('sec-mirador'), category: 'water_drinking', trigger_kind: 'new_urgent', active_needs: null, created_at: new Date(this.now - 30 * HOUR).toISOString() },
      { id: 'al-3', subscription_id: 'sub-2', area: area('sec-quebradita'), category: 'charging', trigger_kind: 'became_uncovered', active_needs: 8, created_at: new Date(this.now - 2 * DAY).toISOString() },
    ];
  }
}

function dedupeNotes(notes: DataQualityNote[]): DataQualityNote[] {
  const seen = new Set<string>();
  return notes.filter((n) => (seen.has(n.code) ? false : (seen.add(n.code), true)));
}
